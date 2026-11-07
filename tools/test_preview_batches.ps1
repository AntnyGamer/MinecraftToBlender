$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$source = Join-Path $PSScriptRoot '../assets/Export_World.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $source), [ref]$tokens, [ref]$parseErrors)
if($parseErrors.Count -gt 0) { throw $parseErrors }
foreach($name in @('Get-PreviewChunkCoordinates', 'New-PreviewChunkCommands',
                  'Update-PreviewChunkProgress', 'Start-CapturedProcess',
                  'Finish-CapturedProcess', 'Format-MiExMemory')) {
    $definitions = @($ast.FindAll({ param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq $name
    }, $true))
    if($definitions.Count -ne 1) { throw "Missing preview helper: $name" }
    . ([ScriptBlock]::Create($definitions[0].Extent.Text))
}

$chunks = @(Get-PreviewChunkCoordinates -32 31 -32 31)
# The northernmost row is deliberately requested last. Its samples keep
# exact coordinates, and no extra chunks are fetched.
if($chunks[0].chunkZ -ne -31 -or $chunks[$chunks.Count - 1].chunkZ -ne -32) {
    throw 'Northern preview boundary was not deferred until after interior chunks'
}
$coarse = @(Get-PreviewChunkCoordinates -80 79 -80 79)
if($coarse.Count -ne 9216 -or $coarse[0].chunkZ -le -80 -or
   $coarse[$coarse.Count - 1].chunkZ -ne -80) {
    throw 'Coarse preview did not keep the northern sampled edge last'
}
# Coarse rows reuse the exact same 96 X samples in their original order.
$expectedX = @(for($col = 0; $col -lt 96; $col++) {
    [int][math]::Floor(-80 + 159 * ($col / [double]95))
})
foreach($row in @(0, 1, 47, 95)) {
    $actualX = @($coarse[($row * 96)..($row * 96 + 95)] | ForEach-Object { $_.chunkX })
    if(($actualX -join ',') -ne ($expectedX -join ',')) {
        throw "Coarse preview X samples changed in row $row"
    }
}
$commands = @(New-PreviewChunkCommands $chunks 64)
if($chunks.Count -ne 4096 -or $commands.Count -ne 65) {
    throw 'Expected 4096 positions, 64 regular batches and one cold-start replay'
}
$firstKeys = @($commands[0].chunks | ForEach-Object { "$($_.chunkX),$($_.chunkZ)" })
$retryKeys = @($commands[-1].chunks | ForEach-Object { "$($_.chunkX),$($_.chunkZ)" })
if(($retryKeys -join ';') -ne ($firstKeys -join ';')) {
    throw 'Final warm-reader retry must repeat the original first batch exactly'
}
$sent = @($commands[0..($commands.Count - 2)] | ForEach-Object {
    if($_.command -ne 'getChunk' -or $_.image -ne $true -or
       @($_.chunks).Count -gt 64 -or @($_.chunks).Count -lt 1) {
        throw 'Invalid preview batch shape'
    }
    $_.chunks
})
$expectedKeys = @($chunks | ForEach-Object { "$($_.chunkX),$($_.chunkZ)" })
$actualKeys = @($sent | ForEach-Object { "$($_.chunkX),$($_.chunkZ)" })
if(($actualKeys -join ';') -ne ($expectedKeys -join ';')) {
    throw 'Preview batches lost, duplicated or reordered source coordinates'
}
$tail = @(New-PreviewChunkCommands $chunks[0..64] 64)
if($tail.Count -ne 3 -or @($tail[1].chunks).Count -ne 1 -or
   @($tail[2].chunks).Count -ne 64) {
    throw 'Final partial batch or first-batch replay was not preserved'
}
if(@(New-PreviewChunkCommands @() 64).Count -ne 0) {
    throw 'Empty preview created commands'
}

$fixture = Join-Path ([IO.Path]::GetTempPath()) ('miex-preview-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$log = Join-Path $fixture 'progress.log'
$stdout = Join-Path $fixture 'stdout.log'
$stderr = Join-Path $fixture 'stderr.log'
try {
    $script:previewLogCursor = [long]0
    $script:previewPendingLine = ''
    $script:previewBatchesFinished = 0
    $script:previewLastResponse = [DateTime]::UtcNow
    $success = '[COMMAND] {"status":"success","chunks":[]}'
    [IO.File]::WriteAllText($log, $success + [Environment]::NewLine)
    Update-PreviewChunkProgress $log 65 64
    Update-PreviewChunkProgress $log 65 64
    if($script:previewBatchesFinished -ne 1) { throw 'Repeated poll counted progress twice' }
    [IO.File]::AppendAllText($log, '[COMMAND] {"status":"error","chunks":[]}' + [Environment]::NewLine)
    [IO.File]::AppendAllText($log, $success.Substring(0, 20))
    Update-PreviewChunkProgress $log 65 64
    if($script:previewBatchesFinished -ne 1) { throw 'Error or incomplete response counted as success' }
    [IO.File]::AppendAllText($log, $success.Substring(20) + [Environment]::NewLine)
    $messages = @(Update-PreviewChunkProgress $log 65 64 6>&1)
    if($script:previewBatchesFinished -ne 2 -or ($messages -join '') -notmatch '65/65') {
        throw 'Completed partial response or final batch count was lost'
    }
    # A fast child can exit before its first poll. Exercise the real captured
    # pipes and final drain rather than relying on a synthetic file alone.
    $script:previewLogCursor = [long]0
    $script:previewPendingLine = ''
    $script:previewBatchesFinished = 0
    $child = @'
[Console]::Out.WriteLine('[COMMAND] {"status":"success","chunks":[]}')
exit 0
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
    $shell = (Get-Process -Id $PID).Path
    $capture = Start-CapturedProcess $shell "-NoLogo -NoProfile -NonInteractive -EncodedCommand $encoded" $fixture $stdout $stderr
    $code = Finish-CapturedProcess $capture -PreviewOnly
    Update-PreviewChunkProgress $stdout 1 64
    if($code -ne 0 -or $script:previewBatchesFinished -ne 1) {
        throw 'Final response from an exited child was lost'
    }
} finally {
    foreach($path in @($log, $stdout, $stderr)) {
        if(Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
    Remove-Item -LiteralPath $fixture -Force
}
Write-Host 'Lossless preview batches, cold-start replay, incremental/partial progress and final pipe drain passed.'
