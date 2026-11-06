$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../assets/Bedrock_Assets.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('miex-state-models-' + [guid]::NewGuid().ToString('N'))
try {
    # A first install has no extracted base models. Every procedural fallback
    # must still have distinct tinted-line and untinted-overlay planes.
    Set-BedrockStateCorrections $root (Join-Path $PSScriptRoot '../assets') bedrock
    $models = Join-Path $root 'resources/BlenderEEVEE/assets/minecraft/models/block'
    foreach($name in @('redstone_dust_dot','redstone_dust_side','redstone_dust_side_alt','redstone_dust_up')) {
        $path = Join-Path $models ($name + '.json')
        $model = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        $line = $model.elements[0]; $overlay = $model.elements[1]
        $axis = if($name -eq 'redstone_dust_up') { 2 } else { 1 }
        if([Math]::Abs(($overlay.from[$axis] - $line.from[$axis]) - 0.001) -gt 0.0000001) {
            throw ('Redstone overlay remains coincident: ' + $name)
        }
        if($line.faces.PSObject.Properties.Value[0].tintindex -ne 0) { throw 'Lost redstone power tint' }
        # Once the vanilla model exists, preserve its material/UV definition
        # and derive the correction from it each run, without accumulating bias.
        $base = Join-Path $root ('resources/base_resource_pack/assets/minecraft/models/block/' + $name + '.json')
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $base) | Out-Null
        $overlay.from[$axis] -= 0.001; $overlay.to[$axis] -= 0.001
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
    Write-Host 'Bedrock dust models: fresh install, cached base, overlay spacing, idempotence and edition cleanup passed.'
} finally {
    # Only remove this test's explicitly allocated temporary tree.
    $resolvedRoot = [IO.Path]::GetFullPath($root)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if(-not $resolvedRoot.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
       (Split-Path -Leaf $resolvedRoot) -notmatch '^miex-state-models-[0-9a-f]{32}$') { throw 'Unexpected test cleanup path' }
    if(Test-Path -LiteralPath $resolvedRoot) { Remove-Item -LiteralPath $resolvedRoot -Recurse -Force }
}
