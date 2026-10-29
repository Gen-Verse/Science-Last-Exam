$ErrorActionPreference = 'Stop'
$root = 'C:\scientific-gui-build\scientific-gui'
Set-Location $root
$settings = Get-Content "$root\settings.json" -Raw | ConvertFrom-Json
function AssetPath($name) { Join-Path "$root\installers" $settings.assets.$name.filename }
function RunInstaller($path, $arguments) {
    $process = Start-Process -FilePath $path -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) { throw "Installer failed with exit code $($process.ExitCode): $path" }
}
RunInstaller (AssetPath 'python') @('/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_test=0', 'TargetDir=C:\Python312')
$env:PATH = "C:\Python312;C:\Python312\Scripts;$env:PATH"
$version = & C:\Python312\python.exe -c 'import platform; print(platform.python_version())'
if ($version.Trim() -ne '3.12.10') { throw "Unexpected Python version: $version" }
$setup = 'C:\Users\Docker\Desktop\Setup'
New-Item -ItemType Directory -Force "$setup\VESTA-win64", "$setup\output_result" | Out-Null
Expand-Archive -Path (AssetPath 'vesta') -DestinationPath "$setup\VESTA-win64"
foreach ($name in @('digitalmicrograph')) {
    $asset = $settings.assets.$name
    # Supply the vendor's actual unattended switches, including no-restart and licensing settings.
    if (-not $asset.arguments) { throw "Missing unattended installer arguments: $name" }
    $file = AssetPath $name
    if ([IO.Path]::GetExtension($file) -eq '.msi') {
        RunInstaller 'msiexec.exe' (@('/i', "`"$file`"") + @($asset.arguments))
    } else {
        RunInstaller $file @($asset.arguments)
    }
}
$env:GUI_BRIDGE_TOKEN = $settings.bridge_token
& "$root\harness\images\provision-windows.ps1" -ProjectPath $root
if ($LASTEXITCODE -ne 0) { throw 'Bridge provisioning failed' }
New-NetFirewallRule -DisplayName 'Science GUI bridge' -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 5001 -RemoteAddress 10.0.2.2 | Out-Null
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /hibernate off
# Build-time WinRM is disabled by Packer's shutdown command; the runtime uses only the GUI bridge.
