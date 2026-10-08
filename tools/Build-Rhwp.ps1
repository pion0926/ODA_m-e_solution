[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$work = Join-Path $taskRoot '.runtime/tooling-upgrade'
$source = Join-Path $work 'rhwp-source'
New-Item -ItemType Directory -Force -Path $work | Out-Null
if (-not (Test-Path -LiteralPath $source)) {
    & git clone --depth 1 --branch v0.8.6 --filter=blob:none --sparse https://github.com/edwardkim/rhwp.git $source
    if ($LASTEXITCODE) { throw 'rHWP checkout failed' }
}
$revision = (& git -C $source rev-parse HEAD).Trim()
if ($revision -ne 'f1f9c6ae58344ee9368996d3543f76b9345cf227') { throw 'Unexpected rHWP source revision' }
& git -C $source sparse-checkout set rhwp-studio npm pkg scripts
if ($LASTEXITCODE) { throw 'rHWP sparse checkout failed' }
& npm.cmd pack '@rhwp/core@0.8.6' --pack-destination $work --silent
if ($LASTEXITCODE) { throw 'rHWP core download failed' }
New-Item -ItemType Directory -Force -Path (Join-Path $source 'pkg') | Out-Null
& tar -xf (Join-Path $work 'rhwp-core-0.8.6.tgz') -C (Join-Path $source 'pkg') --strip-components=1
if ($LASTEXITCODE) { throw 'rHWP core extraction failed' }
& python -X utf8 (Join-Path $PSScriptRoot 'build_rhwp.py') $source
if ($LASTEXITCODE) { throw 'rHWP adapter preparation failed' }
$studio = Join-Path $source 'rhwp-studio'
& npm.cmd ci --prefix $studio --no-audit --no-fund
if ($LASTEXITCODE) { throw 'rHWP build dependency installation failed' }
$previousHwpctrl = $env:RHWP_WITHOUT_HWPCTRL
$previousFonts = $env:RHWP_DISABLE_EXTERNAL_WEBFONTS
try {
    $env:RHWP_WITHOUT_HWPCTRL = '1'
    $env:RHWP_DISABLE_EXTERNAL_WEBFONTS = '1'
    & npm.cmd run build --prefix $studio -- --base=/assets/rhwp/
    if ($LASTEXITCODE) { throw 'rHWP build failed' }
    & python -X utf8 (Join-Path $PSScriptRoot 'build_rhwp.py') $source --publish
    if ($LASTEXITCODE) { throw 'rHWP asset publication failed' }
} finally {
    $env:RHWP_WITHOUT_HWPCTRL = $previousHwpctrl
    $env:RHWP_DISABLE_EXTERNAL_WEBFONTS = $previousFonts
}
