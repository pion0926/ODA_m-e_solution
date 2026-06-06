param(
    [Parameter(Mandatory = $true)][string]$TemplatePath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$ContentPath
)

$ErrorActionPreference = "Stop"

$hwp = New-Object -ComObject HWPFrame.HwpObject
try {
    $hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule") | Out-Null
    $hwp.Open($TemplatePath, "HWP", "forceopen:true") | Out-Null
    $hwp.Run("MoveDocEnd") | Out-Null
    $hwp.Run("BreakPage") | Out-Null

    $content = Get-Content -LiteralPath $ContentPath -Raw -Encoding UTF8
    $hwp.HAction.GetDefault("InsertText", $hwp.HParameterSet.HInsertText.HSet) | Out-Null
    $hwp.HParameterSet.HInsertText.Text = $content
    $hwp.HAction.Execute("InsertText", $hwp.HParameterSet.HInsertText.HSet) | Out-Null

    $hwp.SaveAs($OutputPath, "HWP", "") | Out-Null
}
finally {
    if ($hwp) {
        $hwp.Quit() | Out-Null
    }
}
