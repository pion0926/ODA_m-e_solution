[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$opsRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Assert-Deployment([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    Write-Output "PASS $Message"
}
# Parse configurations in memory; never print environment values containing keys.
$development = & docker compose --env-file (Join-Path $opsRoot '.env') -f (Join-Path $opsRoot 'docker-compose.yml') config --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Invalid development compose configuration.' }
$production = & docker compose --env-file (Join-Path $opsRoot '.runtime/production.env') --env-file (Join-Path $opsRoot '.runtime/production-images.env') -f (Join-Path $opsRoot 'compose.production.yml') config --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Invalid production compose configuration.' }
Assert-Deployment ($development.name -eq 'odame') 'Existing development project name preserved'
Assert-Deployment ($production.name -eq 'odame-prod') 'Production project isolated'
foreach ($service in $production.services.PSObject.Properties) {
    Assert-Deployment (-not $service.Value.build) "Production $($service.Name) cannot rebuild working-tree code"
    Assert-Deployment ($service.Value.image -match '^sha256:[a-f0-9]{64}$') "Production $($service.Name) image is content-addressed"
    Assert-Deployment (-not @($service.Value.volumes | Where-Object type -eq 'bind').Count) "Production $($service.Name) has no development bind mounts"
}
$devCookie = $development.services.'kodame-redesign-api'.environment.SESSION_COOKIE_NAME
$prodCookie = $production.services.'kodame-redesign-api'.environment.SESSION_COOKIE_NAME
Assert-Deployment ($devCookie -ne $prodCookie) 'Login cookie names are different across ports'
Assert-Deployment (-not $production.services.postgres.ports) 'Production database is not exposed to host ports'
Assert-Deployment ($production.services.'kodame-redesign-api'.environment.ALLOW_REGISTRATION -eq 'false') 'Public signup disabled'
Assert-Deployment ($production.services.'kodame-redesign-api'.environment.KODAME_SEED_DEMO_ACCOUNTS -eq 'false') 'No demo users seeded'
Assert-Deployment ($production.services.'kodame-redesign-web'.ports[0].published -ne $development.services.'kodame-redesign-web'.ports[0].published) 'Web ports are distinct'
foreach ($name in $production.volumes.PSObject.Properties.Name) {
    Assert-Deployment ($production.volumes.$name.name -notin @($development.volumes.PSObject.Properties.Value.name)) "Volume $name is not shared with development"
}
Write-Output 'Deployment configuration isolation checks completed. No database mutations or AI requests performed.'
