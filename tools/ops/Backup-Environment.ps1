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
$pgImage = (& docker inspect --format '{{.Config.Image}}' $dbId).Trim()
$runningServices = @(& docker @argsBase ps --services --status running | Where-Object { $_ -ne 'postgres' -and $_ -ne 'kodame-kordoc' })
$runningIds = @(& docker @argsBase ps -q @runningServices)
# Preserve DB/file consistency by stopping writers before both snapshots.
# Containers/volumes are never removed; the same stopped containers restart.
try {
    Invoke-Docker ($argsBase + @('stop') + $runningServices)
    Invoke-Docker @('exec', $dbId, 'pg_dump', '-U', 'kodame', '-d', 'kodame', '-Fc', '-f', '/tmp/odame-backup.dump')
    Invoke-Docker @('cp', "${dbId}:/tmp/odame-backup.dump", (Join-Path $backupDir 'database.dump'))
    Invoke-Docker @('run', '--rm', '--network', 'none', '--volumes-from', "${apiId}:ro", '-v', "${backupDir}:/backup", $pgImage, 'tar', '-czf', '/backup/files.tar.gz', '-C', '/app/data', '.')
    Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backupDir 'database.dump'), (Join-Path $backupDir 'files.tar.gz') |
        Select-Object Algorithm, Hash, Path | ConvertTo-Json | ForEach-Object {
            [IO.File]::WriteAllText((Join-Path $backupDir 'checksums.json'), $_, (New-Object Text.UTF8Encoding($false)))
        }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = Join-Path ([IO.Path]::GetDirectoryName($backupDir)) ([IO.Path]::GetFileName($backupDir)+'.zip')
    [IO.Compression.ZipFile]::CreateFromDirectory($backupDir,$archive,[IO.Compression.CompressionLevel]::NoCompression,$false)
    . (Join-Path $PSScriptRoot 'Backup-Crypto.ps1')
    $key = Get-BackupKey (Join-Path $opsRoot '.runtime/backups/local-backup-key.dpapi')
    Protect-Backup $archive (Join-Path $backupDir 'backup.aes') $key
    # Exact files created above, never a recursive deletion of a computed root.
    Remove-Item -LiteralPath $archive,(Join-Path $backupDir 'database.dump'),(Join-Path $backupDir 'files.tar.gz')
    [IO.File]::WriteAllText((Join-Path $backupDir 'manifest.json'),(@{environment=$Environment;createdAt=(Get-Date).ToUniversalTime().ToString('o');format='aes256cbc-hmacsha256';keyRecovery='Windows DPAPI current user';databaseImage=$pgImage}|ConvertTo-Json))
    Write-Output "Consistent encrypted local backup completed: $backupDir"
} finally {
    # Start the exact containers we paused, even if the workspace Compose was edited.
    if ($runningIds.Count) { Invoke-Docker (@('start') + $runningIds) }
}
