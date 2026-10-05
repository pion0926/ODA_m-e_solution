[CmdletBinding()]
param([switch]$SkipBuild, [switch]$SkipBrowserTests)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$qaOutput = Join-Path $taskRoot ('.runtime/service-tests/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $qaOutput | Out-Null
Push-Location $taskRoot
try {
    if (-not $SkipBuild) {
        & docker compose -f compose.qa.yml build kodame-redesign-api kodame-redesign-web
        if ($LASTEXITCODE -ne 0) { throw 'QA image build failed' }
    }
    # No production mount, no paid AI key, no dependency startup.
    & docker compose -f compose.qa.yml run --rm --no-deps -e OPENROUTER_API_KEY= -e AI_GLOBAL_BUDGET_ENABLED=false -e PARSER_ISOLATION=false -e REPORT_QUALITY_PROFILE_PATH=/workspace/config/report_quality_profile.json -v "${taskRoot}:/workspace:ro" -v "${qaOutput}:/qa" -w /workspace -e PYTHONPATH=/workspace/redesign/backend:/workspace/backend:/workspace --entrypoint sh kodame-redesign-api -c 'pip install --quiet --target /tmp/testdeps -r redesign/backend/requirements-test.txt && PYTHONPATH=/tmp/testdeps:$PYTHONPATH python -m pytest -q -p no:cacheprovider --tb=short --junitxml=/qa/backend.xml redesign/backend/tests'
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
    & node --test --test-isolation=none redesign/frontend/test_*.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
    if (-not $SkipBrowserTests) {
        & npm ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Playwright dependency installation failed' }
        & npx playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Playwright browser installation failed' }
        & npm run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Browser regression tests failed' }
    }
} finally {
    Pop-Location
}
