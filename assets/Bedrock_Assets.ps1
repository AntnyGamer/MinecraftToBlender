# Optional official vanilla Bedrock bed textures for MiEx's Java-style model paths.
# Files are downloaded on the user's machine only; the EXE does not ship game art.
function Test-GitBlobSha1([string]$path,[string]$expected) {
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $prefix = [System.Text.Encoding]::ASCII.GetBytes(('blob ' + $bytes.Length + [char]0))
    $payload = New-Object byte[] ($prefix.Length + $bytes.Length)
    [System.Array]::Copy($prefix, 0, $payload, 0, $prefix.Length)
    [System.Array]::Copy($bytes, 0, $payload, $prefix.Length, $bytes.Length)
    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    try {
        $actual = ([System.BitConverter]::ToString($sha1.ComputeHash($payload))).Replace('-', '').ToLowerInvariant()
        return $actual -eq $expected
    } finally { $sha1.Dispose() }
}
function Ensure-BedrockBedTextures([string]$miexDir,[string]$manifestPath) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if($manifest.source -ne 'Mojang/bedrock-samples' -or
       $manifest.revision -notmatch '^[0-9a-f]{40}$' -or
       $manifest.folder -ne 'resource_pack/textures/entity/bed' -or
       @($manifest.textures).Count -ne 16) {
        throw 'Pinned Mojang Bedrock bed-texture manifest is malformed.'
    }
    $targetDir = Join-Path $miexDir 'resources/BlenderEEVEE/assets/minecraft/textures/entity/bed'
    $networkUnavailable = $false
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    foreach($entry in $manifest.textures) {
        if($entry.from -notmatch '^[a-z_]+\.png$' -or $entry.to -notmatch '^[a-z_]+\.png$' -or
           $entry.git_blob_sha1 -notmatch '^[0-9a-f]{40}$') {
            throw 'Unexpected filename or hash in the pinned Mojang texture manifest.'
        }
        $target = Join-Path $targetDir $entry.to
        if(Test-GitBlobSha1 $target $entry.git_blob_sha1) { continue }
        if($networkUnavailable) { continue }
        $temp = $target + '.new'
        $url = 'https://raw.githubusercontent.com/' + $manifest.source + '/' + $manifest.revision + '/' + $manifest.folder + '/' + $entry.from
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temp -TimeoutSec 15 -ErrorAction Stop
            if(-not (Test-GitBlobSha1 $temp $entry.git_blob_sha1)) {
                throw ('Pinned Mojang texture verification failed: ' + $entry.from)
            }
            Move-Item -LiteralPath $temp -Destination $target -Force -ErrorAction Stop
        } catch {
            $networkUnavailable = $true
            Write-Warning ('Bedrock bed texture download failed; using available cached resources instead. ' + $_.Exception.Message)
        } finally {
            if(Test-Path -LiteralPath $temp) {
                Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Remove-ManagedBedrockBedTextures([string]$miexDir,[string]$manifestPath) {
    # Don't let an earlier Bedrock export's fallback textures override Java or
    # a later world supplied resource pack. Never remove non-matching files.
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $targetDir = Join-Path $miexDir 'resources/BlenderEEVEE/assets/minecraft/textures/entity/bed'
    if(-not (Test-Path -LiteralPath $targetDir -PathType Container)) { return }
    foreach($entry in $manifest.textures) {
        if($entry.to -notmatch '^[a-z_]+\.png$' -or $entry.git_blob_sha1 -notmatch '^[0-9a-f]{40}$') {
            throw 'Unexpected filename or hash in the Bedrock texture manifest.'
        }
        $target = Join-Path $targetDir $entry.to
        if(Test-GitBlobSha1 $target $entry.git_blob_sha1) {
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
        }
    }
}
