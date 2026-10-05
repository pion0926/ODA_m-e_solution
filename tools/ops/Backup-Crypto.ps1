Set-StrictMode -Version Latest
function Get-BackupKey([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        $hex = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(64))
        $secure = ConvertTo-SecureString $hex -AsPlainText -Force
        [IO.File]::WriteAllText($Path, (ConvertFrom-SecureString $secure))
    }
    & icacls $Path /inheritance:r /grant:r "*$([Security.Principal.WindowsIdentity]::GetCurrent().User.Value):(F)" '*S-1-5-18:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot restrict backup key access' }
    $secure = ConvertTo-SecureString ([IO.File]::ReadAllText($Path))
    $value = [Net.NetworkCredential]::new('', $secure).Password
    return [Convert]::FromHexString($value)
}
function Protect-Backup([string]$InputPath, [string]$OutputPath, [byte[]]$Key) {
    $aes = [Security.Cryptography.Aes]::Create()
    $aes.Key = $Key[0..31]; $aes.GenerateIV()
    $inputStream = [IO.File]::OpenRead($InputPath)
    $outputStream = [IO.File]::Create($OutputPath)
    try {
        $outputStream.Write($aes.IV)
        $crypto = [Security.Cryptography.CryptoStream]::new($outputStream,$aes.CreateEncryptor(),[Security.Cryptography.CryptoStreamMode]::Write,$true)
        try { $inputStream.CopyTo($crypto); $crypto.FlushFinalBlock() } finally { $crypto.Dispose() }
    } finally { $inputStream.Dispose(); $outputStream.Dispose(); $aes.Dispose() }
    $mac = [Security.Cryptography.HMACSHA256]::new([byte[]]$Key[32..63])
    $read = [IO.File]::OpenRead($OutputPath)
    try { $tag = $mac.ComputeHash($read) } finally { $read.Dispose(); $mac.Dispose() }
    $append = [IO.File]::Open($OutputPath,[IO.FileMode]::Append)
    try { $append.Write($tag) } finally { $append.Dispose() }
}
function Unprotect-Backup([string]$InputPath, [string]$OutputPath, [byte[]]$Key) {
    $inputStream = [IO.File]::OpenRead($InputPath)
    $aes = [Security.Cryptography.Aes]::Create(); $aes.Key = $Key[0..31]
    try {
        if ($inputStream.Length -lt 64) { throw 'Invalid encrypted backup' }
        $payloadLength = $inputStream.Length - 32
        $mac = [Security.Cryptography.HMACSHA256]::new([byte[]]$Key[32..63])
        $buffer = [byte[]]::new(65536); $remaining = $payloadLength
        while ($remaining -gt 0) { $n=$inputStream.Read($buffer,0,[int][Math]::Min($remaining,$buffer.Length)); if($n -le 0){throw 'Truncated backup'}; $null=$mac.TransformBlock($buffer,0,$n,$buffer,0);$remaining-=$n }
        $null=$mac.TransformFinalBlock([byte[]]::new(0),0,0)
        $expected=[byte[]]::new(32);$null=$inputStream.Read($expected,0,32)
        if (-not [Security.Cryptography.CryptographicOperations]::FixedTimeEquals($expected,$mac.Hash)) { throw 'Backup authentication failed' }
        $mac.Dispose();$inputStream.Position=0
        $iv=[byte[]]::new(16);$null=$inputStream.Read($iv,0,16);$aes.IV=$iv
        $outputStream=[IO.File]::Create($OutputPath)
        $crypto=[Security.Cryptography.CryptoStream]::new($outputStream,$aes.CreateDecryptor(),[Security.Cryptography.CryptoStreamMode]::Write)
        try {
            $remaining=$payloadLength-16
            while($remaining -gt 0){$n=$inputStream.Read($buffer,0,[int][Math]::Min($remaining,$buffer.Length));$crypto.Write($buffer,0,$n);$remaining-=$n}
            $crypto.FlushFinalBlock()
        } finally { $crypto.Dispose();$outputStream.Dispose() }
    } finally { $inputStream.Dispose();$aes.Dispose() }
}
