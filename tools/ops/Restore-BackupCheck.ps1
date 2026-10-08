[CmdletBinding()]
param([Parameter(Mandatory)][string]$BackupDirectory, [string]$ApiImage='odame-qa/api:refactor')
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$backup=(Resolve-Path -LiteralPath $BackupDirectory).Path
$runtime=(Resolve-Path (Join-Path $taskRoot '.runtime')).Path
if (-not $backup.StartsWith($runtime+[IO.Path]::DirectorySeparatorChar)) { throw 'Backup must be inside workspace runtime' }
$checkRoot=Join-Path $runtime ('restore-check-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $checkRoot | Out-Null
$ident='odame-restore-'+[Guid]::NewGuid().ToString('N').Substring(0,12)
$watch=[Diagnostics.Stopwatch]::StartNew()
$manifest=Get-Content (Join-Path $backup 'manifest.json') -Raw | ConvertFrom-Json
function Invoke-RestoreDocker([string[]]$Arguments) {
    $result=& docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Isolated restore command failed ($LASTEXITCODE)" }
    return $result
}
. (Join-Path $PSScriptRoot 'Backup-Crypto.ps1')
try {
    $key=Get-BackupKey (Join-Path $runtime 'backups/local-backup-key.dpapi')
    $archive=Join-Path $checkRoot 'archive.zip'
    Unprotect-Backup (Join-Path $backup 'backup.aes') $archive $key
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($archive,(Join-Path $checkRoot 'payload'))
    $payload=Join-Path $checkRoot 'payload'
    foreach($item in (Get-Content (Join-Path $payload 'checksums.json') -Raw | ConvertFrom-Json)) {
        $file=Join-Path $payload ([IO.Path]::GetFileName($item.Path))
        if((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash -ne $item.Hash){throw 'Restored backup checksum mismatch'}
    }
    Invoke-RestoreDocker @('network','create','--internal',$ident) | Out-Null
    Invoke-RestoreDocker @('volume','create',"$ident-db") | Out-Null
    Invoke-RestoreDocker @('volume','create',"$ident-files") | Out-Null
    Invoke-RestoreDocker @('run','-d','--name',$ident,'--network',$ident,'--network-alias','postgres','-e','POSTGRES_USER=kodame','-e','POSTGRES_DB=kodame','-e','POSTGRES_HOST_AUTH_METHOD=trust','-v',"${ident}-db:/var/lib/postgresql/data",$manifest.databaseImage) | Out-Null
    $ready=$false
    for($attempt=0;$attempt -lt 30;$attempt++) {
        & docker exec $ident pg_isready -U kodame -d kodame *> $null
        if($LASTEXITCODE -eq 0){$ready=$true;break}
        Start-Sleep -Seconds 1
    }
    if(-not $ready){throw 'Isolated PostgreSQL did not start'}
    Invoke-RestoreDocker @('exec',$ident,'psql','-U','kodame','-d','kodame','-v','ON_ERROR_STOP=1','-c','DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname=''kodame_app'') THEN CREATE ROLE kodame_app LOGIN; END IF; END $$;') | Out-Null
    Invoke-RestoreDocker @('cp',(Join-Path $payload 'database.dump'),"${ident}:/tmp/database.dump") | Out-Null
    Invoke-RestoreDocker @('exec',$ident,'pg_restore','-U','kodame','-d','kodame','--exit-on-error','/tmp/database.dump') | Out-Null
    Invoke-RestoreDocker @('run','--rm','--network','none','-v',"${payload}:/backup:ro",'-v',"${ident}-files:/app/data",$manifest.databaseImage,'tar','-xzf','/backup/files.tar.gz','-C','/app/data') | Out-Null
    $before=Invoke-RestoreDocker @('exec',$ident,'psql','-U','kodame','-d','kodame','-At','-c',"SELECT json_build_object('projects',(SELECT count(*) FROM projects WHERE NOT is_bootstrap),'documents',(SELECT count(*) FROM intake_documents),'accounts',(SELECT count(*) FROM accounts));")
    Invoke-RestoreDocker @('run','--rm','--network','none','--user','0','-v',"${ident}-files:/app/data",$ApiImage,'chown','-R','10001:10001','/app/data') | Out-Null
    Invoke-RestoreDocker @('run','--rm','--network',$ident,'-e','DATABASE_URL=postgresql://kodame_app:restore-only@postgres:5432/kodame','-e','ADMIN_DATABASE_URL=postgresql://kodame:restore-only@postgres:5432/kodame','-e','KODAME_BOOTSTRAP_PASSWORD=restore-isolated-only','-e','OPENROUTER_API_KEY=','-v',"${ident}-files:/app/data",'-v',"${taskRoot}:/workspace:ro",'-e','PYTHONPATH=/workspace/redesign/backend:/workspace/backend:/app','--entrypoint','python',$ApiImage,'-m','kodame_intake.migrate') | Out-Null
    $after=Invoke-RestoreDocker @('exec',$ident,'psql','-U','kodame','-d','kodame','-At','-c',"SELECT json_build_object('projects',(SELECT count(*) FROM projects WHERE NOT is_bootstrap),'documents',(SELECT count(*) FROM intake_documents),'accounts',(SELECT count(*) FROM accounts));")
    if($before -ne $after){throw 'Migration changed restored entity counts'}
    $versions=Invoke-RestoreDocker @('exec',$ident,'psql','-U','kodame','-d','kodame','-At','-c','SELECT version FROM schema_migrations ORDER BY version;')
    $result=@{status='passed';seconds=[Math]::Round($watch.Elapsed.TotalSeconds,2);backup=$backup;counts=($after|ConvertFrom-Json);migrations=$versions;archiveHashesVerified=$true;network='internal, no published ports';offHost=$false}
    $result|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $checkRoot 'result.json')
    Write-Output ($result|ConvertTo-Json -Depth 6 -Compress)
} finally {
    & docker rm -f $ident *> $null
    & docker volume rm "${ident}-db" "${ident}-files" *> $null
    & docker network rm $ident *> $null
    # Delete only the exact plaintext scratch paths under the verified workspace.
    foreach($scratch in @((Join-Path $checkRoot 'payload'),(Join-Path $checkRoot 'archive.zip'))) {
        $resolved=[IO.Path]::GetFullPath($scratch)
        if(-not $resolved.StartsWith($runtime+[IO.Path]::DirectorySeparatorChar)){throw 'Unsafe cleanup path'}
        if(Test-Path -LiteralPath $resolved){Remove-Item -LiteralPath $resolved -Recurse -Force}
    }
}
