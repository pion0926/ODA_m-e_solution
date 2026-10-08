param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Download', 'Upload')]
    [string]$Mode,
    [string]$ManifestPath = 'data-redesign/drive-import/manifest.json',
    [string]$ApiBaseUrl = 'http://127.0.0.1:8002'
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath '.').Path
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath | ConvertFrom-Json
$stagingRoot = Join-Path $workspaceRoot 'data-redesign\drive-import\files'
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

$mimeExtensions = @{
    'application/pdf' = '.pdf'
    'text/markdown' = '.md'
    'text/plain' = '.txt'
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' = '.xlsx'
    'application/x-zip-compressed' = '.zip'
}

function ConvertFrom-Utf8Mojibake([string]$Value) {
    try {
        return [Text.Encoding]::UTF8.GetString([Text.Encoding]::GetEncoding(28591).GetBytes($Value))
    }
    catch {
        return $Value
    }
}

function Get-SafeName([string]$Folder, [string]$Title, [string]$MimeType) {
    $name = "$Folder`__$Title" -replace '[,;<>:"/\\|?*\x00-\x1f]', '_'
    $extension = [IO.Path]::GetExtension($name)
    if (-not $extension -and $mimeExtensions.ContainsKey($MimeType)) {
        $name += $mimeExtensions[$MimeType]
    }
    return $name.Trim(' ', '.')
}

if ($Mode -eq 'Download') {
    $downloaded = 0
    foreach ($file in $manifest.files) {
        $safeName = Get-SafeName $file.folder $file.title $file.mime_type
        $target = Join-Path $stagingRoot $safeName
        $expectedSize = [int64]$file.size
        if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target).Length -eq $expectedSize)) {
            $downloaded++
            Write-Output "SKIP $downloaded/$($manifest.files.Count) $safeName"
            continue
        }
        $temporary = "$target.part"
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        $url = "https://drive.usercontent.google.com/download?id=$($file.id)&export=download&confirm=t"
        Write-Output "DOWNLOAD $($downloaded + 1)/$($manifest.files.Count) $safeName"
        & curl.exe -L --fail --silent --show-error --retry 5 --retry-all-errors --connect-timeout 30 --max-time 900 $url -o $temporary
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $safeName" }
        $actualSize = (Get-Item -LiteralPath $temporary).Length
        if ($expectedSize -gt 0 -and $actualSize -ne $expectedSize) {
            throw "Size mismatch: $safeName expected=$expectedSize actual=$actualSize"
        }
        Move-Item -LiteralPath $temporary -Destination $target -Force
        $downloaded++
    }
    Write-Output "DOWNLOAD_COMPLETE count=$downloaded"
    exit 0
}

$existingResponse = Invoke-RestMethod -Uri "$ApiBaseUrl/api/v2/intake/jobs?limit=200" -TimeoutSec 30
$existing = @{}
foreach ($job in $existingResponse.items) {
    $decodedName = ConvertFrom-Utf8Mojibake $job.file_name
    $existing["$decodedName|$($job.sha256)|$($job.size_bytes)"] = $true
}
$uploaded = 0
foreach ($file in $manifest.files) {
    $safeName = Get-SafeName $file.folder $file.title $file.mime_type
    $source = Join-Path $stagingRoot $safeName
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing staged file: $safeName" }
    $sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
    $databaseName = if ($safeName.Length -gt 180) { $safeName.Substring(0, 180) } else { $safeName }
    $key = "$databaseName|$sha256|$($file.size)"
    if ($existing.ContainsKey($key)) {
        $uploaded++
        Write-Output "SKIP_UPLOAD $uploaded/$($manifest.files.Count) $safeName"
        continue
    }
    Write-Output "UPLOAD $($uploaded + 1)/$($manifest.files.Count) $safeName"
    $response = & curl.exe --fail --silent --show-error --retry 3 --retry-all-errors --connect-timeout 15 --max-time 900 -X POST -F "files=@$source;type=$($file.mime_type)" "$ApiBaseUrl/api/v2/intake/uploads"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed: $safeName" }
    $result = $response | ConvertFrom-Json
    if ($result.count -ne 1) { throw "Unexpected API response: $safeName" }
    $uploaded++
}
Write-Output "UPLOAD_COMPLETE count=$uploaded"
