[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $taskRoot '.runtime'
$source = Join-Path $runtime 'cloudflare-prod-install.txt'
$destination = Join-Path $runtime 'cloudflared-prod.token'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw 'Save the Cloudflare Docker install command in .runtime/cloudflare-prod-install.txt first. Do not paste it into chat.'
}
$raw = [IO.File]::ReadAllText($source).Trim()
$found = [regex]::Matches($raw, '(?:--token\s+|^)(eyJ[A-Za-z0-9_+/=-]+)')
if ($found.Count -ne 1) { throw 'Expected exactly one unmasked tunnel token.' }
$token = $found[0].Groups[1].Value
try {
    $base64 = $token.Replace('-', '+').Replace('_', '/')
    $base64 = $base64.PadRight([int]([Math]::Ceiling($base64.Length / 4.0) * 4), '=')
    $claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($base64)) | ConvertFrom-Json
} catch { throw 'The token could not be validated. No credentials were printed.' }
if ($claims.t -ne 'a028b2e2-1761-4994-8a2c-de1de93498de' -or
    $claims.a -ne 'a6a44e07bcdd904b238c669e01492436' -or -not $claims.s) {
    throw 'Token does not belong to the approved kodame-prod tunnel/account.'
}
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
function Protect-PrivateFile([string]$Path) {
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetOwner($currentSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($currentSid, $systemSid)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}
# Credential storage is runtime data; it is ignored by git and never printed.
if (-not (Test-Path -LiteralPath $destination)) { [IO.File]::WriteAllText($destination, '') }
Protect-PrivateFile $destination
Protect-PrivateFile $source
[IO.File]::WriteAllText($destination, $token, [Text.UTF8Encoding]::new($false))
$raw = $null; $token = $null; $base64 = $null; $claims = $null; $found = $null
Write-Output 'Approved production tunnel token saved to private runtime storage. No network connection was started.'
