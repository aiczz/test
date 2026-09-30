# Build contact sheets of the generated ingredient-*-wide.jpg so a human/vision model
# can verify every one in a couple of glances. Read-only apart from the output pngs.
# Pure ASCII on purpose.

param(
    [int]$Cols  = 6,
    [int]$Rows  = 4,
    [int]$CellW = 200,
    [int]$CellH = 125
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$jpgDir = "D:\Deepseek Harness\project4\team\front\mealmind\assets\images"
$outDir = "D:\Deepseek Harness\project4\team\front\output\contact"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$files = Get-ChildItem $jpgDir -Filter 'ingredient-*-wide.jpg' | Sort-Object Name
Write-Host "images: $($files.Count)"

$per   = $Cols * $Rows
$sheet = 0

for ($i = 0; $i -lt $files.Count; $i += $per) {
    $sheet++
    $last  = [Math]::Min($i + $per - 1, $files.Count - 1)
    $batch = @($files[$i..$last])

    $W = $Cols * $CellW
    $H = $Rows * $CellH
    $bmp = New-Object System.Drawing.Bitmap $W, $H
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
            $g.Clear([System.Drawing.Color]::White)
            $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $font  = New-Object System.Drawing.Font('Arial', 16, [System.Drawing.FontStyle]::Bold)
            $pen   = New-Object System.Drawing.Pen ([System.Drawing.Color]::Red), 2
            $brush = [System.Drawing.Brushes]::Red

            for ($k = 0; $k -lt $batch.Count; $k++) {
                $cx = ($k % $Cols) * $CellW
                $cy = [int][Math]::Floor($k / $Cols) * $CellH

                $img = [System.Drawing.Image]::FromFile($batch[$k].FullName)
                try {
                    # fit inside the cell, keep aspect
                    $sc  = [Math]::Min($CellW / $img.Width, $CellH / $img.Height)
                    $dw  = [int]($img.Width  * $sc)
                    $dh  = [int]($img.Height * $sc)
                    $dx  = $cx + [int](($CellW - $dw) / 2)
                    $dy  = $cy + [int](($CellH - $dh) / 2)
                    $g.DrawImage($img, $dx, $dy, $dw, $dh)
                } finally { $img.Dispose() }

                $g.DrawRectangle($pen, $cx, $cy, $CellW - 1, $CellH - 1)
                $g.DrawString(($i + $k + 1).ToString(), $font, $brush, ($cx + 5), ($cy + 3))
            }
            $font.Dispose(); $pen.Dispose()
        } finally { $g.Dispose() }

        $out = Join-Path $outDir ("contact-{0}.png" -f $sheet)
        $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        Write-Host "wrote $out"
    } finally { $bmp.Dispose() }
}

Write-Host ""
Write-Host "=== index -> file ==="
for ($i = 0; $i -lt $files.Count; $i++) {
    "{0,3}  {1}" -f ($i + 1), ($files[$i].Name -replace '^ingredient-', '' -replace '-wide\.jpg$', '')
}
