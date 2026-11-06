$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'assets/Export_World.ps1'),[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count) { throw $parseErrors }
$function = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-MiExJavaArguments' },$true)
if($null -eq $function) { throw 'Missing MiEx launch helper' }
Invoke-Expression $function.Extent.Text
$heapFunction = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-MiExHeapGiB' },$true)
if($null -eq $heapFunction) { throw 'Missing MiEx heap helper' }
Invoke-Expression $heapFunction.Extent.Text
function Get-CimInstance {
    [CmdletBinding()]
    param([string]$ClassName)
    if($ClassName -ne 'Win32_ComputerSystem') { throw 'Unexpected CIM query' }
    if($script:heapProbeFailure) { throw 'Simulated terminating CIM provider failure' }
    return [pscustomobject]@{TotalPhysicalMemory=$script:heapProbeBytes}
}
try {
    $script:heapProbeFailure = $false
    foreach($case in @(@(0,8),@(4GB,2),@(16GB,8),@(32GB,16),@(128GB,24))) {
        $script:heapProbeBytes = $case[0]
        if((Get-MiExHeapGiB) -ne $case[1]) { throw ('Wrong heap cap for ' + $case[0]) }
    }
    $script:heapProbeFailure = $true
    if((Get-MiExHeapGiB) -ne 8) { throw 'Terminating memory probe failure did not use fallback' }
} finally {
    Remove-Item Function:\Get-CimInstance
}
foreach($reader in @('', 'C:\test workspace\reader')) {
    foreach($worldPacks in @($false,$true)) {
        $launch = Get-MiExJavaArguments 4 'C:\test workspace\MiEx.jar' $reader 'C:\test workspace\commands.json' $worldPacks
        $skips = [regex]::Matches($launch,'-skipWorldResourcePackCheck').Count
        if($skips -ne [int](-not $worldPacks)) { throw "World pack toggle ignored in: $launch" }
        if(-not $launch.Contains('-commandFile "C:\test workspace\commands.json"')) { throw 'Command path not quoted' }
        if($reader) {
            if(-not $launch.Contains('-cp "C:\test workspace\reader;C:\test workspace\MiEx.jar"')) { throw 'Reader classpath not retained/quoted' }
            if($launch.Contains(' -jar ')) { throw 'Overlay launcher incorrectly uses -jar' }
        } elseif(-not $launch.Contains('-jar "C:\test workspace\MiEx.jar"')) { throw 'Java JAR path not quoted' }
    }
}
Write-Host 'MiEx Java and Bedrock launchers honor world resource packs and retain quoted paths.'
Write-Host 'MiEx heap selection retains RAM limits and falls back when the Windows memory query fails.'
