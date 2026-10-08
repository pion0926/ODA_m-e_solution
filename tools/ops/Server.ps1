[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('production','development')][string]$Environment,
    [ValidateSet('start','stop','status','logs')][string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$opsRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$composeArgs = @('compose')
if ($Environment -eq 'production') {
    $runtimeDir = Join-Path $opsRoot '.runtime'
    $manifest = Get-Content -LiteralPath (Join-Path $runtimeDir 'production-release.json') -Raw | ConvertFrom-Json
    $sourceDir = [IO.Path]::GetFullPath($manifest.sourceDir)
    $releaseRoot = [IO.Path]::GetFullPath((Join-Path $runtimeDir 'releases')) + [IO.Path]::DirectorySeparatorChar
    if (-not $sourceDir.StartsWith($releaseRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Release source must be inside .runtime/releases.' }
    $composeArgs += @('--env-file', (Join-Path $runtimeDir 'production.env'), '--env-file', (Join-Path $runtimeDir 'production-images.env'), '-f', (Join-Path $sourceDir 'compose.production.yml'))
    foreach ($property in $manifest.images.PSObject.Properties) {
        $revision = & docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' $property.Value.imageId
        $expectedRevision = if ($property.Value.sourceRevision) { $property.Value.sourceRevision } else { $manifest.commit }
        if ($LASTEXITCODE -ne 0 -or $revision -ne $expectedRevision) { throw "Release image missing or revision mismatch: $($property.Name)" }
    }
} else {
    $composeArgs += @('--env-file', (Join-Path $opsRoot '.env'), '-f', (Join-Path $opsRoot 'docker-compose.yml'))
}
switch ($Action) {
    'start' {
        $composeArgs += @('up', '-d')
        if ($Environment -eq 'production') { $composeArgs += @('--no-build', '--pull', 'never') }
        else { $composeArgs += '--build' }
        $composeArgs += @('--wait', '--wait-timeout', '180')
    }
    'stop' { $composeArgs += 'stop' }
    'status' { $composeArgs += 'ps' }
    'logs' { $composeArgs += @('logs', '--tail', '100') }
}
& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw "Docker $Environment $Action failed ($LASTEXITCODE). Volumes were not deleted." }
