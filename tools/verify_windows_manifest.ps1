param([string]$Executable = 'MinecraftToBlender_v1.exe')
$ErrorActionPreference = 'Stop'

# Map only resources as data. This verification never starts the application.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class MinecraftResourceReader {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr LoadLibraryExW(string path, IntPtr file, uint flags);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool FreeLibrary(IntPtr module);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr FindResourceW(IntPtr module, IntPtr name, IntPtr type);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SizeofResource(IntPtr module, IntPtr resource);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr LoadResource(IntPtr module, IntPtr resource);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr LockResource(IntPtr resource);
}
'@
$path = (Resolve-Path -LiteralPath $Executable).Path
$module = [MinecraftResourceReader]::LoadLibraryExW($path, [IntPtr]::Zero, 0x22)
if ($module -eq [IntPtr]::Zero) { throw 'Could not map EXE resources as data' }
try {
    $resource = [MinecraftResourceReader]::FindResourceW($module, [IntPtr]1, [IntPtr]24)
    if ($resource -eq [IntPtr]::Zero) { throw 'Built EXE has no application manifest' }
    $size = [MinecraftResourceReader]::SizeofResource($module, $resource)
    if ($size -eq 0 -or $size -gt 65536) { throw 'Invalid application manifest size' }
    $handle = [MinecraftResourceReader]::LoadResource($module, $resource)
    $pointer = [MinecraftResourceReader]::LockResource($handle)
    if ($pointer -eq [IntPtr]::Zero) { throw 'Could not read application manifest' }
    $bytes = New-Object byte[] $size
    [Runtime.InteropServices.Marshal]::Copy($pointer, $bytes, 0, $bytes.Length)
    $xml = New-Object Xml.XmlDocument
    $xml.XmlResolver = $null
    $xml.LoadXml([Text.Encoding]::UTF8.GetString($bytes).TrimEnd([char]0))
    $ns = New-Object Xml.XmlNamespaceManager $xml.NameTable
    $ns.AddNamespace('asm', 'urn:schemas-microsoft-com:asm.v1')
    $ns.AddNamespace('trust', 'urn:schemas-microsoft-com:asm.v3')
    $levels = @($xml.SelectNodes('/asm:assembly/trust:trustInfo/trust:security/trust:requestedPrivileges/trust:requestedExecutionLevel', $ns))
    if ($levels.Count -ne 1 -or $levels[0].level -cne 'asInvoker' -or $levels[0].uiAccess -cne 'false') {
        throw 'Application must request normal user privileges without UI access'
    }
    $identity = $xml.SelectSingleNode('/asm:assembly/asm:assemblyIdentity', $ns)
    $version = (Get-Content (Join-Path $PSScriptRoot '../VERSION') -Raw).Trim() + '.0'
    if ($identity.name -cne 'MinecraftToBlender' -or $identity.version -cne $version) {
        throw 'Application manifest identity does not match VERSION'
    }
    Write-Host "Verified built EXE manifest: asInvoker, uiAccess=false, version=$version"
} finally {
    [void][MinecraftResourceReader]::FreeLibrary($module)
}
