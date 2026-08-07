param(
    [string]$ImageName = "oda-impactops-flightbase",
    [string]$Tag = "1.0.0",
    [string]$OutputDirectory = "output/docker"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$fullImageName = "${ImageName}:${Tag}"
$outputPath = Join-Path $root $OutputDirectory
$safeFileName = ($ImageName -replace '[^A-Za-z0-9_.-]', '-') + "-${Tag}.tar"
$tarPath = Join-Path $outputPath $safeFileName

Push-Location $root
try {
    docker build --pull --tag $fullImageName .
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }

    docker image inspect $fullImageName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Built image could not be inspected" }

    New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
    docker save --output $tarPath $fullImageName
    if ($LASTEXITCODE -ne 0) { throw "Docker image export failed" }

    $hash = Get-FileHash -LiteralPath $tarPath -Algorithm SHA256
    $checksumPath = "$tarPath.sha256"
    Set-Content -LiteralPath $checksumPath -Value "$($hash.Hash.ToLowerInvariant())  $safeFileName" -Encoding ascii
    [pscustomobject]@{
        Image = $fullImageName
        TarFile = $tarPath
        ChecksumFile = $checksumPath
        SizeMB = [math]::Round((Get-Item -LiteralPath $tarPath).Length / 1MB, 1)
        SHA256 = $hash.Hash
    }
}
finally {
    Pop-Location
}
