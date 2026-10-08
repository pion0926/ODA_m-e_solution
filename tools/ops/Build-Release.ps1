[CmdletBinding()]
param(
    [ValidatePattern('^V\d+\.\d+\.\d+$')][string]$Version = 'V1.0.0',
    [string]$GitRef = 'V1.0.0'
)
$ErrorActionPreference = 'Stop'
$opsRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}
Push-Location $opsRoot
try {
    $commit = (& git rev-parse --verify "$GitRef^{commit}").Trim()
    if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[a-f0-9]{40}$') { throw 'Release ref must resolve to a committed revision.' }
    $runtimeDir = Join-Path $opsRoot '.runtime'
    $sourceDir = Join-Path $runtimeDir "releases/$Version-$($commit.Substring(0,12))"
    $archivePath = Join-Path $runtimeDir "releases/$Version-$($commit.Substring(0,12)).zip"
    $sourceMarker = Join-Path $sourceDir '.source-commit'
    if (Test-Path -LiteralPath $sourceDir) {
        if (-not (Test-Path -LiteralPath $sourceMarker) -or ([IO.File]::ReadAllText($sourceMarker)).Trim() -ne $commit) {
            throw 'Incomplete or mismatched release source. No overwrite performed; inspect .runtime/releases.'
        }
    } else {
        New-Item -ItemType Directory -Path $sourceDir -Force | Out-Null
        Invoke-Checked git @('archive', '--format=zip', "--output=$archivePath", $commit)
        # Windows tar interprets Korean entry names through the local code page.
        # Git ZIP + explicit UTF-8 preserves every template/prompt filename.
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($archivePath, $sourceDir, [Text.Encoding]::UTF8)
        [IO.File]::WriteAllText($sourceMarker, $commit, (New-Object Text.UTF8Encoding($false)))
    }
    $components = [ordered]@{
        api = 'redesign/backend/Dockerfile'
        web = 'redesign/frontend/Dockerfile'
        kordoc = 'redesign/kordoc/Dockerfile'
        postgres = 'redesign/postgres/Dockerfile'
    }
    $locks = @("# $Version commit $commit - content-addressed local images")
    $images = [ordered]@{}
    foreach ($component in $components.Keys) {
        $tag = "odame-release/${component}:$($Version.Substring(1))-$($commit.Substring(0,12))"
        $existing = & docker image ls --quiet $tag
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Docker images.' }
        if ($existing) {
            $existingRevision = & docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' $tag
            if ($LASTEXITCODE -ne 0 -or $existingRevision -ne $commit) { throw "Immutable release tag exists for a different commit: $tag. Refusing to replace it." }
            Write-Output "Reusing already built immutable image: $tag"
        } else {
            Invoke-Checked docker @('build', '--label', "org.opencontainers.image.version=$Version", '--label', "org.opencontainers.image.revision=$commit", '--tag', $tag, '--file', (Join-Path $sourceDir $components[$component]), $sourceDir)
        }
        $imageId = (& docker image inspect --format '{{.Id}}' $tag).Trim()
        if ($LASTEXITCODE -ne 0 -or $imageId -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid built image ID.' }
        $locks += "PROD_$($component.ToUpperInvariant())_IMAGE=$imageId"
        $images[$component] = @{ tag = $tag; imageId = $imageId }
    }
    [IO.File]::WriteAllLines((Join-Path $runtimeDir 'production-images.env'), $locks, (New-Object Text.UTF8Encoding($false)))
    $manifest = [ordered]@{ version = $Version; commit = $commit; sourceDir = $sourceDir; builtAt = (Get-Date).ToUniversalTime().ToString('o'); images = $images }
    [IO.File]::WriteAllText((Join-Path $runtimeDir 'production-release.json'), ($manifest | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
    Write-Output "Release $Version pinned to $commit. Image lock and manifest created in .runtime."
} finally { Pop-Location }
