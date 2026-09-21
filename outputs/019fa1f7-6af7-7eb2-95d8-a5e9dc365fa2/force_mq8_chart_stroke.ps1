param(
  [string]$InputPath = "D:\Github\PertaminaGLD\outputs\019fa1f7-6af7-7eb2-95d8-a5e9dc365fa2\MQ8_REPORT_FIXED_rebuild.xlsx",
  [string]$OutputPath = "D:\Github\PertaminaGLD\outputs\019fa1f7-6af7-7eb2-95d8-a5e9dc365fa2\MQ8_REPORT_FIXED.xlsx"
)

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
Copy-Item -LiteralPath $InputPath -Destination $OutputPath -Force
$zip = [System.IO.Compression.ZipFile]::Open($OutputPath, [System.IO.Compression.ZipArchiveMode]::Update)
try {
  $stroke = '<c:spPr><a:ln w="19050" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:solidFill><a:srgbClr val="1F77B4" /></a:solidFill><a:prstDash val="solid" /></a:ln></c:spPr>'
  $entries = @($zip.Entries | Where-Object { $_.FullName -match '^xl/drawings/charts/chart[2-7]\.xml$' })
  foreach ($entry in $entries) {
    $reader = [System.IO.StreamReader]::new($entry.Open())
    $xml = $reader.ReadToEnd()
    $reader.Close()
    $xml = $xml -replace '(<c:grouping val="standard" />)(?!<c:varyColors)', '$1<c:varyColors val="0" />'
    $xml = $xml -replace '(<c:marker><c:symbol val="none" /></c:marker>)(?!<c:spPr>)', ('$1' + $stroke)
    $entry.Delete()
    $newEntry = $zip.CreateEntry($entry.FullName, [System.IO.Compression.CompressionLevel]::Optimal)
    $writer = [System.IO.StreamWriter]::new($newEntry.Open())
    $writer.Write($xml)
    $writer.Close()
  }
} finally {
  if ($null -ne $zip) { $zip.Dispose() }
}
