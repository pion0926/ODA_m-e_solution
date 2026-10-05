[CmdletBinding()]
param([string]$Version='V2.2.0', [ValidateSet('api','web','kordoc')][string[]]$Components=@('api','web'))
$ErrorActionPreference='Stop'
$opsRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime=Join-Path $opsRoot '.runtime'
$previous=Get-Content (Join-Path $runtime 'production-release.json') -Raw | ConvertFrom-Json
# The current Compose requires the migration and durable workflow entrypoints.
# Reject web-only promotion against an older API before replacing release locks.
$candidateApi=if ('api' -in $Components) { 'odame-dev/api:latest' } else { $previous.images.api.imageId }
& docker run --rm --network none --entrypoint python $candidateApi -c 'import importlib.util; assert all(importlib.util.find_spec("kodame_intake."+name) for name in ("migrate","workflow_worker")), "API image does not support the current Compose; promote api and web together"'
if ($LASTEXITCODE -ne 0) { throw 'Release preflight failed: API image is incompatible with current Compose.' }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$release=Join-Path $runtime "releases/$Version-validated-$stamp"
New-Item -ItemType Directory -Path $release | Out-Null
function Checked([string[]]$ArgsList) { & docker @ArgsList; if ($LASTEXITCODE -ne 0) { throw 'Docker operation failed' } }
Copy-Item -LiteralPath (Join-Path $opsRoot 'compose.production.yml') -Destination $release
Copy-Item -LiteralPath (Join-Path $runtime 'production-release.json') -Destination (Join-Path $release 'previous-release.json')
Copy-Item -LiteralPath (Join-Path $runtime 'production-images.env') -Destination (Join-Path $release 'previous-images.env')
$images=[ordered]@{}
foreach ($component in @('api','web','kordoc','postgres')) {
    if ($component -in $Components) {
        $source=(& docker image inspect --format '{{.Id}}' "odame-dev/${component}:latest").Trim()
        if ($LASTEXITCODE -ne 0 -or $source -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Missing validated source image' }
        $revision="validated-$source"
        $tag="odame-release/${component}:$($Version.Substring(1))-$stamp"
        $baseTag="odame-validated/${component}:$($source.Substring(7))"
        Checked @('tag',$source,$baseTag)
        $recipe=Join-Path $release "Dockerfile.$component"
        [IO.File]::WriteAllText($recipe,"FROM $baseTag`nLABEL org.opencontainers.image.version=`"$Version`" org.opencontainers.image.revision=`"$revision`"`n",[Text.UTF8Encoding]::new($false))
        Checked @('build','--network','none','-f',$recipe,'-t',$tag,$release)
        $image=(& docker image inspect --format '{{.Id}}' $tag).Trim()
        $images[$component]=@{tag=$tag;imageId=$image;sourceRevision=$revision;validatedSourceImage=$source}
        # Keep the actual baked application files with the release, including
        # uncommitted changes tested in development. No running data volume is read.
        $container=(& docker create --network none $source).Trim()
        try {
            if ($component -eq 'kordoc') {
                # node_modules contains Linux symlinks which Docker cannot
                # materialize on unprivileged Windows. The immutable image
                # retains dependencies; archive the app and exact lockfile.
                $destination=Join-Path $release 'kordoc-runtime'
                New-Item -ItemType Directory -Path $destination | Out-Null
                foreach ($file in @('package.json','package-lock.json','server.mjs')) {
                    Checked @('cp',"${container}:/app/$file",(Join-Path $destination $file))
                }
            } else {
                $sourcePath=if ($component -eq 'api') { '/app' } else { '/usr/share/nginx/html' }
                Checked @('cp',"${container}:$sourcePath",(Join-Path $release "$component-runtime"))
            }
        } finally { Checked @('rm','-v',$container) }
    } else {
        $entry=$previous.images.$component
        $revision=(& docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' $entry.imageId).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Missing existing infrastructure image' }
        $images[$component]=@{tag=$entry.tag;imageId=$entry.imageId;sourceRevision=$revision}
    }
}
$manifest=[ordered]@{version=$Version;commit=(& git -C $opsRoot rev-parse HEAD).Trim();sourceState='validated working-tree images';sourceDir=$release;builtAt=(Get-Date).ToUniversalTime().ToString('o');previousRelease=$previous.sourceDir;images=$images}
$locks=@('# Immutable validated images; infrastructure images preserved')
foreach($component in $images.Keys) { $locks+="PROD_$($component.ToUpperInvariant())_IMAGE=$($images[$component].imageId)" }
[IO.File]::WriteAllLines((Join-Path $runtime 'production-images.env'),$locks,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $runtime 'production-release.json'),($manifest|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
Write-Output "Prepared immutable production release: $release"
