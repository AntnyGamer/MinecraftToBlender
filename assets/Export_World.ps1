# Minecraft to Blender v1: full-detail Java/Bedrock world folder to Blender USD.
# The source save remains untouched; no missing-block substitution is performed by this script.
# MiEx itself may have limitations and this workflow does not certify pixel-for-pixel parity.
[CmdletBinding()]
param(
    [string]$WorldZip = '',
    [string]$WorldPath = '',
    [ValidateSet('bedrock','java')][string]$Edition = 'bedrock',
    [ValidateRange(16,8192)][int]$Size = 256,
    [int]$CenterX = 0,
    [int]$CenterZ = 0,
    [ValidateRange(-256,2048)][int]$MinY = -64,
    [ValidateRange(-256,2048)][int]$MaxY = 319,
    [ValidatePattern('^[a-zA-Z][a-zA-Z0-9_]{0,60}$')][string]$ExportName = 'Bedrock_World',
    [switch]$CompactUSD,
    [switch]$UseWorldResourcePacks
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$work = Join-Path $base 'MiEx_Work'
$worldDir = Join-Path $work 'world_source'
$chunkSize = 16
$enableGeometrySubsets = $false
$enableFaceOptimization = $false
$fillWorldBorders = $true
$finalExportDir = Join-Path (Join-Path $work 'exports') $ExportName
# Always export into a unique, empty directory. Never let leftover chunk files
# from a previous run hide missing geometry in a failed or partial export.
$exportDir = Join-Path (Join-Path $work 'exports') ('.staging_' + $ExportName + '_' + [guid]::NewGuid().ToString('N'))
$exportFile = "$ExportName.usd"
if($MinY -gt $MaxY) { throw 'MinY must be less than or equal to MaxY.' }
if(($Size % 16) -ne 0) { throw 'Size must be a multiple of 16 (Minecraft chunk width).' }
$minX = $CenterX - [int][math]::Floor($Size/2)
$minZ = $CenterZ - [int][math]::Floor($Size/2)
$maxX = $minX + $Size - 1
$maxZ = $minZ + $Size - 1
Write-Host ('Minecraft to Blender v1: compatibility-first export; face merging, geometry-subset batching and point instancing disabled.') -ForegroundColor Cyan
Write-Host ("Region: X=$minX..$maxX Z=$minZ..$maxZ Y=$MinY..$MaxY")
$miexDir = Join-Path $work 'miex'
$jar = Join-Path $miexDir 'MiEx.jar'
$releaseUrl = 'https://github.com/BramStoutProductions/MiEx/releases/download/v2.0.0.experimental-34/MiEx.jar'
$releaseSha256 = 'e4951d44116fd2d90c14f52643b7cd66ddd7f64ac108b8a16705b379672de707'

function Get-WebFile([string]$url,[string]$dest) {
    $folder = Split-Path -Parent $dest
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    Write-Host "Downloading $url"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest
    if(-not (Test-Path -LiteralPath $dest)) { throw "Missing downloaded file: $dest" }
}
function Test-Hash([string]$path,[string]$expected) {
    $found = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if($found -ne $expected) {throw "SHA256 mismatch for $path. Actual: $found / expected: $expected"}
    Write-Host "Verified SHA256: $path" -ForegroundColor Green
}
function Ensure-PinnedFile([string]$url,[string]$dest,[string]$expected) {
    # A previously interrupted download or modified cache must not silently
    # change the models and materials used in later conversions.
    if(Test-Path -LiteralPath $dest) {
        $actual = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
        if($actual -eq $expected) { return }
        Write-Host "Cached resource changed; fetching the pinned original: $dest" -ForegroundColor Yellow
    }
    Get-WebFile $url $dest
    Test-Hash $dest $expected
}
function Start-CapturedProcess([string]$exe,[string]$arguments,[string]$folder,[string]$stdout,[string]$stderr) {
    # System.Diagnostics.Process exposes a reliable ExitCode on Windows
    # PowerShell 5.1, unlike Start-Process -PassThru on some Windows builds.
    # Stream each output pipe asynchronously to disk, without buffering a
    # potentially huge MiEx log in memory or involving CMD path expansion.
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $exe
    $info.Arguments = $arguments
    $info.WorkingDirectory = $folder
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    $outFile = [System.IO.File]::Open($stdout, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
    try {
        $errFile = [System.IO.File]::Open($stderr, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
        try {
            if(-not $process.Start()) { throw "Could not start $exe" }
            $outTask = $process.StandardOutput.BaseStream.CopyToAsync($outFile)
            $errTask = $process.StandardError.BaseStream.CopyToAsync($errFile)
            return @{ Process=$process; OutTask=$outTask; ErrTask=$errTask; OutFile=$outFile; ErrFile=$errFile }
        } catch { $errFile.Dispose(); throw }
    } catch { $outFile.Dispose(); $process.Dispose(); throw }
}
function Finish-CapturedProcess($capture) {
    try {
        $capture.Process.WaitForExit()
        [System.Threading.Tasks.Task]::WaitAll([System.Threading.Tasks.Task[]]@($capture.OutTask, $capture.ErrTask))
        return [int]$capture.Process.ExitCode
    } finally {
        $capture.OutFile.Dispose()
        $capture.ErrFile.Dispose()
        $capture.Process.Dispose()
    }
}
function Read-MiExDiagnostics([string]$logPath) {
    # The getWorld result may include almost a megabyte of player NBT, which
    # Windows PowerShell 5.1 cannot reliably convert into a PSObject. Read
    # only the small fields needed here, leaving raw JSON in the MiEx log.
    $result = @{ WorldPath=''; Reported=$false; Returned=0; Readable=0 }
    if(-not (Test-Path -LiteralPath $logPath)) { return $result }
    foreach($line in [System.IO.File]::ReadLines($logPath)) {
        if(-not $line.StartsWith('[COMMAND] ')) { continue }
        if(-not $line.Substring(10, [math]::Min($line.Length - 10, 96)).Contains('"status":"success"')) { continue }
        if($line.Contains('"world"')) {
            $match = [regex]::Match($line, '"world"\s*:\s*\{\s*"path"\s*:\s*"(?<path>(?:\\.|[^"\\])*)"')
            if($match.Success) {
                # Decode the isolated JSON string; do not deserialize player NBT.
                $smallJson = '{"path":"' + $match.Groups['path'].Value + '"}'
                $result.WorldPath = [string](($smallJson | ConvertFrom-Json).path)
            }
        }
        if($line.Contains('"chunks"')) {
            # Chunk entries are MiEx's own flat records; count only the keys
            # required for diagnosis. The returned heightmaps are large, so
            # ConvertFrom-Json of the entire response is unnecessary.
            $result.Reported = $true
            $result.Returned = [regex]::Matches($line, '"chunkX"\s*:').Count
            $result.Readable = [regex]::Matches($line, '"layerCount"\s*:\s*[1-9][0-9]*').Count
        }
    }
    return $result
}
function Test-UnsupportedBedrockChunk([string]$stdout,[string]$stderr) {
    foreach($path in @($stdout, $stderr)) {
        if((Test-Path -LiteralPath $path) -and (Select-String -LiteralPath $path -Pattern 'Chunk section format not supported' -Quiet -ErrorAction SilentlyContinue)) {
            return $true
        }
    }
    return $false
}
function Publish-Export([string]$stage,[string]$destination) {
    # Preserve completed Blender projects when replacing generated USD chunks.
    $backup = $destination + '.previous_' + [guid]::NewGuid().ToString('N')
    $hadPrevious = Test-Path -LiteralPath $destination
    if($hadPrevious) { Move-Item -LiteralPath $destination -Destination $backup -ErrorAction Stop }
    $published = $false
    $movedProjects = @()
    try {
        Move-Item -LiteralPath $stage -Destination $destination -ErrorAction Stop
        $published = $true
        if($hadPrevious) {
            foreach($project in (Get-ChildItem -LiteralPath $backup -File -ErrorAction Stop | Where-Object { $_.Name -match '\.blend[0-9]*$' })) {
                $target = Join-Path $destination $project.Name
                if(Test-Path -LiteralPath $target) { throw "New export conflicts with saved Blender project: $target" }
                Move-Item -LiteralPath $project.FullName -Destination $target -ErrorAction Stop
                $movedProjects += $project.Name
            }
        }
    } catch {
        $failure = $_
        if($published) {
            foreach($name in $movedProjects) {
                Move-Item -LiteralPath (Join-Path $destination $name) -Destination $backup -ErrorAction Stop
            }
            Remove-Item -LiteralPath $destination -Recurse -Force -ErrorAction Stop
        }
        if($hadPrevious) { Move-Item -LiteralPath $backup -Destination $destination -ErrorAction Stop }
        throw $failure
    }
    if($hadPrevious) {
        try { Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction Stop }
        catch { Write-Warning ("Previous export backup could not be removed: " + $backup) }
    }
}
function Test-ChunkTerrainGeometry([string]$folder) {
    # MiEx's ASCII chunk layers contain nonempty faceVertexCounts for mesh
    # geometry. A directory full of empty USD layer shells is not terrain.
    # Read in bounded pieces: face arrays may occupy very long USD lines.
    $files = @(Get-ChildItem -LiteralPath $folder -Filter '*.usd' -File -Recurse -ErrorAction Stop)
    $pattern = 'faceVertexCounts\s*=\s*\[\s*[1-9]'
    $buffer = New-Object char[] 65536
    foreach($file in $files) {
        $reader = [System.IO.File]::OpenText($file.FullName)
        try {
            $tail = ''
            while(($n = $reader.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $chunk = $tail + [string]::new($buffer, 0, $n)
                if($chunk -match $pattern) { return $true }
                $tail = $chunk.Substring([Math]::Max(0, $chunk.Length - 64))
            }
        } finally { $reader.Dispose() }
    }
    return $false
}
function Assert-SafeResourcePackArchives([string]$worldFolder) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach($name in @('resource_packs', 'behavior_packs', 'datapacks')) {
        $folder = Join-Path $worldFolder $name
        if(-not (Test-Path -LiteralPath $folder -PathType Container)) { continue }
        foreach($archive in (Get-ChildItem -LiteralPath $folder -File -Recurse -ErrorAction Stop | Where-Object { $_.Extension -in @('.zip', '.jar') })) {
            $zip = [System.IO.Compression.ZipFile]::OpenRead($archive.FullName)
            try {
                foreach($entry in $zip.Entries) {
                    $entryPath = $entry.FullName.Replace('\', '/')
                    if($entryPath.StartsWith('/') -or $entryPath -match '^[A-Za-z]:' -or
                       $entryPath -match '(^|/)\.\.(/|$)') {
                        throw "Unsafe resource-pack archive entry in $($archive.FullName): $($entry.FullName)"
                    }
                }
            } finally { $zip.Dispose() }
        }
    }
}
function Abort([string]$reason) {throw $reason}

try {
    Write-Host ("$Edition world folder -> MiEx -> Blender USD") -ForegroundColor Cyan
    if(-not (Get-Command java -ErrorAction SilentlyContinue)) {
        Abort 'Java is not installed. Install Java 21 (or a compatible JDK), then rerun this script.'
    }
    # Check BEFORE creating the working directories. An unsafe workspace
    # must not create AppTools files in the original Minecraft save.
    if($WorldPath) {
        $sourceSafe = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $WorldPath -ErrorAction Stop).Path).TrimEnd('\')
        $toolSafe = [System.IO.Path]::GetFullPath($base).TrimEnd('\')
        if($sourceSafe.Equals($toolSafe, [StringComparison]::OrdinalIgnoreCase) -or
           $sourceSafe.StartsWith(($toolSafe + '\'), [StringComparison]::OrdinalIgnoreCase) -or
           $toolSafe.StartsWith(($sourceSafe + '\'), [StringComparison]::OrdinalIgnoreCase)) {
            Abort 'Converter workspace overlaps the selected world folder. Move the workspace outside the Minecraft save.'
        }
    }
    New-Item -ItemType Directory -Force -Path $work,$exportDir,$miexDir | Out-Null

    if(-not $WorldZip -and -not $WorldPath) {
        Add-Type -AssemblyName System.Windows.Forms
        $dlg = New-Object System.Windows.Forms.OpenFileDialog
        $dlg.Title = 'Select a Minecraft Bedrock world ZIP (with level.dat and db folder)'
        $dlg.Filter = 'ZIP files (*.zip)|*.zip|All files (*.*)|*.*'
        if($dlg.ShowDialog() -ne 'OK') { Abort 'No world ZIP was selected.' }
        $WorldZip = $dlg.FileName
    }
    if(-not $WorldPath) {
    $WorldZip = (Resolve-Path -LiteralPath $WorldZip).Path
    Write-Host "Selected file: $WorldZip"
    # Confirm the ZIP is a Bedrock world rather than a previously exported model.
    # GLB export archives are not Minecraft world saves, even if their name contains "Source".
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $hasLevelDat = $false
    $hasDb = $false
    $hasGlb = $false
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($WorldZip)
        try {
            foreach($entry in $archive.Entries) {
                $name = ($entry.FullName -replace '\\','/').ToLowerInvariant()
                if($name -match '(^|/)level\.dat$') { $hasLevelDat = $true }
                if($name -match '(^|/)db/[^/]+\.(ldb|sst|log)$' -or $name -match '(^|/)db/current$') { $hasDb = $true }
                if($name.EndsWith('.glb')) { $hasGlb = $true }
            }
        } finally { $archive.Dispose() }
    } catch { Abort "Not a readable ZIP file: $WorldZip" }
    if(-not ($hasLevelDat -and $hasDb)) {
        if($hasGlb) {
            Abort 'Selected archive contains GLB model files, not a Bedrock world. Select an original Bedrock world ZIP.'
        }
        Abort 'Selected ZIP is not a Bedrock world. Its contents must include level.dat and a db directory.'
    }
    # World-specific SHA256 is calculated at runtime; public users can supply any Bedrock save.
    $actualWorldHash = (Get-FileHash -LiteralPath $WorldZip -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "Bedrock world ZIP SHA256: $actualWorldHash" -ForegroundColor Green

    $marker = Join-Path $worldDir '.verified_world_sha256'
    $doExtract = $true
    if((Test-Path -LiteralPath $marker) -and ((Get-Content -LiteralPath $marker -Raw).Trim() -eq $actualWorldHash)) {
        $cachedLevel = Get-ChildItem -LiteralPath $worldDir -Recurse -Filter 'level.dat' -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if($cachedLevel -and (Test-Path -LiteralPath (Join-Path $cachedLevel.DirectoryName 'db'))) {
            $doExtract = $false
            Write-Host 'Reusing verified, extracted Bedrock save (no redundant ZIP extraction).' -ForegroundColor Green
        }
    }
    if($doExtract) {
        if(Test-Path -LiteralPath $worldDir) {Remove-Item -LiteralPath $worldDir -Recurse -Force}
        New-Item -ItemType Directory -Path $worldDir -Force | Out-Null
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($WorldZip,$worldDir)
        Set-Content -LiteralPath $marker -Value $actualWorldHash -Encoding ASCII
    }
    $level = Get-ChildItem -LiteralPath $worldDir -Recurse -Filter level.dat -File | Select-Object -First 1
    if(-not $level) {Abort 'No Bedrock level.dat file found after extraction.'}
    $worldPath = Split-Path -Parent $level.FullName
    if(-not (Test-Path -LiteralPath (Join-Path $worldPath 'db'))) {Abort 'Bedrock world database folder is missing.'}
    Write-Host "Verified Bedrock world directory: $worldPath" -ForegroundColor Green
    } else {
        # Users select a local world in the GUI. Snapshot the save read-only;
        # MiEx is never given the original game directory. No ZIP is needed.
        $source = (Resolve-Path -LiteralPath $WorldPath -ErrorAction Stop).Path
        if(-not (Test-Path -LiteralPath (Join-Path $source 'level.dat') -PathType Leaf)) {
            Abort 'Selected world has no level.dat.'
        }
        if($Edition -eq 'bedrock' -and -not (Test-Path -LiteralPath (Join-Path $source 'db') -PathType Container)) {
            Abort 'Selected Bedrock world has no LevelDB db folder.'
        }
        if($Edition -eq 'java' -and -not ((Test-Path -LiteralPath (Join-Path $source 'region') -PathType Container) -or (Test-Path -LiteralPath (Join-Path $source 'dimensions') -PathType Container))) {
            Abort 'Selected Java world has no region/dimensions folder.'
        }
        if($source.StartsWith($work, [System.StringComparison]::OrdinalIgnoreCase) -or $work.StartsWith(($source + [IO.Path]::DirectorySeparatorChar), [System.StringComparison]::OrdinalIgnoreCase)) {
            Abort 'The world save and converter workspace cannot contain one another.'
        }
        # Source game worlds can be updated at any time. A fresh snapshot avoids
        # using stale data from a prior export, even for identically named saves.
        $stage = Join-Path $work 'world_source_staging'
        if(Test-Path -LiteralPath $stage) {Remove-Item -LiteralPath $stage -Recurse -Force}
        New-Item -ItemType Directory -Force -Path $stage | Out-Null
        Write-Host "Copying a safe, read-only snapshot of the $Edition world..." -ForegroundColor Cyan
        try {
            foreach($entry in (Get-ChildItem -LiteralPath $source -Force -ErrorAction Stop)) {
                Copy-Item -LiteralPath $entry.FullName -Destination $stage -Recurse -Force -ErrorAction Stop
            }
            if(-not (Test-Path -LiteralPath (Join-Path $stage 'level.dat'))) {
                Abort 'World snapshot is incomplete: level.dat missing.'
            }
            if($Edition -eq 'bedrock' -and -not (Test-Path -LiteralPath (Join-Path $stage 'db'))) {
                Abort 'World snapshot is incomplete: LevelDB db folder missing.'
            }
            if(Test-Path -LiteralPath $worldDir) {Remove-Item -LiteralPath $worldDir -Recurse -Force}
            Move-Item -LiteralPath $stage -Destination $worldDir -ErrorAction Stop
        } catch {
            if(Test-Path -LiteralPath $stage) {Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue}
            throw
        }
        $worldPath = $worldDir
        $actualWorldHash = (Get-FileHash -LiteralPath (Join-Path $worldPath 'level.dat') -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host "Snapshot ready; world metadata SHA256: $actualWorldHash" -ForegroundColor Green
    }

    if($UseWorldResourcePacks) { Assert-SafeResourcePackArchives $worldPath }

    if(-not (Test-Path -LiteralPath $jar)) {Get-WebFile $releaseUrl $jar}
    try {Test-Hash $jar $releaseSha256}
    catch {Remove-Item -LiteralPath $jar -Force -ErrorAction SilentlyContinue;Get-WebFile $releaseUrl $jar;Test-Hash $jar $releaseSha256}

    # Apply the fourth-vertex color-check fix in a NEW JAR, not
    # the checksummed official original. This must succeed before
    # export; do not silently fall back to a different implementation.
    $runJar = $jar
    if($enableFaceOptimization) {
        $runJar = Join-Path $miexDir 'MiEx_Optimized.jar'
        $patcherClass = Join-Path $base 'PatchMiExFaceOptimizer.class'
        $patcherHelper = Join-Path $base 'PatchMiExFaceOptimizer$ClassView.class'
        if(-not (Test-Path -LiteralPath $patcherClass) -or -not (Test-Path -LiteralPath $patcherHelper)) {
            Abort 'Missing Java patcher class files. Extract the entire release ZIP before running.'
        }
        $patchMarker = Join-Path $miexDir 'MiEx_Optimized.sha256.txt'
        # Include the patcher itself in the cache key, not just the resulting JAR.
        # A new patch implementation must not silently reuse an older patched JAR.
        $patcherHash = ((Get-FileHash -LiteralPath $patcherClass -Algorithm SHA256).Hash.ToLowerInvariant() + ':' + 
                        (Get-FileHash -LiteralPath $patcherHelper -Algorithm SHA256).Hash.ToLowerInvariant())
        $patchFresh = $false
        if((Test-Path -LiteralPath $runJar) -and (Test-Path -LiteralPath $patchMarker)) {
            $savedHash = (Get-Content -LiteralPath $patchMarker -Raw).Trim().ToLowerInvariant()
            $jarHash = (Get-FileHash -LiteralPath $runJar -Algorithm SHA256).Hash.ToLowerInvariant()
            $patchFresh = ($savedHash -eq ($jarHash + ':' + $patcherHash))
        }
        if(-not $patchFresh) {
            $patchLog = Join-Path $work 'Face_Patch_Log.txt'
            $javaExe = (Get-Command java.exe -ErrorAction Stop).Source
            $patchArgs = '-cp "{0}" PatchMiExFaceOptimizer "{1}" "{2}"' -f $base, $jar, $runJar
            $patchProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
            $patchProcessInfo.FileName = $javaExe
            $patchProcessInfo.Arguments = $patchArgs
            $patchProcessInfo.WorkingDirectory = $base
            $patchProcessInfo.UseShellExecute = $false
            $patchProcessInfo.CreateNoWindow = $true
            $patchProcessInfo.RedirectStandardOutput = $true
            $patchProcessInfo.RedirectStandardError = $true
            Write-Host 'Applying face optimizer patch to a separate JAR...' -ForegroundColor Cyan
            $patchProcess = New-Object System.Diagnostics.Process
            $patchProcess.StartInfo = $patchProcessInfo
            try {
                [void]$patchProcess.Start()
                $patchStdout = $patchProcess.StandardOutput.ReadToEnd()
                $patchStderr = $patchProcess.StandardError.ReadToEnd()
                $patchProcess.WaitForExit()
                $patchCode = $patchProcess.ExitCode
                [System.IO.File]::WriteAllText($patchLog, ($patchStdout + [Environment]::NewLine + $patchStderr), [System.Text.Encoding]::UTF8)
                if($patchStdout) { Write-Host $patchStdout.Trim() }
                if($patchStderr) { Write-Host $patchStderr.Trim() -ForegroundColor Yellow }
            } finally { $patchProcess.Dispose() }
            if($patchCode -ne 0 -or -not (Test-Path -LiteralPath $runJar)) {
                Abort "Face optimizer patch failed (exit code $patchCode). Original MiEx.jar remains intact. Details: $patchLog"
            }
            $optimizedSha = (Get-FileHash -LiteralPath $runJar -Algorithm SHA256).Hash.ToLowerInvariant()
            if($optimizedSha -eq $releaseSha256) {Abort 'Patched MiEx JAR is unexpectedly identical to the original. Refusing export.'}
            [System.IO.File]::WriteAllText($patchMarker, ($optimizedSha + ':' + $patcherHash + [Environment]::NewLine), [System.Text.Encoding]::ASCII)
            Write-Host ('Verified separate optimized JAR: ' + $optimizedSha) -ForegroundColor Green
        }else {
            Write-Host 'Reusing previously validated, checksummed patched MiEx JAR.' -ForegroundColor Green
        }
    }

    # Official MiEx example resource pack for Blender EEVEE materials only.
    # It does not contain custom block textures and is not the world's custom pack.
    $pinnedPackRevision = '631e9fc2fde8c749bf59d4c3495492e62a83ef6c'
    $packUrl = 'https://raw.githubusercontent.com/BramStoutProductions/MiEx/' + $pinnedPackRevision + '/extras/example_resource_packs/BlenderEEVEE/'
    $pinnedTemplates = @{
      'materials/minecraft/templates/json_base.json' = '33752fcc6b70201c4dc218a93d0e396f50ab8e23cc6807aebd79ae956ad24cb8'
      'materials/minecraft/templates/json_emission.json' = '72a10f283a9e258d0aa554e41c46bfdece1c741efa568deff19b41b3819f4b05'
      'materials/minecraft/templates/json_grass_block_side.json' = '2dea1f14004f91e27b73700ac42804daef776fbae9b655cf21abd35be6b56425'
      'materials/minecraft/templates/json_grass_block_snow.json' = 'adf937c0b3eb073f7ea4fc4e5a78887d83ff48bb9c71fd7d073d3ab179092228'
    }
    foreach($f in $pinnedTemplates.Keys) {
        $target = Join-Path $miexDir ('resources/BlenderEEVEE/' + $f)
        Ensure-PinnedFile ($packUrl + $f) $target $pinnedTemplates[$f]
    }
    # Generate the configurable working copy from an immutable, verified
    # upstream template each run. This prevents settings from drifting when
    # the user switches between Java and Bedrock worlds.
    $packConfigSource = Join-Path $miexDir 'miex_config_upstream.json'
    Ensure-PinnedFile ($packUrl + 'miex_config.json') $packConfigSource '88e8876c950a59ccf9d7992b4c965893d61561bc85d09f5583b7d8a7136a4372'
    $packConfigPath = Join-Path $miexDir 'resources/BlenderEEVEE/miex_config.json'
    $packConfig = Get-Content -LiteralPath $packConfigSource -Raw | ConvertFrom-Json
    $packConfig | Add-Member -MemberType NoteProperty -Name 'useGeometrySubsets' -Value $enableGeometrySubsets -Force
    # The existing MiEx USD already uses point instancers for these block types;
    # Disable individual-block point instancing until the corresponding Blender
    # geometry-node output is validated. Previously it imported as scattered points.
    $packConfig | Add-Member -MemberType NoteProperty -Name 'usePointInstancersForIndividualBlocks' -Value $false -Force
    $packConfig | Add-Member -MemberType NoteProperty -Name 'runFaceOptimiser' -Value $enableFaceOptimization -Force
    $packConfig | Add-Member -MemberType NoteProperty -Name 'runRaytracingOptimiser' -Value $false -Force
    $packConfig | Add-Member -MemberType NoteProperty -Name 'fillWorldBorders' -Value $fillWorldBorders -Force
    $outConfig = $packConfig | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($packConfigPath, $outConfig + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    $parsedConfig = Get-Content -LiteralPath $packConfigPath -Raw | ConvertFrom-Json
    if([bool]$parsedConfig.useGeometrySubsets -ne $enableGeometrySubsets -or [bool]$parsedConfig.usePointInstancersForIndividualBlocks -or [bool]$parsedConfig.runFaceOptimiser -ne $enableFaceOptimization -or [bool]$parsedConfig.runRaytracingOptimiser -or [bool]$parsedConfig.fillWorldBorders -ne $fillWorldBorders) {
        Abort 'MiEx exporter resource-pack configuration did not validate.'
    }
    Write-Host 'Applied reusable exporter configuration in BlenderEEVEE/miex_config.json.' -ForegroundColor Green
    $bedrockAssetHelper = Join-Path $base 'Bedrock_Assets.ps1'
    if(-not (Test-Path -LiteralPath $bedrockAssetHelper -PathType Leaf)) {
        Abort 'Bedrock asset helper is missing.'
    }
    . $bedrockAssetHelper
    $bedTextureManifest = Join-Path $base 'Bedrock_Bed_Textures.json'
    if($Edition -eq 'bedrock' -and -not $UseWorldResourcePacks) {
        Ensure-BedrockBedTextures $miexDir $bedTextureManifest
    } else {
        Remove-ManagedBedrockBedTextures $miexDir $bedTextureManifest
    }
    $blockOverrideDir = Join-Path $miexDir 'resources/BlenderEEVEE/builtins/minecraft/blockstates'
    $bedrockBlockOverrides = @{
        'Bedrock_Beds.json' = 'bed.json'
        'Bedrock_Shulkers.json' = 'shulker_box.json'
        'Bedrock_Signs.json' = 'sign.json'
        'Bedrock_Hanging_Signs.json' = 'hanging_sign.json'
    }
    if($Edition -eq 'bedrock') {
        New-Item -ItemType Directory -Force -Path $blockOverrideDir | Out-Null
        foreach($entry in $bedrockBlockOverrides.GetEnumerator()) {
            $source = Join-Path $base $entry.Key
            if(-not (Test-Path -LiteralPath $source -PathType Leaf)) {
                Abort ("Bedrock model override is missing: " + $source)
            }
            $parsed = Get-Content -LiteralPath $source -Raw | ConvertFrom-Json
            if(-not $parsed.blocks -or -not $parsed.handler) {
                Abort ("Bedrock model override did not validate: " + $source)
            }
            Copy-Item -LiteralPath $source -Destination (Join-Path $blockOverrideDir $entry.Value) -Force -ErrorAction Stop
        }
        Write-Host 'Enabled Bedrock-specific beds, shulker orientation, and legacy sign text models.' -ForegroundColor Green
    } else {
        # Remove any overrides created for an earlier Bedrock export in this workspace.
        foreach($name in $bedrockBlockOverrides.Values) {
            $target = Join-Path $blockOverrideDir $name
            if(Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force -ErrorAction Stop }
        }
    }
    $frameStateFolder = Join-Path $miexDir 'resources/BlenderEEVEE/assets/minecraft/blockstates'
    $frameOverridePath = Join-Path $miexDir 'resources/BlenderEEVEE/builtins/minecraft/entities/item_frame.json'
    if($Edition -eq 'bedrock') {
        # Bedrock item frames are both stored as blocks AND exported by MiEx as
        # entities. Their blockstate is intentionally empty: the real vanilla
        # frame geometry is generated by the separate entity model below.
        # This prevents the false missing-blockstate error during neighboring
        # block occlusion checks without inventing a placeholder 3D frame.
        New-Item -ItemType Directory -Force -Path $frameStateFolder | Out-Null
        foreach($frameStateName in @('frame', 'glow_frame')) {
            $frameStatePath = Join-Path $frameStateFolder ($frameStateName + '.json')
            [System.IO.File]::WriteAllText($frameStatePath, '{"variants":{}}' + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        }
        # MiEx's pinned built-in frame entity incorrectly checks the block context
        # for a stored item (thisBlock), and uses Java Item.id even for Bedrock
        # Item.Name entries. Correct these narrowly using the official frame model.
        # The item model geometry and textures themselves are not replaced.
        $frameSource = Join-Path $miexDir 'item_frame_upstream.json'
        Ensure-PinnedFile 'https://raw.githubusercontent.com/BramStoutProductions/MiEx/631e9fc2fde8c749bf59d4c3495492e62a83ef6c/builtin_files/base_resource_pack/builtins/minecraft/entities/item_frame.json' $frameSource 'd554356c34cf09691bca790c35c1a070532d2bf9e25ca35aa3db7612153bfe4d'
        $frameRaw = [System.IO.File]::ReadAllText($frameSource)
        $frameOldCondition = '(thisBlock.state.Item != null)'
        $frameOldId = '"id": "thisEntity.state.Item.id"'
        if(($frameRaw.Split([string[]]@($frameOldCondition), [System.StringSplitOptions]::None).Length - 1) -ne 2 -or
           ($frameRaw.Split([string[]]@($frameOldId), [System.StringSplitOptions]::None).Length - 1) -ne 1) {
            Abort 'Pinned MiEx item-frame definition differs from the expected version. Refusing an unverified correction.'
        }
        $frameFixed = $frameRaw.Replace($frameOldCondition, '(thisEntity.state.Item != null)')
        $frameFixed = $frameFixed.Replace($frameOldId, '"id": "thisEntity.state.Item.id != null ? thisEntity.state.Item.id : thisEntity.state.Item.Name"')
        $frameObj = $frameFixed | ConvertFrom-Json
        if(($frameObj.entities -notcontains 'minecraft:item_frame') -or
           ($frameObj.entities -notcontains 'minecraft:glow_item_frame')) {
            Abort 'Pinned frame model does not declare the expected entity identifiers.'
        }
        # Bedrock's integer block entity X/Z refer to the block origin, whereas
        # the entity frame model expects the horizontal center of that block.
        $frameObj | Add-Member -MemberType NoteProperty -Name posX -Value 'thisEntity.state.x + 0.5' -Force
        $frameObj | Add-Member -MemberType NoteProperty -Name posZ -Value 'thisEntity.state.z + 0.5' -Force
        $frameOverrideDir = Join-Path $miexDir 'resources/BlenderEEVEE/builtins/minecraft/entities'
        New-Item -ItemType Directory -Force -Path $frameOverrideDir | Out-Null
        $frameOutput = $frameObj | ConvertTo-Json -Depth 80
        $frameReparsed = $frameOutput | ConvertFrom-Json
        if($frameReparsed.posX -ne 'thisEntity.state.x + 0.5' -or
           $frameReparsed.posZ -ne 'thisEntity.state.z + 0.5') {
            Abort 'Frame entity model override failed validation.'
        }
        [System.IO.File]::WriteAllText($frameOverridePath, $frameOutput + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host 'Installed Bedrock frame and glow-frame blockstates and corrected entity item models.' -ForegroundColor Green

    } else {
        # A Java export must not inherit Bedrock-specific frame overrides
        # from an earlier export in this workspace.
        foreach($frameStateName in @('frame', 'glow_frame')) {
            $frameStatePath = Join-Path $frameStateFolder ($frameStateName + '.json')
            if(Test-Path -LiteralPath $frameStatePath) {
                Remove-Item -LiteralPath $frameStatePath -Force
            }
        }
        if(Test-Path -LiteralPath $frameOverridePath) {
            Remove-Item -LiteralPath $frameOverridePath -Force
        }
    }

    $addon = Join-Path $base 'MiExImport.py'
    if(-not (Test-Path -LiteralPath $addon)) {
        Get-WebFile 'https://raw.githubusercontent.com/BramStoutProductions/MiEx/631e9fc2fde8c749bf59d4c3495492e62a83ef6c/extras/Blender/BlenderAddon/MiExImport.py' $addon
    }

    $region = [ordered]@{
      name='Region 1'; minX=$minX; maxX=$maxX; minZ=$minZ; maxZ=$maxZ;
      minY=$MinY; maxY=$MaxY; offsetX=0; offsetY=0; offsetZ=0;
      enableLOD=$false; lodBaseLevel=0; lodYDetail=1; chunkSize=$chunkSize;
      actAsExcludeRegion=$false;
      onlyIndividualBlocks=$false; excludeRegionsAsAir=$false; defaultValues=$false
    }
    # Ask MiEx to read a small, distributed sample of chunks before exporting.
    # This distinguishes an unreadable Bedrock LevelDB/chunk format from a
    # downstream failure to turn successfully decoded blocks into USD meshes.
    $probeChunks = @()
    $minChunkX = [int][math]::Floor($minX / 16.0)
    $maxChunkX = [int][math]::Floor($maxX / 16.0)
    $minChunkZ = [int][math]::Floor($minZ / 16.0)
    $maxChunkZ = [int][math]::Floor($maxZ / 16.0)
    foreach($fractionZ in @(0.1, 0.3, 0.5, 0.7, 0.9)) {
        foreach($fractionX in @(0.1, 0.3, 0.5, 0.7, 0.9)) {
            $probeChunks += @{ chunkX=([int][math]::Floor($minChunkX + ($maxChunkX - $minChunkX) * $fractionX));
                              chunkZ=([int][math]::Floor($minChunkZ + ($maxChunkZ - $minChunkZ) * $fractionZ)) }
        }
    }
    $commands = @()
    if($UseWorldResourcePacks) {
        # A unique working pack avoids stale textures from a different export
        # and keeps any USD-relative texture references valid after export.
        $worldPackName = 'MinecraftToBlender_World_' + [guid]::NewGuid().ToString('N')
        $commands += @{command='setActiveResourcePacks'; resourcePacks=@('BlenderEEVEE','base_resource_pack')}
        $commands += @{command='loadWorld'; world=$worldPath; loadWorldResourcePacks=$true; worldResourcePackName=$worldPackName}
        Write-Host 'Using world-supplied resource packs where available.' -ForegroundColor Cyan
    } else {
        $commands += @{command='loadWorld'; world=$worldPath; loadWorldResourcePacks=$false}
    }
    $commands += @{command='loadDimension'; dimension='overworld'}
    if(-not $UseWorldResourcePacks) {
        $commands += @{command='setActiveResourcePacks'; resourcePacks=@('BlenderEEVEE','base_resource_pack')}
    }
    $commands += @(
      @{command='getWorld'},
      @{command='getChunk'; chunks=$probeChunks; heightmap=$true},
      @{command='applyExportSettings'; settings=@{chunkSize=$chunkSize; exportRegions=@{'Region 1'=$region}; runOptimiser=$enableFaceOptimization; removeCaves=$false; fillInCaves=$false; exportBlockAnimations=$false; entityStartFrame=0; entityEndFrame=1; entityFPS=24; entitySpawnRules=@(); entitySimulate=@(); entityExport=@('minecraft:item_frame','minecraft:glow_item_frame','minecraft:painting','minecraft:block_display','minecraft:item_display','minecraft:armor_stand')}},
      @{command='export';path=(Join-Path $exportDir $exportFile)}
    )
    $cmdFile = Join-Path $work 'MiEx_export_commands.json'
    $commands | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $cmdFile -Encoding UTF8
    Write-Host 'Enabling vanilla item-frame, glow-frame, painting, display and armor-stand models (single static frame).' -ForegroundColor Cyan
    $env:MIEX_PORTABLE_EXPORTS='1'
    $env:MIEX_STORE_GEN_TEX_IN_EXPORT='1'
    $env:MIEX_SKIP_WORLD_RESOURCEPACK_CHECK = if($UseWorldResourcePacks) { '0' } else { '1' }
    $log = Join-Path $work 'miex_console.log'
    Write-Host 'Starting full-detail export. Large regions may take considerable time and memory.' -ForegroundColor Cyan
    if($enableFaceOptimization) {
        Write-Warning 'Check UV tiling, water, foliage, transparent blocks, biome tint and ambient occlusion after importing. Face merging and geometry subsets are not certified visually lossless.'
    }
    # IMPORTANT: Java writes harmless warnings to stderr. Windows PowerShell 5.1
    # can turn those warnings into terminating errors when ErrorActionPreference
    # is Stop and stderr is merged with stdout using *>&1. Capture both streams
    # separately instead; success depends on exit code AND the actual USD file.
    $stderrLog = Join-Path $work 'miex_stderr.log'
    $javaCommand = (Get-Command java.exe -ErrorAction Stop).Source
    $ramBytes = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).TotalPhysicalMemory
    if($ramBytes) {
        $ramGiB = [math]::Floor([double]$ramBytes / 1GB)
        $heapGiB = [int][math]::Max(2, [math]::Min(24, [math]::Floor($ramGiB * 0.5)))
    } else { $heapGiB = 8 }
    Write-Host "Java heap cap: ${heapGiB}G"
    $javaArgs = '-Xmx{0}G -jar "{1}" -cli -cliAutoQuit -storeGenTexInExport -skipWorldResourcePackCheck -commandFile "{2}"' -f $heapGiB, $runJar, $cmdFile
    Write-Host "MiEx stdout log: $log"
    Write-Host "MiEx stderr log: $stderrLog"
    Write-Host 'Java warnings alone do NOT stop the export.' -ForegroundColor DarkCyan
    # Launch Java directly; CMD would expand percent signs in world paths.
    # The captured streams keep warning messages separate from exit status.
    $capture = Start-CapturedProcess $javaCommand $javaArgs $miexDir $log $stderrLog
    $proc = $capture.Process
    $lastSize = -1
    while(-not $proc.HasExited) {
        [void]$proc.WaitForExit(5000)
        $proc.Refresh()
        if(Test-Path -LiteralPath $log) {
            $length = (Get-Item -LiteralPath $log).Length
            if($length -ne $lastSize) {
                $lastSize = $length
                Get-Content -LiteralPath $log -Tail 8 -ErrorAction SilentlyContinue | ForEach-Object {
                    if($_.Length -gt 4000 -and $_.StartsWith('[COMMAND] ')) {
                        Write-Host '[COMMAND] Large diagnostic response saved to miex_console.log.'
                    } else { Write-Host $_ }
                }
            }
        }
    }
    $code = Finish-CapturedProcess $capture
    Write-Host "MiEx Java process exited with code $code"
    if((Test-Path -LiteralPath $stderrLog) -and (Get-Item -LiteralPath $stderrLog).Length -gt 0) {
        Write-Host 'MiEx stderr (last 12 lines, warnings alone are not fatal):' -ForegroundColor Yellow
        Get-Content -LiteralPath $stderrLog -Tail 12 | ForEach-Object {Write-Host $_}
    }
    # Avoid converting enormous getWorld/player-NBT or getChunk JSON into
    # PowerShell objects; Windows PowerShell 5.1 can reject valid responses.
    $diagnostics = Read-MiExDiagnostics $log
    $probeReturned = $diagnostics.Returned
    $probeLoaded = $diagnostics.Readable
    $probeReported = $diagnostics.Reported
    $loadedMiExWorld = $diagnostics.WorldPath
    if($loadedMiExWorld) {
        Write-Host "MiEx selected world: $loadedMiExWorld" -ForegroundColor Cyan
        if(-not [string]::Equals([IO.Path]::GetFullPath($loadedMiExWorld), [IO.Path]::GetFullPath($worldPath), [StringComparison]::OrdinalIgnoreCase)) {
            Abort 'MiEx loaded a different world folder than the selected snapshot. Refusing an incorrect export.'
        }
    } else { Write-Warning 'MiEx did not return its selected-world path. Check the CLI command log.' }
    Write-Host ("MiEx chunk probe: $probeLoaded readable chunk(s), $probeReturned returned, out of $($probeChunks.Count) sampled positions.") -ForegroundColor Cyan
    $unsupportedChunk = Test-UnsupportedBedrockChunk $log $stderrLog
    if($unsupportedChunk) {
        Write-Warning 'MiEx cannot decode one or more Bedrock subchunk formats (see Data version in miex_console.log). This is an upstream chunk-reader compatibility issue, not a Blender import issue.'
    } elseif($probeReported -and $probeLoaded -eq 0) {
        Write-Warning 'MiEx could not decode terrain sections in any sampled chunk. Check the world snapshot DB and miex_console.log for read errors.'
    }
    $main = Join-Path $exportDir $exportFile
    if($code -ne 0 -or -not (Test-Path -LiteralPath $main)) {
        Abort "MiEx did not complete the run (Java exit code: $code). Check $log and $stderrLog. The original world ZIP is unchanged."
    }
    $materialsJson = Join-Path $exportDir ($ExportName + '_materials.json')
    $materialsUsd = Join-Path $exportDir ($ExportName + '_materials.usd')
    $chunksDir = Join-Path $exportDir ($ExportName + '_chunks')
    $materialsFound = (Test-Path -LiteralPath $materialsJson)
    $materialsUsdFound = (Test-Path -LiteralPath $materialsUsd)
    $chunkFiles = @()
    if(Test-Path -LiteralPath $chunksDir) {
        $chunkFiles = @(Get-ChildItem -LiteralPath $chunksDir -Filter '*.usd' -Recurse -File -ErrorAction SilentlyContinue)
    }
    $chunkCount = $chunkFiles.Count
    $entityUsdFiles = @(Get-ChildItem -LiteralPath $exportDir -Recurse -Filter '*entit*.usd' -File -ErrorAction SilentlyContinue)
    $entityUsdCount = $entityUsdFiles.Count
    if(-not $materialsFound) {
        Write-Warning 'Blender materials JSON is MISSING. The USD may import but cannot have correct Blender material nodes. Check BlenderEEVEE pack activation.'
    }
    if(-not $materialsUsdFound) { Write-Warning 'USD materials sidecar is missing.' }
    if($chunkCount -eq 0) { Write-Warning 'No chunk USD files were found; the main USD may reference missing geometry.' }
    # MiEx can return process code 0 and [COMMAND] status=success even when
    # meshes were skipped. Check that the expected USD isn't a zero-byte file.
    if((Get-Item -LiteralPath $main).Length -eq 0) { Abort 'USD exists but is empty.' }
    $usdText = Get-Content -LiteralPath $main -Raw
    $refPattern = 'payload\s*=\s*@\./' + [regex]::Escape($ExportName + '_chunks') + '/region_1_chunk_\d+_\d+\.usd@'
    $refMatches = [regex]::Matches($usdText, $refPattern)
    $regionPayloadCount = $refMatches.Count
    $expectedSections = [int][math]::Ceiling($Size / (16.0 * $chunkSize))
    $expectedSections = $expectedSections * $expectedSections
    if($regionPayloadCount -ne $expectedSections) {
        Write-Warning "Region section reference count: $regionPayloadCount; expected: $expectedSections. Verify MiEx applied the chunk-size setting."
    }
    # The root USD can contain valid render/proxy payload references even if
    # every referenced chunk is empty. Catch that before replacing a previous
    # export or launching Blender, which cannot reconstruct missing terrain.
    if(-not (Test-ChunkTerrainGeometry $chunksDir)) {
        $diagnosis = if($unsupportedChunk) {
            'MiEx rejected the saved Bedrock chunk format; inspect miex_console.log for the exact unsupported Data version.'
        } elseif($probeReported -and $probeLoaded -gt 0) {
            'MiEx decoded some terrain chunks, but its mesh generation/export produced no terrain faces. Inspect the MiEx log for blockstate/material exceptions.'
        } elseif($probeReported) {
            'MiEx could not decode terrain in any sampled location. Check LevelDB open errors, subchunk versions and whether the snapshot contains saved terrain.'
        } else {
            'No valid chunk-read diagnostic was returned. The MiEx command sequence or world loading may have failed.'
        }
        Abort ("MiEx produced no solid terrain in X=$minX..$maxX, Z=$minZ..$maxZ. $diagnosis " +
               "Inspect $log and $stderrLog; keep those logs for diagnosis. The previous export was preserved.")
    }
    Write-Host 'Verified: exported chunk USD contains nonempty terrain mesh faces.' -ForegroundColor Green
    # LOSSLESS COMPACT USD: convert text (USDA) layers to indexed Crate
    # (USDC) layers, keeping their .usd filenames and relative payload paths.
    # This is a file-format conversion, NOT face reduction or retopology.
    # It uses Blender's existing Python/OpenUSD installation, not an add-on.
    $binaryInfoPath = Join-Path $work 'USD_Crate_Result.txt'
    $binaryLog = Join-Path $work 'USD_Crate_Convert.log'
    $binarySummary = 'Skipped optional USD compaction for faster export. Original USD is preserved.'
    if($CompactUSD) {
        $binarySummary = 'Blender executable not detected; original ASCII USD is still valid.'
        $blenderExe = $null
        $blenderCmd = Get-Command 'blender.exe' -ErrorAction SilentlyContinue
        if($blenderCmd) { $blenderExe = $blenderCmd.Source }
        if(-not $blenderExe) {
            $blenderRoot = Join-Path ${env:ProgramFiles} 'Blender Foundation'
            if(Test-Path -LiteralPath $blenderRoot) {
                $blenderExe = Get-ChildItem -LiteralPath $blenderRoot -Filter 'blender.exe' -File -Recurse -ErrorAction SilentlyContinue |
                    Sort-Object FullName -Descending | Select-Object -ExpandProperty FullName -First 1
            }
        }
        if($blenderExe -and (Test-Path -LiteralPath $blenderExe)) {
            $crateScript = Join-Path $base 'Convert_USD_To_Crate.py'
            if(-not (Test-Path -LiteralPath $crateScript)) { Abort 'Lossless USD converter script is missing.' }
            $crateStderrLog = Join-Path $work 'USD_Crate_Convert_Errors.log'
            # Run Blender directly as well: the optional compactor must treat
            # workspace paths literally, not reinterpret them through CMD.
            $crateArgs = '--background --factory-startup --python "{0}" -- "{1}" "{2}" "{3}"' -f $crateScript, $exportDir, $binaryInfoPath, $exportFile
            Write-Host 'Compacting USD layers to lossless binary Crate format using installed Blender...' -ForegroundColor Cyan
            $crateCapture = Start-CapturedProcess $blenderExe $crateArgs $work $binaryLog $crateStderrLog
            $crateCode = Finish-CapturedProcess $crateCapture
            if(Test-Path -LiteralPath $binaryLog) {
                Get-Content -LiteralPath $binaryLog -Tail 10 | ForEach-Object {Write-Host $_}
            }
            if(Test-Path -LiteralPath $crateStderrLog) {
                Get-Content -LiteralPath $crateStderrLog -Tail 10 | ForEach-Object {Write-Host $_}
            }
            if($crateCode -ne '0') {
                $binarySummary = "Crate conversion not completed (exit $crateCode). See $binaryLog. Existing USD layers are still valid."
                Write-Warning $binarySummary
            } elseif(Test-Path -LiteralPath $binaryInfoPath) {
                $binarySummary = (Get-Content -LiteralPath $binaryInfoPath -Raw).Trim()
                Write-Host $binarySummary -ForegroundColor Green
            } else {
                $binarySummary = 'Crate process exited successfully but no conversion report was produced.'
                Write-Warning $binarySummary
            }
        } else {
            Write-Warning 'No Blender executable detected. Skipping optional lossless Crate conversion; ASCII USD remains intact.'
        }
    }
    # A successful Java exit code is insufficient if the output is missing
    # companion files. Refuse to publish an incomplete replacement.
    if(-not $materialsFound -or -not $materialsUsdFound -or $chunkCount -eq 0) {
        Abort 'MiEx export is missing material or chunk USD files. The previous export was preserved.'
    }
    # Ensure texture definitions are portable before relocating the stage.
    $matText = [System.IO.File]::ReadAllText($materialsJson)
    if($matText.Contains($exportDir + '\') -or $matText.Contains(($exportDir -replace '\\', '/'))) {
        Abort 'Materials reference the temporary export path; refusing to publish a broken import.'
    }
    Publish-Export $exportDir $finalExportDir
    $exportDir = $finalExportDir
    $main = Join-Path $exportDir $exportFile
    Write-Host 'Fresh export published; previous chunk layers cannot be reused.' -ForegroundColor Green
    $reportPath = Join-Path $work 'Export_Accuracy_Audit.txt'
    $missing = @()
    $errors = @()
    $exceptions = @()
    $logSuccess = $false
    if(Test-Path -LiteralPath $log) {
        $missing = @(Select-String -LiteralPath $log -Pattern 'Missing blockstate:\s*([^\r\n]+)' -AllMatches | ForEach-Object { $_.Matches | ForEach-Object {$_.Groups[1].Value.Trim()} } | Sort-Object -Unique)
        $errors = @(Select-String -LiteralPath $log -Pattern '(?i)\[MSG\] Error:|No blockstate file|Missing texture|No texture found|Missing model|No model file|Unknown block|Exception|\[MSG\] Error|\[ERROR\]' | Select-Object -First 35 | ForEach-Object {$_.Line.Trim()})
        $logSuccess = [bool](Select-String -LiteralPath $log -SimpleMatch '[COMMAND] {"status":"success"}' -Quiet)
    }
    if(Test-Path -LiteralPath $stderrLog) {
        $exceptions = @(Select-String -LiteralPath $stderrLog -Pattern 'Exception|Error:|OutOfMemory|fatal' | Select-Object -First 35 | ForEach-Object {$_.Line.Trim()})
    }
    $report = @(
        'MINECRAFT TO BLENDER v1 - ACCURACY AUDIT',
        ('Generated UTC: ' + [DateTime]::UtcNow.ToString('u')),
        ('USD: ' + $main),
        ('USD size after optional binary compaction: ' + (Get-Item -LiteralPath $main).Length + ' bytes'),
        ('Java exit code: ' + $code),
        'Export mode: compatibility-first; face merging and individual block instancing disabled',
        ('Minecraft-chunks-per-USD-section: ' + $chunkSize + 'x' + $chunkSize),
        ('USD geometry-subset batching enabled: ' + $enableGeometrySubsets),
        ('Face merging enabled (MiEx FaceOptimiser): ' + $enableFaceOptimization),
        'Raytracing geometry removal disabled (preserve all visible model surfaces).',
        ('Fill export-region boundary faces: ' + $fillWorldBorders),
        'Generated textures (banners, layered entity materials) stored with the export.',
        ('MiEx JAR used: ' + $runJar),
        ('MiEx status success: ' + $logSuccess),
        ('USD binary Crate compaction: ' + $binarySummary),
        ('Exported chunk USD files: ' + $chunkCount),
        ('Main USD terrain payloads: ' + $regionPayloadCount),
        ('Expected terrain payloads: ' + $expectedSections),
        ('Entity-named USD sidecar files: ' + $entityUsdCount),
        ('Blender materials JSON present: ' + $materialsFound),
        ('USD materials sidecar present: ' + $materialsUsdFound),
        ('Source ZIP SHA256 or direct world level.dat SHA256: ' + $actualWorldHash),
        ('Source world edition: ' + $Edition),
        'Source world compatibility depends on MiEx support for this saved version.',
        'MiEx Java asset source may differ from Bedrock; vanilla texture parity is NOT verified.',
        ('Export region X=' + $minX + '..' + $maxX + ', Z=' + $minZ + '..' + $maxZ + ', Y=' + $MinY + '..' + $MaxY + ', LOD disabled'),
        'Bedrock frame and glow-frame blockstate definitions and pinned vanilla frame-entity model corrected; visual item-frame verification still required.',
        'Entity export requested: item_frame, glow_item_frame, painting, block_display, item_display, armor_stand.',
        'Entity timeline: static single frame (no simulation).',
        'Face merging and geometry-subset batching disabled to avoid missing terrain. Verify model visually.',
        'IMPORTANT: Check actual frame meshes and item contents in Blender. Blockstate warnings alone cannot prove entity export failed or succeeded.',
        '',
        'IMPORTANT: structurally valid geometry does NOT prove correct models or textures.',
        ('Missing blockstate names reported: ' + $missing.Count),
        ('Logged suspicious error lines (sample): ' + $errors.Count),
        ('Stderr exception/error lines (sample): ' + $exceptions.Count),
        '',
        'MISSING BLOCKSTATES:',
        ($missing -join [Environment]::NewLine),
        '',
        'LOGGED ERRORS:',
        ($errors -join [Environment]::NewLine),
        '',
        'STDERR EXCEPTIONS:',
        ($exceptions -join [Environment]::NewLine),
        '',
        'UNRESOLVED LIMITATIONS:',
        'MiEx Bedrock block-state translation and model generation are not independently verified for all block variants.',
        'MiEx uses translated assets; exact Bedrock texture parity is not independently proven.',
        'MiEx Bedrock WorldBedrock.java initializes worldVersion=0 intentionally; this is not an error.',
        'Frame block entities are requested via entityExport; corrected model output and item contents still require Blender inspection.',
        'Non-animated USD cannot exactly reproduce every runtime rendering effect; animations and lighting are excluded by user request.'
    )
    [System.IO.File]::WriteAllLines($reportPath, $report, [System.Text.Encoding]::UTF8)
    Write-Host "Export generated: $main" -ForegroundColor Green
    Write-Host "Accuracy audit: $reportPath" -ForegroundColor Cyan
    Write-Host "Official MiEx Blender importer: $addon"
    Write-Host 'To import correctly: install and enable MiExImport.py in Blender, then File > Import > MiEx USD.'
    if($missing.Count -gt 0 -or $errors.Count -gt 0 -or $exceptions.Count -gt 0 -or -not $logSuccess -or -not $materialsFound -or -not $materialsUsdFound -or $chunkCount -eq 0 -or $regionPayloadCount -ne $expectedSections) {
        Write-Host 'WARNING: The USD was generated, but MiEx reported unresolved rendering problems. This is NOT an exact Bedrock export.' -ForegroundColor Yellow
        if($missing.Count -gt 0) { Write-Host ('Missing blockstates: ' + ($missing -join ', ')) -ForegroundColor Yellow }
        Write-Host "Review $reportPath before importing into Blender."
    } else {
        Write-Host 'No obvious logged errors or missing files were found; this still does not certify exact block/state parity.' -ForegroundColor Yellow
    }
    # The GUI provides an Open Folder action; do not open Explorer automatically.
} catch {
    if($exportDir -ne $finalExportDir -and (Test-Path -LiteralPath $exportDir)) {
        Remove-Item -LiteralPath $exportDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host ('EXPORT STOPPED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('At line: ' + $_.InvocationInfo.ScriptLineNumber) -ForegroundColor DarkYellow
    exit 1
}
