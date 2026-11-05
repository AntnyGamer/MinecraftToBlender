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
function Test-BedrockBedAtlas([string]$path) {
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
    # The pinned Bedrock geometry uses a 64x64 atlas. Permit lossless
    # high-resolution replacements, but never use a corrupt or non-square PNG.
    try {
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $image = [System.Drawing.Image]::FromFile($path)
        try {
            return ($image.RawFormat.Guid -eq [System.Drawing.Imaging.ImageFormat]::Png.Guid -and
                    $image.Width -ge 64 -and $image.Height -ge 64 -and
                    $image.Width -eq $image.Height -and ($image.Width % 64) -eq 0)
        } finally { $image.Dispose() }
    } catch { return $false }
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
        if(Test-Path -LiteralPath $target -PathType Leaf) {
            if(-not (Test-GitBlobSha1 $target $entry.git_blob_sha1)) {
                # This path may contain a user-supplied pack override. Never
                # replace a nonmatching file solely to install a fallback.
                Write-Warning ('Preserving a custom or modified Bedrock bed texture: ' + $target)
            }
            continue
        }
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
    $invalid = @()
    foreach($entry in $manifest.textures) {
        $target = Join-Path $targetDir $entry.to
        if(-not (Test-BedrockBedAtlas $target)) { $invalid += $entry.to }
    }
    if($invalid.Count -gt 0) {
        throw ('Bedrock bed texture(s) missing, corrupt, or incompatible with the 64x64 atlas: ' +
               ($invalid -join ', ') + '. Check internet access and retry; the earlier successful export is preserved.')
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

# The Mojang Bedrock shulker sheets share the 64x64 entity UV atlas layout
# used by MiEx, but Bedrock calls light gray "silver" and undyed "undyed".
# The pinned manifest maps these two names to the importer's Java-style paths.
function Ensure-BedrockShulkerTextures([string]$miexDir,[string]$manifestPath) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if($manifest.source -ne 'Mojang/bedrock-samples' -or
       $manifest.revision -notmatch '^[0-9a-f]{40}$' -or
       $manifest.folder -ne 'resource_pack/textures/entity/shulker' -or
       @($manifest.textures).Count -ne 17) {
        throw 'Pinned Mojang Bedrock shulker-texture manifest is malformed.'
    }
    $targetDir = Join-Path $miexDir 'resources/BlenderEEVEE/assets/minecraft/textures/entity/shulker'
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    $staged = New-Object System.Collections.ArrayList
    $failed = $false
    try {
        foreach($entry in $manifest.textures) {
            if($entry.from -notmatch '^shulker_[a-z_]+\.png$' -or
               $entry.to -notmatch '^shulker(?:_[a-z_]+)?\.png$' -or
               $entry.git_blob_sha1 -notmatch '^[0-9a-f]{40}$') {
                throw 'Invalid filename or hash in pinned Mojang shulker texture manifest.'
            }
            $target = Join-Path $targetDir $entry.to
            if(Test-Path -LiteralPath $target -PathType Leaf) {
                if(-not (Test-GitBlobSha1 $target $entry.git_blob_sha1)) {
                    # May be a customized Minecraft pack texture.
                    Write-Warning ('Preserving existing custom shulker texture: ' + $target)
                }
                continue
            }
            $temp = $target + '.new'
            $url = 'https://raw.githubusercontent.com/' + $manifest.source + '/' + $manifest.revision + '/' + $manifest.folder + '/' + $entry.from
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temp -TimeoutSec 15 -ErrorAction Stop
                if(-not (Test-GitBlobSha1 $temp $entry.git_blob_sha1) -or
                   -not (Test-BedrockBedAtlas $temp)) {
                    throw ('Bedrock shulker atlas validation failed: ' + $entry.from)
                }
                [void]$staged.Add(@{ from=$temp; to=$target })
            } catch {
                Write-Warning ('Official Bedrock shulker textures unavailable; keeping existing textures. ' + $_.Exception.Message)
                $failed = $true
                break
            }
        }
        # Do not apply only some of the 17 official atlases, which could
        # produce a mixed Java/Bedrock appearance after a failed download.
        if(-not $failed) {
            foreach($item in $staged) {
                Move-Item -LiteralPath $item.from -Destination $item.to -ErrorAction Stop
            }
            Write-Host 'Bedrock shulker-box textures: verified official 64x64 atlases where absent.' -ForegroundColor Green
        }
    } finally {
        foreach($item in $staged) {
            if(Test-Path -LiteralPath $item.from) {
                Remove-Item -LiteralPath $item.from -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Remove-ManagedBedrockShulkerTextures([string]$miexDir,[string]$manifestPath) {
    # Only managed, hash-identical Mojang files may be removed. Custom textures
    # remain intact when changing to Java or world resource packs.
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if($manifest.source -ne 'Mojang/bedrock-samples' -or
       $manifest.folder -ne 'resource_pack/textures/entity/shulker' -or
       $manifest.revision -notmatch '^[0-9a-f]{40}$' -or
       @($manifest.textures).Count -ne 17) {
        throw 'Pinned Mojang Bedrock shulker-texture manifest is malformed.'
    }
    $targetDir = Join-Path $miexDir 'resources/BlenderEEVEE/assets/minecraft/textures/entity/shulker'
    if(-not (Test-Path -LiteralPath $targetDir -PathType Container)) { return }
    foreach($entry in $manifest.textures) {
        if($entry.to -notmatch '^shulker(?:_[a-z_]+)?\.png$' -or
           $entry.git_blob_sha1 -notmatch '^[0-9a-f]{40}$') {
            throw 'Invalid filename or hash in pinned Mojang shulker texture manifest.'
        }
        $target = Join-Path $targetDir $entry.to
        if(Test-GitBlobSha1 $target $entry.git_blob_sha1) {
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
        }
    }
}
