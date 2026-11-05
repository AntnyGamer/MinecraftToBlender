$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'assets/Export_World.ps1'),[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count) { throw $parseErrors }
$function = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-MiExJavaArguments' },$true)
if($null -eq $function) { throw 'Missing MiEx launch helper' }
Invoke-Expression $function.Extent.Text
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
