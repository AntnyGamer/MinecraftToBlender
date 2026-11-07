# Bedrock reader overlay and official vanilla textures for MiEx model paths.
$script:miexExporterPackName = 'BlenderEEVEE'
function Get-MiExExporterPackRoot([string]$miexDir) {
    if($script:miexExporterPackName -notmatch '^BlenderEEVEE(?:_java|_bedrock)?$') { throw 'Invalid exporter pack name.' }
    return Join-Path $miexDir ('resources/' + $script:miexExporterPackName)
}
function Copy-VerifiedLegacyTexture([string]$miexDir,[string]$target,[string]$relative,[string]$hash) {
    if(Test-Path -LiteralPath $target) { return $false }
    $source = Join-Path $miexDir ('resources/BlenderEEVEE/' + $relative)
    if(Test-GitBlobSha1 $source $hash) {
        [IO.File]::Copy($source, $target, $false)
        return $true
    }
    return $false
}
function Test-UsablePortalTexture([string]$path) {
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
    try {
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $image = [System.Drawing.Image]::FromFile($path)
        try {
            return ($image.RawFormat.Guid -eq [System.Drawing.Imaging.ImageFormat]::Png.Guid -and
                    $image.Width -gt 0 -and $image.Height -gt 0)
        } finally { $image.Dispose() }
    } catch { return $false }
}
function Ensure-BedrockPortalTexture([string]$miexDir,[string]$edition) {
    $relative = 'assets/minecraft/textures/block/end_portal.png'
    $target = Join-Path (Get-MiExExporterPackRoot $miexDir) $relative
    $hash = '7b4dbaf59ac9a115c7b6af2a1cfdbd110470255a'
    # Both editions' pinned models use this static portal approximation.
    # Keep valid custom PNGs, but never treat a corrupt cache entry as usable.
    if(Test-Path -LiteralPath $target) {
        if(-not (Test-UsablePortalTexture $target)) {
            throw ('Existing End portal texture is not a valid PNG: ' + $target +
                   '. The file was preserved; repair it and retry.')
        }
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if(Copy-VerifiedLegacyTexture $miexDir $target $relative $hash) {
        if(-not (Test-UsablePortalTexture $target)) {
            throw 'Hash-matched legacy End portal texture could not be decoded as PNG.'
        }
        return
    }
    $temp = $target + '.' + [guid]::NewGuid().ToString('N') + '.partial'
    try {
        $url = 'https://raw.githubusercontent.com/Mojang/bedrock-samples/15701fa9c13923f12662984c32c124327e40e3d3/resource_pack/textures/blocks/end_portal.png'
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temp -TimeoutSec 15 -ErrorAction Stop
        if(-not (Test-GitBlobSha1 $temp $hash) -or -not (Test-UsablePortalTexture $temp)) {
            throw 'Official End portal texture failed hash or PNG validation.'
        }
        Move-Item -LiteralPath $temp -Destination $target -ErrorAction Stop
    } finally {
        if(Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}

function Set-SharedBlockModels([string]$miexDir,[string]$assetDir,[string]$edition) {
    $files = @{
        'Bedrock_Copper_Chests.json' = 'copper_chests.json'
        'Bedrock_Decorated_Pots.json' = 'decorated_pot.json'
        'Bedrock_Enchanting_Table.json' = 'enchanting_table.json'
        'Bedrock_End_Portals.json' = 'end_portals.json'
        'Bedrock_Skulls.json' = 'skull.json'
    }
    if($edition -eq 'java') {
        $files['Java_Copper_Statues.json'] = 'copper_statues.json'
        $files['Java_Conduits.json'] = 'conduit.json'
    } else {
        $files['Bedrock_Copper_Statues.json'] = 'copper_statues.json'
        $files['Bedrock_Conduits.json'] = 'conduit.json'
    }
    foreach($entry in $files.GetEnumerator()) {
        $source = Join-Path $assetDir $entry.Key
        $doc = Get-Content -LiteralPath $source -Raw | ConvertFrom-Json
        if(-not $doc.blocks -or -not $doc.handler) { throw ('Invalid shared block model: ' + $source) }
        $target = Join-Path (Get-MiExExporterPackRoot $miexDir) ('builtins/minecraft/blockstates/' + $entry.Value)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        if($edition -eq 'java' -and $entry.Key -eq 'Bedrock_Skulls.json') {
            # Keep native Java skull/player-profile handling. Only these four
            # newer head IDs have no native geometry in the pinned exporter.
            $doc.blocks = @($doc.blocks | Where-Object { $_ -match '^minecraft:(dragon|piglin)(_wall)?_head$' })
            [IO.File]::WriteAllText($target, ($doc | ConvertTo-Json -Depth 80), [Text.UTF8Encoding]::new($false))
        } else {
            Copy-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
        }
    }
    return @($files.Values)
}

function Ensure-LegacyChainModel([string]$miexDir) {
    $baseModels = Join-Path $miexDir 'resources/base_resource_pack/assets/minecraft/blockstates'
    $target = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/blockstates/chain.json'
    $managed = $false
    if(Test-Path -LiteralPath $target -PathType Leaf) {
        $existing = Get-Content -LiteralPath $target -Raw | ConvertFrom-Json
        $marker = $existing.PSObject.Properties['_minecraft_to_blender_generated']
        $managed = $null -ne $marker -and $marker.Value -eq 'legacy_chain_v1'
        if(-not $managed) { return }
    }
    if(Test-Path -LiteralPath (Join-Path $baseModels 'chain.json') -PathType Leaf) {
        if($managed) { Remove-Item -LiteralPath $target -Force }
        return
    }
    $modern = Join-Path $baseModels 'iron_chain.json'
    if(Test-Path -LiteralPath $modern -PathType Leaf) {
        $doc = Get-Content -LiteralPath $modern -Raw | ConvertFrom-Json
    } else {
        # On a first run MiEx chooses the newest *installed* client, which
        # may still use the old name. Do not override it with an unverified
        # modern model reference. Recheck once the base resources exist.
        if($managed) { Remove-Item -LiteralPath $target -Force }
        return
    }
    $doc | Add-Member -NotePropertyName '_minecraft_to_blender_generated' -NotePropertyValue 'legacy_chain_v1' -Force
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    [IO.File]::WriteAllText($target, ($doc | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
}

function Read-JavaBedManifest([string]$manifestPath) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $colors = @('white','orange','magenta','light_blue','yellow','lime','pink','gray','light_gray','cyan','purple','blue','brown','green','red','black')
    if($manifest.version -ne '26.1.2' -or $manifest.client_sha1 -notmatch '^[0-9a-f]{40}$' -or
       $manifest.client_url -ne ('https://piston-data.mojang.com/v1/objects/' + $manifest.client_sha1 + '/client.jar') -or
       @($manifest.textures).Count -ne 16) { throw 'Malformed pinned Java bed texture manifest.' }
    $seen = @{}
    foreach($entry in $manifest.textures) {
        if($entry.file -notmatch '^[a-z_]+\.png$' -or [IO.Path]::GetFileNameWithoutExtension($entry.file) -notin $colors -or
           $entry.sha256 -notmatch '^[0-9a-f]{64}$' -or $seen.ContainsKey($entry.file)) {
            throw 'Unexpected Java bed texture filename or hash.'
        }
        $seen[$entry.file] = $true
    }
    return $manifest
}

function Remove-ManagedJavaBedTextures([string]$miexDir,[string]$manifestPath) {
    $manifest = Read-JavaBedManifest $manifestPath
    $folder = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/bed'
    foreach($entry in $manifest.textures) {
        $target = Join-Path $folder $entry.file
        if((Test-Path -LiteralPath $target -PathType Leaf) -and
           (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -eq $entry.sha256) {
            Remove-Item -LiteralPath $target -Force
        }
    }
}

function Ensure-JavaBedTextures([string]$miexDir,[string]$manifestPath,[string]$clientJar='') {
    $manifest = Read-JavaBedManifest $manifestPath
    $folder = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/bed'
    $baseFolder = Join-Path $miexDir 'resources/base_resource_pack/assets/minecraft/textures/entity/bed'
    $needed = New-Object 'System.Collections.Generic.List[object]'
    foreach($entry in $manifest.textures) {
        $target = Join-Path $folder $entry.file
        $baseAtlas = Join-Path $baseFolder $entry.file
        if((Test-Path -LiteralPath $target) -and -not (Test-Path -LiteralPath $target -PathType Leaf)) {
            throw ('Java bed atlas path is not a file: ' + $target)
        }
        $existing = if(Test-Path -LiteralPath $target -PathType Leaf) { $target }
                    elseif(Test-Path -LiteralPath $baseAtlas -PathType Leaf) { $baseAtlas }
                    else { $null }
        if($existing) {
            # Retain custom/HD sheets, but don't treat a truncated PNG as a
            # usable atlas just because its filename is present in the cache.
            if(-not (Test-BedrockBedAtlas $existing)) {
                throw ('Java bed atlas is corrupt or incompatible: ' + $existing + '. Existing files were preserved; repair this image and retry.')
            }
        } else {
            $needed.Add($entry)
        }
    }
    if($needed.Count -eq 0) { return }
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $candidates = @($clientJar)
    $minecraftRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) '.minecraft'
    $candidates += Join-Path $minecraftRoot ('versions/' + $manifest.version + '/' + $manifest.version + '.jar')
    $verifiedJar = $null
    foreach($candidate in $candidates) {
        if($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf) -and
           (Get-FileHash -LiteralPath $candidate -Algorithm SHA1).Hash.ToLowerInvariant() -eq $manifest.client_sha1) {
            $verifiedJar = $candidate
            break
        }
    }
    $download = $null
    $archive = $null
    $staged = New-Object 'System.Collections.Generic.List[object]'
    try {
        if(-not $verifiedJar) {
            $download = Join-Path $miexDir ('java_bed_reference_' + [guid]::NewGuid().ToString('N') + '.partial')
            Write-Host 'Restoring missing Java bed atlases from the pinned official client (one-time download).'
            Invoke-WebRequest -UseBasicParsing -Uri $manifest.client_url -OutFile $download -TimeoutSec 180 -ErrorAction Stop
            if((Get-FileHash -LiteralPath $download -Algorithm SHA1).Hash.ToLowerInvariant() -ne $manifest.client_sha1) {
                throw 'Official Java client hash mismatch.'
            }
            $verifiedJar = $download
        }
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($verifiedJar)
        foreach($entry in $needed) {
            $zipEntry = $archive.GetEntry('assets/minecraft/textures/entity/bed/' + $entry.file)
            if($null -eq $zipEntry) { throw ('Missing official Java bed atlas: ' + $entry.file) }
            $target = Join-Path $folder $entry.file
            $temp = $target + '.' + [guid]::NewGuid().ToString('N') + '.partial'
            $staged.Add(@{from=$temp; to=$target})
            $inputStream = $zipEntry.Open()
            try {
                $outputStream = [IO.File]::Create($temp)
                try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
            } finally { $inputStream.Dispose() }
            if((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256 -or
               -not (Test-BedrockBedAtlas $temp)) { throw ('Invalid official Java bed atlas: ' + $entry.file) }
        }
        foreach($item in $staged) { Move-Item -LiteralPath $item.from -Destination $item.to -ErrorAction Stop }
        Write-Host ('Java bed textures: restored ' + $needed.Count + ' verified atlases; existing textures retained.')
    } finally {
        if($null -ne $archive) { $archive.Dispose() }
        foreach($item in $staged) { if(Test-Path -LiteralPath $item.from) { Remove-Item -LiteralPath $item.from -Force } }
        if($download -and (Test-Path -LiteralPath $download)) { Remove-Item -LiteralPath $download -Force }
    }
}

function Set-BedrockStateCorrections([string]$miexDir,[string]$assetDir,[string]$edition) {
    $pack = Get-MiExExporterPackRoot $miexDir
    $connections = Join-Path $pack 'translation/minecraft/bedrock/miex_block_connections.json'
    $models = Join-Path $pack 'assets/minecraft/models/block'
    # Preserve installed vanilla models where available. On a first run MiEx
    # installs its base pack later, so use equivalent simple dust planes until
    # those files exist. No game textures or upstream files are changed.
    $names = @('redstone_dust_dot', 'redstone_dust_side', 'redstone_dust_side_alt', 'redstone_dust_up')
    if($edition -ne 'bedrock') {
        foreach($target in @($connections) + @($names | ForEach-Object { Join-Path $models ($_ + '.json') })) {
            if(Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
        }
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $connections), $models | Out-Null
    Copy-Item -LiteralPath (Join-Path $assetDir 'Bedrock_Block_Connections.json') -Destination $connections -Force
    foreach($name in $names) {
        $source = Join-Path $miexDir ('resources/base_resource_pack/assets/minecraft/models/block/' + $name + '.json')
        $target = Join-Path $models ($name + '.json')
        if(Test-Path -LiteralPath $source -PathType Leaf) {
            $model = Get-Content -LiteralPath $source -Raw | ConvertFrom-Json
        } else {
            $from = @(0, 0.25, 0); $to = @(16, 0.25, 16)
            $uv = @(0, 0, 16, 16); $uvBack = @(0, 16, 16, 0)
            $front = 'up'; $back = 'down'; $line = 'block/redstone_dust_dot'
            if($name -eq 'redstone_dust_side') { $to[2] = 8; $uv[3] = 8; $uvBack = @(0, 8, 16, 0) }
            if($name -eq 'redstone_dust_side_alt') { $from[2] = 8; $uv[1] = 8; $uvBack = @(0, 16, 16, 8) }
            if($name -eq 'redstone_dust_up') {
                $from = @(0, 0, 0.25); $to = @(16, 16, 0.25)
                $front = 'south'; $back = 'north'; $uvBack = @(16, 0, 0, 16)
                $line = 'block/redstone_dust_line1'
            }
            $elements = foreach($texture in @('#line', '#overlay')) {
                $faces = @{}
                $faces[$front] = @{uv=$uv; texture=$texture}
                $faces[$back] = @{uv=$uvBack; texture=$texture}
                if($texture -eq '#line') { $faces[$front].tintindex = 0; $faces[$back].tintindex = 0 }
                @{from=$from.Clone(); to=$to.Clone(); faces=$faces}
            }
            $model = @{ambientocclusion=$false; textures=@{particle='block/redstone_dust_dot'; line=$line; overlay='block/redstone_dust_overlay'}; elements=@($elements)} |
                ConvertTo-Json -Depth 20 | ConvertFrom-Json
        }
        # Several dust pieces share the same base plane at corners. Their
        # transparent quads z-fight with each other, independently of the
        # overlay-vs-line conflict. Give those overlapping variants distinct
        # tiny depth layers (model coordinates, 16 units per block) and keep
        # the untinted overlay above its own tinted wire.
        $planeBase = switch($name) {
            'redstone_dust_side' { 0.0625 }
            'redstone_dust_side_alt' { 0.125 }
            default { 0.0 }
        }
        foreach($element in $model.elements) {
            $faces = @($element.faces.PSObject.Properties)
            if($faces.Count -eq 0) { continue }
            $overlay = @($faces | Where-Object { $_.Value.texture -eq '#overlay' }).Count -eq $faces.Count
            $offset = $planeBase + $(if($overlay) { 0.03125 } else { 0.0 })
            if($offset -eq 0.0) { continue }
            for($axis = 0; $axis -lt 3; $axis++) {
                if($element.from[$axis] -eq $element.to[$axis]) {
                    $element.from[$axis] = [double]$element.from[$axis] + $offset
                    $element.to[$axis] = [double]$element.to[$axis] + $offset
                    break
                }
            }
        }
        [IO.File]::WriteAllText($target, ($model | ConvertTo-Json -Depth 40), [Text.UTF8Encoding]::new($false))
    }
    Write-Host 'Bedrock state corrections: directional redstone connections and separated corner/overlay planes.'
}

function Install-BedrockReaderClass([string]$sourceJar, [string]$classPath) {
    $expectedClass = '3df2a9e27c6fb18bcac3f606ad15646df4db60aea4b3843a658248a2b29f2fb4'
    if((Get-FileHash -LiteralPath $sourceJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne
       'e4951d44116fd2d90c14f52643b7cd66ddd7f64ac108b8a16705b379672de707' -or
       (Get-FileHash -LiteralPath $classPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedClass) {
        throw 'Unrecognized MiEx JAR or Bedrock reader overlay. Refusing an unverified patch.'
    }
    $root = Join-Path (Split-Path -Parent $sourceJar) 'bedrock_reader'
    $target = Join-Path $root 'nl/bramstout/mcworldexporter/world/bedrock/ChunkBedrock.class'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    [IO.File]::Copy($classPath, $target, $true)
    Write-Host 'Bedrock block-entity reader: corrected bounds, dye, attachments and piston state; original MiEx.jar unchanged.'
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
        $target = Join-Path (Get-MiExExporterPackRoot $miexDir) ('builtins/minecraft/' + $entry.Value)
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
    $target = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/banner_base.png'
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
    if(Copy-VerifiedLegacyTexture $miexDir $tga 'assets/minecraft/textures/entity/banner_base.tga' '91a21d0511a0d0cf0c2ad14261126eee2af53814') { return }
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
    $stream = [System.IO.File]::OpenRead($path)
    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    try {
        # Git hashes "blob <size>\0" followed by the exact file bytes.
        # Stream the input instead of allocating two complete file copies.
        $prefix = [System.Text.Encoding]::ASCII.GetBytes(('blob ' + $stream.Length + [char]0))
        [void]$sha1.TransformBlock($prefix, 0, $prefix.Length, $prefix, 0)
        $buffer = New-Object byte[] 65536
        while(($length = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            [void]$sha1.TransformBlock($buffer, 0, $length, $buffer, 0)
        }
        [void]$sha1.TransformFinalBlock([byte[]]@(), 0, 0)
        $actual = ([System.BitConverter]::ToString($sha1.Hash)).Replace('-', '').ToLowerInvariant()
        return $actual -eq $expected
    } finally {
        $stream.Dispose()
        $sha1.Dispose()
    }
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
    $targetDir = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/bed'
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
        if(Copy-VerifiedLegacyTexture $miexDir $target ('assets/minecraft/textures/entity/bed/' + $entry.to) $entry.git_blob_sha1) { continue }
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
    $targetDir = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/bed'
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
    $targetDir = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/shulker'
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
            if(Copy-VerifiedLegacyTexture $miexDir $target ('assets/minecraft/textures/entity/shulker/' + $entry.to) $entry.git_blob_sha1) { continue }
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
    $targetDir = Join-Path (Get-MiExExporterPackRoot $miexDir) 'assets/minecraft/textures/entity/shulker'
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
