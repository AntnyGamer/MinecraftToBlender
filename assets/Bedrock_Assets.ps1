# Bedrock reader overlay and official vanilla textures for MiEx model paths.
function Install-BedrockReaderClass([string]$sourceJar, [string]$classPath) {
    $expectedClass = 'f1cb94f95ed619139acdfe0ed2207fe21531613b9a160d818e792034c20718d5'
    if((Get-FileHash -LiteralPath $sourceJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne
       'e4951d44116fd2d90c14f52643b7cd66ddd7f64ac108b8a16705b379672de707' -or
       (Get-FileHash -LiteralPath $classPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedClass) {
        throw 'Unrecognized MiEx JAR or Bedrock reader overlay. Refusing an unverified patch.'
    }
    $root = Join-Path (Split-Path -Parent $sourceJar) 'bedrock_reader'
    $target = Join-Path $root 'nl/bramstout/mcworldexporter/world/bedrock/ChunkBedrock.class'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    [IO.File]::Copy($classPath, $target, $true)
    Write-Host 'Bedrock block-entity reader: corrected section bounds; original MiEx.jar unchanged.'
    return $root
}

function Set-BedrockDetailModels([string]$miexDir,[string]$assetDir,[string]$edition) {
    $files = @{
        'Bedrock_Armor_Stand.json' = 'entities/armor_stand.json'
        'Bedrock_Armor_Boots.json' = 'attachments/boots.json'
        'Bedrock_Armor_Chestplate.json' = 'attachments/chestplate.json'
        'Bedrock_Armor_Helmet.json' = 'attachments/helmet.json'
        'Bedrock_Armor_Leggings.json' = 'attachments/leggings.json'
    }
    foreach($entry in $files.GetEnumerator()) {
        $target = Join-Path $miexDir ('resources/BlenderEEVEE/builtins/minecraft/' + $entry.Value)
        if($edition -eq 'bedrock') {
            $source = Join-Path $assetDir $entry.Key
            [void](Get-Content -LiteralPath $source -Raw | ConvertFrom-Json)
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
        } elseif(Test-Path -LiteralPath $target -PathType Leaf) {
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
        }
    }
}

function Ensure-BannerBaseAlias([string]$miexDir) {
    # Recent Java assets moved this sheet into entity/banner/. Pinned MiEx
    # still requests entity/banner_base for the pole/crossbar material.
    $target = Join-Path $miexDir 'resources/BlenderEEVEE/assets/minecraft/textures/entity/banner_base.png'
    $source = Join-Path $miexDir 'resources/base_resource_pack/assets/minecraft/textures/entity/banner/banner_base.png'
    $tga = [IO.Path]::ChangeExtension($target, '.tga')
    if((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $tga)) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if(Test-Path -LiteralPath $source -PathType Leaf) {
        [IO.File]::Copy($source, $target, $false)
        return
    }
    # First-run MiEx may not have installed its Java textures yet. Its image
    # loader and Blender also support Mojang's original Bedrock TGA sheet.
    $temp = $tga + '.' + [guid]::NewGuid().ToString('N') + '.partial'
    try {
        $url = 'https://raw.githubusercontent.com/Mojang/bedrock-samples/15701fa9c13923f12662984c32c124327e40e3d3/resource_pack/textures/entity/banner/banner_base.tga'
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temp -TimeoutSec 15 -ErrorAction Stop
        if(-not (Test-GitBlobSha1 $temp '91a21d0511a0d0cf0c2ad14261126eee2af53814')) {
            throw 'Official banner base texture hash mismatch.'
        }
        Move-Item -LiteralPath $temp -Destination $tga -ErrorAction Stop
    } catch {
        Write-Warning ('Banner pole texture unavailable: ' + $_.Exception.Message)
    } finally {
        if(Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}

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
    # Don't let Bedrock's differently arranged bed atlas override Java.
    # Bedrock world packs have higher priority and retain these fallbacks.
    # Never remove non-matching files.
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
    # remain intact when changing to Java. Bedrock world packs retain fallbacks.
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
