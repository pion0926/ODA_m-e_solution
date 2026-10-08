[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$opsRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtimeDir = Join-Path $opsRoot '.runtime'
$envPath = Join-Path $runtimeDir 'production.env'
if (Test-Path -LiteralPath $envPath) { throw 'production.env already exists. It was not overwritten.' }

function New-RandomHex([int]$Bytes) {
    $value = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($value) } finally { $rng.Dispose() }
    return -join ($value | ForEach-Object { $_.ToString('x2') })
}

# Only the explicitly shared AI settings are copied, never the development DB,
# bootstrap password, sessions, project IDs, file paths or public registration.
$ai = @{}
$devEnv = Join-Path $opsRoot '.env'
if (Test-Path -LiteralPath $devEnv) {
    foreach ($line in [IO.File]::ReadAllLines($devEnv)) {
        if ($line -match '^\s*(OPENROUTER_API_KEY|OPENROUTER_MODEL|OPENROUTER_PRESENTATION_MODEL)\s*=(.*)$') {
            $ai[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
}
$lines = @(
    '# Local secret file. Never commit, print compose config, or send this file.'
    'PROD_BIND_IP=127.0.0.1'
    'PROD_PORT=8000'
    'PROD_PUBLIC_URL=http://127.0.0.1:8000'
    'PROD_COOKIE_SECURE=false'
    "PROD_POSTGRES_PASSWORD=$(New-RandomHex 32)"
    "PROD_BOOTSTRAP_PASSWORD=$(New-RandomHex 18)"
)
foreach ($key in @('OPENROUTER_API_KEY', 'OPENROUTER_MODEL', 'OPENROUTER_PRESENTATION_MODEL')) {
    if ($ai.ContainsKey($key)) {
        if ($ai[$key] -match "[\r\n']") { throw "Unsupported quoting in $key. No secret file was written." }
        $lines += "$key='$($ai[$key])'"
    }
}
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
[IO.File]::WriteAllLines($envPath, $lines, (New-Object Text.UTF8Encoding($false)))
Write-Output "Created $envPath (secrets not displayed). Production admin login: admin."
