[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('production','development')][string]$Environment)
$ErrorActionPreference = 'Stop'
$opsRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$argsBase = @('compose')
if ($Environment -eq 'production') {
    $manifest = Get-Content (Join-Path $opsRoot '.runtime/production-release.json') -Raw | ConvertFrom-Json
    $argsBase += @('--env-file', (Join-Path $opsRoot '.runtime/production.env'), '--env-file', (Join-Path $opsRoot '.runtime/production-images.env'), '-f', (Join-Path $manifest.sourceDir 'compose.production.yml'))
} else {
    $argsBase += @('--env-file', (Join-Path $opsRoot '.env'), '-f', (Join-Path $opsRoot 'docker-compose.yml'))
}
function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed ($LASTEXITCODE)" }
}
$backupDir = Join-Path $opsRoot ('.runtime/backups/' + $Environment + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupDir | Out-Null
$dbId = (& docker @argsBase ps -q postgres).Trim()
$apiId = (& docker @argsBase ps -q kodame-redesign-api).Trim()
if (-not $dbId -or -not $apiId) { throw 'Environment must be running before backup.' }
$pgImage = (& docker inspect --format '{{.Image}}' $dbId).Trim()
# Preserve DB/file consistency by stopping writers before both snapshots.
# Containers/volumes are never removed; the same stopped containers restart.
try {
    Invoke-Docker ($argsBase + @('stop', 'kodame-redesign-web', 'kodame-intake-worker', 'kodame-redesign-api'))
    Invoke-Docker @('exec', $dbId, 'pg_dump', '-U', 'kodame', '-d', 'kodame', '-Fc', '-f', '/tmp/odame-backup.dump')
    Invoke-Docker @('cp', "${dbId}:/tmp/odame-backup.dump", (Join-Path $backupDir 'database.dump'))
    Invoke-Docker @('run', '--rm', '--network', 'none', '--volumes-from', "${apiId}:ro", '-v', "${backupDir}:/backup", $pgImage, 'tar', '-czf', '/backup/files.tar.gz', '-C', '/app/data', '.')
    Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backupDir 'database.dump'), (Join-Path $backupDir 'files.tar.gz') |
        Select-Object Algorithm, Hash, Path | ConvertTo-Json | ForEach-Object {
            [IO.File]::WriteAllText((Join-Path $backupDir 'checksums.json'), $_, (New-Object Text.UTF8Encoding($false)))
        }
    Write-Output "Consistent backup completed: $backupDir"
} finally {
    Invoke-Docker ($argsBase + @('start', 'kodame-redesign-api', 'kodame-intake-worker', 'kodame-redesign-web'))
}
