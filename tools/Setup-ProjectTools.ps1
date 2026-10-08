[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$directory = Join-Path $taskRoot '.codex'
$target = Join-Path $directory 'config.toml'
$content = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'codex-project.toml') -Raw).Replace('@ROOT@', $taskRoot.Replace('\', '/'))
if (Test-Path -LiteralPath $target) {
    $existing = Get-Content -LiteralPath $target -Raw
    if ($existing.Trim() -eq $content.Trim()) { Write-Output 'Project tooling configuration already current.'; return }
    throw 'Existing project config differs. Merge it explicitly; this installer never overwrites other settings.'
}
New-Item -ItemType Directory -Force -Path $directory | Out-Null
[IO.File]::WriteAllText($target, $content, [Text.UTF8Encoding]::new($false))
Write-Output 'Project web search and MCP configuration installed. Reload the Codex project to activate.'
