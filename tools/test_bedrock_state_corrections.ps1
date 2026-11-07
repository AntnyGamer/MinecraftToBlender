$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../assets/Bedrock_Assets.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('miex-state-models-' + [guid]::NewGuid().ToString('N'))
try {
    # A first install has no extracted base models. Every procedural fallback
    # must still have distinct tinted-line and untinted-overlay planes.
    Set-BedrockStateCorrections $root (Join-Path $PSScriptRoot '../assets') bedrock
    $models = Join-Path $root 'resources/BlenderEEVEE/assets/minecraft/models/block'
    $depths = [System.Collections.Generic.HashSet[string]]::new()
    foreach($name in @('redstone_dust_dot','redstone_dust_side','redstone_dust_side_alt','redstone_dust_up')) {
        $path = Join-Path $models ($name + '.json')
        $model = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        $line = $model.elements[0]; $overlay = $model.elements[1]
        $axis = if($name -eq 'redstone_dust_up') { 2 } else { 1 }
        $baseOffset = switch($name) {
            'redstone_dust_side' { 0.0625 }
            'redstone_dust_side_alt' { 0.125 }
            default { 0.0 }
        }
        if([Math]::Abs(($overlay.from[$axis] - $line.from[$axis]) - 0.03125) -gt 0.0000001) {
            throw ('Redstone overlay remains coincident or incorrectly layered: ' + $name)
        }
        if($name -ne 'redstone_dust_up') {
            foreach($element in @($line,$overlay)) {
                $depth = [string]([Math]::Round([double]$element.from[$axis],7))
                if(-not $depths.Add($depth)) { throw ('Redstone corner planes overlap at ' + $depth) }
            }
        }
        if($line.faces.PSObject.Properties.Value[0].tintindex -ne 0) { throw 'Lost redstone power tint' }
        # Reconstruct the unmodified vanilla-equivalent cached model to verify
        # installation never accumulates height offsets across invocations.
        $base = Join-Path $root ('resources/base_resource_pack/assets/minecraft/models/block/' + $name + '.json')
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $base) | Out-Null
        $line.from[$axis] -= $baseOffset; $line.to[$axis] -= $baseOffset
        $overlay.from[$axis] -= ($baseOffset + 0.03125)
        $overlay.to[$axis] -= ($baseOffset + 0.03125)
        [IO.File]::WriteAllText($base, ($model | ConvertTo-Json -Depth 40))
    }
    Set-BedrockStateCorrections $root (Join-Path $PSScriptRoot '../assets') bedrock
    $once = [IO.File]::ReadAllText((Join-Path $models 'redstone_dust_dot.json'))
    Set-BedrockStateCorrections $root (Join-Path $PSScriptRoot '../assets') bedrock
    if($once -ne [IO.File]::ReadAllText((Join-Path $models 'redstone_dust_dot.json'))) { throw 'Repeated installation accumulates offsets' }
    $connections = Join-Path $root 'resources/BlenderEEVEE/translation/minecraft/bedrock/miex_block_connections.json'
    # Windows PowerShell 5's JSON adapter rejects MiEx's valid empty-string
    # unconditional connection key. Java parses the actual mappings at runtime.
    $json = Get-Content -LiteralPath $connections -Raw
    if($json -notmatch '"mappings"\s*:' -or $json -notmatch '"redstone_wire"\s*:') { throw 'Missing MiEx connection mappings' }
    Set-BedrockStateCorrections $root (Join-Path $PSScriptRoot '../assets') java
    if(Test-Path -LiteralPath $connections) { throw 'Bedrock connections leaked into Java export' }
    if(@(Get-ChildItem -LiteralPath $models -Filter 'redstone_*.json').Count -ne 0) { throw 'Bedrock model overrides leaked into Java export' }
    Write-Host 'Bedrock dust models: fresh install, corner/overlay depth separation, idempotence and edition cleanup passed.'
} finally {
    # Only remove this test's explicitly allocated temporary tree.
    $resolvedRoot = [IO.Path]::GetFullPath($root)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if(-not $resolvedRoot.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
       (Split-Path -Leaf $resolvedRoot) -notmatch '^miex-state-models-[0-9a-f]{32}$') { throw 'Unexpected test cleanup path' }
    if(Test-Path -LiteralPath $resolvedRoot) { Remove-Item -LiteralPath $resolvedRoot -Recurse -Force }
}
