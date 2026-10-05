[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('foundation','facts','dac','report','resume','export','gold','scope')][string]$Stage,
      [string]$OutputDirectory='.runtime/workflow-improvements-20260925')
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$qaKeyLine=Get-Content -LiteralPath (Join-Path $taskRoot '.env') | Where-Object { $_ -match '^OPENROUTER_API_KEY=' } | Select-Object -First 1
if (-not $qaKeyLine) { throw 'Development provider key is not configured' }
$previousKey=$env:OPENROUTER_API_KEY
try {
    $env:OPENROUTER_API_KEY=$qaKeyLine.Substring('OPENROUTER_API_KEY='.Length).Trim().Trim('"').Trim("'")
    if (-not $env:OPENROUTER_API_KEY) { throw 'Development provider key is empty' }
    $qaOutput=[IO.Path]::GetFullPath((Join-Path $taskRoot $OutputDirectory))
    if (-not $qaOutput.StartsWith((Join-Path $taskRoot '.runtime')+[IO.Path]::DirectorySeparatorChar)) { throw 'QA output must be inside workspace .runtime' }
    $probeArguments = @('/workspace/tools/qa_service_live_synthetic.py', $Stage)
    if ($Stage -eq 'gold') { $probeArguments = @('/workspace/tools/qa_improvements_live.py') }
    if ($Stage -eq 'scope') { $probeArguments = @('/workspace/tools/qa_dac_scope_comparison.py') }
    & docker compose -f (Join-Path $taskRoot 'compose.qa.yml') run --rm --no-deps -e KODAME_QA=1 -e OPENROUTER_API_KEY -v "${taskRoot}:/workspace:ro" -v "${qaOutput}:/qa" -e PYTHONPATH=/workspace/redesign/backend:/workspace/backend:/app:/workspace --entrypoint python kodame-redesign-api @probeArguments
    if ($LASTEXITCODE -ne 0) { throw "Synthetic $Stage probe failed" }
} finally {
    $env:OPENROUTER_API_KEY=$previousKey
}
