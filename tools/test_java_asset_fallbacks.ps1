$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../assets/Bedrock_Assets.ps1')
$assetDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../assets'))
$root = Join-Path ([IO.Path]::GetTempPath()) ('miex-java-assets-' + [guid]::NewGuid().ToString('N'))
function Assert-VisualTest([bool]$condition,[string]$message) { if(-not $condition) { throw $message } }
function Invoke-WebRequest {
    [CmdletBinding()]
    param($Uri,$OutFile,[switch]$UseBasicParsing,[int]$TimeoutSec)
    throw 'Network must not be needed when a verified client or textures already exist.'
}
try {
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $shared = @(Set-SharedBlockModels $root $assetDir java)
    $models = Join-Path $root 'resources/BlenderEEVEE/builtins/minecraft/blockstates'
    Assert-VisualTest ($shared.Count -eq 7) 'Missing shared Java models'
    $heads = Get-Content -LiteralPath (Join-Path $models 'skull.json') -Raw | ConvertFrom-Json
    Assert-VisualTest (@($heads.blocks).Count -eq 4) 'Java must retain native player/skull handling'
    Assert-VisualTest (@($heads.blocks | Where-Object { $_ -notmatch '^minecraft:(dragon|piglin)(_wall)?_head$' }).Count -eq 0) 'Unexpected Java head override'
    $statues = Get-Content -LiteralPath (Join-Path $models 'copper_statues.json') -Raw | ConvertFrom-Json
    Assert-VisualTest (@($statues.handler.children).Count -eq 4) 'Missing Java statue poses'
    $conduit = Get-Content -LiteralPath (Join-Path $models 'conduit.json') -Raw | ConvertFrom-Json
    Assert-VisualTest ($conduit.handler[0].variables[0].Contains('waterlogged')) 'Java conduit must derive activation'
    $null = Set-SharedBlockModels $root $assetDir bedrock
    $heads = Get-Content -LiteralPath (Join-Path $models 'skull.json') -Raw | ConvertFrom-Json
    Assert-VisualTest (@($heads.blocks).Count -eq 14) 'Bedrock must retain all normalized head types'
    $conduit = Get-Content -LiteralPath (Join-Path $models 'conduit.json') -Raw | ConvertFrom-Json
    Assert-VisualTest ($conduit.handler[0].variables[0].Contains('state.Active')) 'Bedrock saved activation was replaced'
    $null = Set-SharedBlockModels $root $assetDir java

    # Legacy names need an alias only when their original definition is absent.
    Ensure-LegacyChainModel $root
    $chain = Join-Path $root 'resources/BlenderEEVEE/assets/minecraft/blockstates/chain.json'
    Assert-VisualTest (-not (Test-Path -LiteralPath $chain)) 'Unknown first-run resources must not receive an unverified chain alias'
    $modern = Join-Path $root 'resources/base_resource_pack/assets/minecraft/blockstates/iron_chain.json'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $modern) | Out-Null
    [IO.File]::WriteAllText($modern,'{"variants":{"axis=x":{"model":"minecraft:block/custom_iron_chain","x":45}}}')
    Ensure-LegacyChainModel $root
    $doc = Get-Content -LiteralPath $chain -Raw | ConvertFrom-Json
    Assert-VisualTest ($doc.variants.'axis=x'.model -eq 'minecraft:block/custom_iron_chain') 'Modern definition was not retained'
    Assert-VisualTest ($doc.variants.'axis=x'.x -eq 45) 'Modern rotations were replaced'
    [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $modern) 'chain.json'),'{}')
    Ensure-LegacyChainModel $root
    Assert-VisualTest (-not (Test-Path -LiteralPath $chain)) 'Alias overrides a legacy definition'
    [IO.File]::WriteAllText($chain,'{"variants":{"axis=y":{"model":"custom:chain"}}}')
    $customChain = [IO.File]::ReadAllText($chain)
    Ensure-LegacyChainModel $root
    Assert-VisualTest ([IO.File]::ReadAllText($chain) -eq $customChain) 'Custom alias was overwritten'

    # A cached portal must be a decodable PNG, not merely an existing path.
    # Custom portal images remain intact; invalid files and directories are
    # reported without overwriting anything or unexpectedly using the network.
    Add-Type -AssemblyName System.Drawing
    $portal = Join-Path (Get-MiExExporterPackRoot $root) 'assets/minecraft/textures/block/end_portal.png'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $portal) | Out-Null
    $portalImage = [Drawing.Bitmap]::new(16,16)
    try { $portalImage.Save($portal,[Drawing.Imaging.ImageFormat]::Png) } finally { $portalImage.Dispose() }
    $portalHash = (Get-FileHash -LiteralPath $portal -Algorithm SHA256).Hash
    Ensure-BedrockPortalTexture $root java
    Assert-VisualTest ((Get-FileHash -LiteralPath $portal -Algorithm SHA256).Hash -eq $portalHash) 'Valid custom portal PNG changed'
    [IO.File]::WriteAllText($portal,'truncated portal fixture')
    $badPortalHash = (Get-FileHash -LiteralPath $portal -Algorithm SHA256).Hash
    $portalRejected = $false
    try { Ensure-BedrockPortalTexture $root java } catch { $portalRejected = $_.Exception.Message -like '*End portal texture*valid PNG*' }
    Assert-VisualTest $portalRejected 'Corrupt existing portal image was accepted or downloaded over'
    Assert-VisualTest ((Get-FileHash -LiteralPath $portal -Algorithm SHA256).Hash -eq $badPortalHash) 'Corrupt portal file was modified'
    Remove-Item -LiteralPath $portal -Force
    New-Item -ItemType Directory -Path $portal | Out-Null
    $portalRejected = $false
    try { Ensure-BedrockPortalTexture $root java } catch { $portalRejected = $_.Exception.Message -like '*End portal texture*valid PNG*' }
    Assert-VisualTest ($portalRejected -and (Test-Path -LiteralPath $portal -PathType Container)) 'Portal directory was overwritten or accepted'
    Remove-Item -LiteralPath $portal -Recurse -Force

    # A synthetic, hash-verified client exercises extraction without game art
    # or network access. All sixteen entries are real 64x64 PNG files.
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $original = Read-JavaBedManifest (Join-Path $assetDir 'Java_Bed_Textures.json')
    $fixture = Join-Path $root 'fixtures'
    New-Item -ItemType Directory -Force -Path $fixture | Out-Null
    $jar = Join-Path $root 'client-fixture.jar'
    $zip = [IO.Compression.ZipFile]::Open($jar, [IO.Compression.ZipArchiveMode]::Create)
    $entries = @()
    try {
        $index = 0
        foreach($entry in $original.textures) {
            $png = Join-Path $fixture $entry.file
            $bitmap = [Drawing.Bitmap]::new(64,64)
            try {
                $graphics = [Drawing.Graphics]::FromImage($bitmap)
                try { $graphics.Clear([Drawing.Color]::FromArgb(255,($index*13)%256,($index*29)%256,($index*41)%256)) }
                finally { $graphics.Dispose() }
                $bitmap.Save($png,[Drawing.Imaging.ImageFormat]::Png)
            } finally { $bitmap.Dispose() }
            $null = [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$png,('assets/minecraft/textures/entity/bed/'+$entry.file))
            $entries += @{file=$entry.file; sha256=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLowerInvariant()}
            $index++
        }
    } finally { $zip.Dispose() }
    $jarHash = (Get-FileHash -LiteralPath $jar -Algorithm SHA1).Hash.ToLowerInvariant()
    $manifest = @{version='26.1.2'; client_sha1=$jarHash; client_url=('https://piston-data.mojang.com/v1/objects/'+$jarHash+'/client.jar'); textures=$entries}
    $manifestPath = Join-Path $root 'fixture-manifest.json'
    [IO.File]::WriteAllText($manifestPath,($manifest | ConvertTo-Json -Depth 6))
    $bedDir = Join-Path $root 'resources/BlenderEEVEE/assets/minecraft/textures/entity/bed'
    $baseBedDir = Join-Path $root 'resources/base_resource_pack/assets/minecraft/textures/entity/bed'
    New-Item -ItemType Directory -Force -Path $bedDir,$baseBedDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $fixture 'white.png') -Destination (Join-Path $bedDir 'light_gray.png')
    $customHash = (Get-FileHash -LiteralPath (Join-Path $bedDir 'light_gray.png')).Hash
    Copy-Item -LiteralPath (Join-Path $fixture 'red.png') -Destination (Join-Path $baseBedDir 'red.png')
    Ensure-JavaBedTextures $root $manifestPath $jar
    Assert-VisualTest (@(Get-ChildItem -LiteralPath $bedDir -Filter '*.png').Count -eq 15) 'Wrong fallback atlas count'
    foreach($entry in $entries) {
        if($entry.file -in @('red.png','light_gray.png')) { continue }
        Assert-VisualTest ((Get-FileHash -LiteralPath (Join-Path $bedDir $entry.file) -Algorithm SHA256).Hash.ToLowerInvariant() -eq $entry.sha256) 'Atlas bytes changed'
    }
    Ensure-JavaBedTextures $root $manifestPath 'unavailable-client.jar'
    Assert-VisualTest ((Get-FileHash -LiteralPath (Join-Path $bedDir 'light_gray.png')).Hash -eq $customHash) 'Custom atlas changed'
    Assert-VisualTest ((Get-FileHash -LiteralPath $jar -Algorithm SHA1).Hash.ToLowerInvariant() -eq $jarHash) 'Source client was modified'
    # Existing atlas paths are not proof that the images can be decoded.
    # Fail before publication, retaining corrupt/custom source bytes for repair.
    foreach($invalidPath in @((Join-Path $bedDir 'white.png'),(Join-Path $baseBedDir 'red.png'))) {
        $saved = [IO.File]::ReadAllBytes($invalidPath)
        [IO.File]::WriteAllText($invalidPath, 'truncated PNG fixture')
        $invalidHash = (Get-FileHash -LiteralPath $invalidPath).Hash
        $rejected = $false
        try { Ensure-JavaBedTextures $root $manifestPath 'unavailable-client.jar' }
        catch { $rejected = $_.Exception.Message -like '*Java bed atlas*' }
        Assert-VisualTest $rejected 'Corrupt existing Java bed atlas was silently accepted'
        Assert-VisualTest ((Get-FileHash -LiteralPath $invalidPath).Hash -eq $invalidHash) 'Invalid custom/source atlas was overwritten'
        [IO.File]::WriteAllBytes($invalidPath,$saved)
    }
    $hdPath = Join-Path $bedDir 'light_gray.png'
    $bitmap = [Drawing.Bitmap]::new(128,128)
    try { $bitmap.Save($hdPath,[Drawing.Imaging.ImageFormat]::Png) } finally { $bitmap.Dispose() }
    $hdHash = (Get-FileHash -LiteralPath $hdPath).Hash
    Ensure-JavaBedTextures $root $manifestPath 'unavailable-client.jar'
    Assert-VisualTest ((Get-FileHash -LiteralPath $hdPath).Hash -eq $hdHash) 'Valid HD custom atlas changed'
    $lowerPriority = Join-Path $baseBedDir 'white.png'
    [IO.File]::WriteAllText($lowerPriority,'unused lower-priority image')
    Ensure-JavaBedTextures $root $manifestPath 'unavailable-client.jar'
    Remove-Item -LiteralPath $lowerPriority
    foreach($color in @('blue','red')) {
        $blockedPath = Join-Path $bedDir ($color + '.png')
        $saved = $null
        if(Test-Path -LiteralPath $blockedPath -PathType Leaf) {
            $saved = [IO.File]::ReadAllBytes($blockedPath)
            Remove-Item -LiteralPath $blockedPath
        }
        New-Item -ItemType Directory -Path $blockedPath | Out-Null
        $rejected = $false
        try { Ensure-JavaBedTextures $root $manifestPath $jar }
        catch { $rejected = $_.Exception.Message -like '*Java bed atlas path is not a file*' }
        Assert-VisualTest $rejected 'An atlas directory was treated as a valid image destination or hid the base atlas'
        Assert-VisualTest (Test-Path -LiteralPath $blockedPath -PathType Container) 'Existing directory was changed'
        Remove-Item -LiteralPath $blockedPath
        if($null -ne $saved) { [IO.File]::WriteAllBytes($blockedPath,$saved) }
    }
    Remove-ManagedJavaBedTextures $root $manifestPath
    Assert-VisualTest (@(Get-ChildItem -LiteralPath $bedDir -Filter '*.png').Count -eq 1) 'Managed cleanup removed custom data or retained managed images'

    # Production uses different physical folders for each edition. Loading
    # Bedrock must not remove/reinterpret an existing Java project's atlases,
    # and the previous shared pack remains intact for older project links.
    $isolated = Join-Path $root 'isolated'
    $legacyBed = Join-Path $isolated 'resources/BlenderEEVEE/assets/minecraft/textures/entity/bed'
    New-Item -ItemType Directory -Force -Path $legacyBed | Out-Null
    Copy-Item -LiteralPath (Join-Path $fixture 'red.png') -Destination (Join-Path $legacyBed 'white.png')
    $legacyHash = (Get-FileHash -LiteralPath (Join-Path $legacyBed 'white.png')).Hash
    $script:miexExporterPackName = 'BlenderEEVEE_java'
    $null = Set-SharedBlockModels $isolated $assetDir java
    Ensure-JavaBedTextures $isolated $manifestPath $jar
    $javaBed = Join-Path (Get-MiExExporterPackRoot $isolated) 'assets/minecraft/textures/entity/bed/white.png'
    $javaHash = (Get-FileHash -LiteralPath $javaBed).Hash
    $script:miexExporterPackName = 'BlenderEEVEE_bedrock'
    $null = Set-SharedBlockModels $isolated $assetDir bedrock
    Remove-ManagedJavaBedTextures $isolated $manifestPath
    $otherBed = Join-Path (Get-MiExExporterPackRoot $isolated) 'assets/minecraft/textures/entity/bed'
    New-Item -ItemType Directory -Force -Path $otherBed | Out-Null
    Copy-Item -LiteralPath (Join-Path $fixture 'blue.png') -Destination (Join-Path $otherBed 'white.png')
    Assert-VisualTest ((Get-FileHash -LiteralPath $javaBed).Hash -eq $javaHash) 'Edition switching changed a Java project atlas'
    Assert-VisualTest ((Get-FileHash -LiteralPath (Join-Path $legacyBed 'white.png')).Hash -eq $legacyHash) 'Legacy project dependency changed'
    $script:miexExporterPackName = 'BlenderEEVEE'

    $badRoot = Join-Path $root 'bad'
    $manifest.textures[5].sha256 = '0' * 64
    [IO.File]::WriteAllText($manifestPath,($manifest | ConvertTo-Json -Depth 6))
    $failed = $false
    try { Ensure-JavaBedTextures $badRoot $manifestPath $jar } catch { $failed = $true }
    Assert-VisualTest $failed 'Corrupt texture bytes were accepted'
    $badDir = Join-Path $badRoot 'resources/BlenderEEVEE/assets/minecraft/textures/entity/bed'
    Assert-VisualTest (@(Get-ChildItem -LiteralPath $badDir -File).Count -eq 0) 'Failed extraction published partial atlases or left temporary files'
    Write-Host 'Shared Java/Bedrock models, edition switching, chain compatibility and atomic Java atlas fallbacks passed.'
} finally {
    $script:miexExporterPackName = 'BlenderEEVEE'
    Remove-Item Function:\Invoke-WebRequest
    $absolute = [IO.Path]::GetFullPath($root)
    $temp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if(-not $absolute.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase) -or
       (Split-Path -Leaf $absolute) -notmatch '^miex-java-assets-[0-9a-f]{32}$') { throw 'Unexpected test cleanup target' }
    if(Test-Path -LiteralPath $absolute) { Remove-Item -LiteralPath $absolute -Recurse -Force }
}
