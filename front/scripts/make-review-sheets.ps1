# Build paginated review contact sheets for the bulk-generated ingredient / dish
# images, so every one of the 1090 can be visually verified against its filename.
#
# Each cell shows the global index (red, top-left) AND the english slug from the
# filename (blue, bottom-left) -- so a reviewer can spot "file says blueberry but
# the photo is broccoli" straight off the image, without cross-referencing a list.
#
# Also writes output/review/<kind>-sheet-NN.txt with "<idx>\t<file>\t<name>".
# Pure ASCII.

param(
    [ValidateSet('ingredient', 'dish')]
    [string]$Kind = 'ingredient',
    [int]$Cols = 6,
    [int]$GridRows = 8,
    [int]$CellW = 200,
    [int]$CellH = 125
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root   = "D:\Deepseek Harness\project4"
$outDir = Join-Path $root "team\front\output\review"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$imgDir = Join-Path $root "team\front\mealmind\assets\images"

if ($Kind -eq 'ingredient') {
    $manPath = Join-Path $root "ingredient_image_library\ingredient_image_library\manifest.csv"
    $items = Import-Csv $manPath -Encoding UTF8 |
        ForEach-Object { [pscustomobject]@{ File = [System.IO.Path]::ChangeExtension($_.filename, '.jpg'); Name = $_.name } }
} else {
    $manPath = Join-Path $root "dish_image_library\dish_image_library\manifest.csv"
    $items = Import-Csv $manPath -Encoding UTF8 |
        ForEach-Object { [pscustomobject]@{ File = [System.IO.Path]::ChangeExtension($_.filename, '.jpg'); Name = $_.dish_name } }
}
$items = @($items | Where-Object { Test-Path (Join-Path $imgDir $_.File) })
Write-Host "$Kind : $($items.Count) images to review"

$per   = $Cols * $GridRows
$sheet = 0
for ($i = 0; $i -lt $items.Count; $i += $per) {
    $sheet++
    $last  = [Math]::Min($i + $per - 1, $items.Count - 1)
    $batch = @($items[$i..$last])

    $bmp = New-Object System.Drawing.Bitmap ($Cols * $CellW), ($GridRows * $CellH)
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
            $g.Clear([System.Drawing.Color]::White)
            $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $idxFont  = New-Object System.Drawing.Font('Arial', 15, [System.Drawing.FontStyle]::Bold)
            $slugFont = New-Object System.Drawing.Font('Arial', 10, [System.Drawing.FontStyle]::Bold)
            $pen      = New-Object System.Drawing.Pen ([System.Drawing.Color]::Red), 2
            $red      = [System.Drawing.Brushes]::Red
            $blue     = [System.Drawing.Brushes]::Blue

            for ($k = 0; $k -lt $batch.Count; $k++) {
                $cx = ($k % $Cols) * $CellW
                $cy = [int][Math]::Floor($k / $Cols) * $CellH
                $img = [System.Drawing.Image]::FromFile((Join-Path $imgDir $batch[$k].File))
                try {
                    $sc = [Math]::Min($CellW / $img.Width, $CellH / $img.Height)
                    $dw = [int]($img.Width * $sc); $dh = [int]($img.Height * $sc)
                    $g.DrawImage($img, ($cx + [int](($CellW - $dw) / 2)), ($cy + [int](($CellH - $dh) / 2)), $dw, $dh)
                } finally { $img.Dispose() }

                $g.DrawRectangle($pen, $cx, $cy, $CellW - 1, $CellH - 1)
                $g.DrawString(($i + $k + 1).ToString(), $idxFont, $red, ($cx + 4), ($cy + 2))

                $slug = ($batch[$k].File -replace '^(food|dish)-\d+-', '') -replace '\.jpg$', ''
                if ($slug.Length -gt 26) { $slug = $slug.Substring(0, 26) }
                $g.DrawString($slug, $slugFont, $blue, ($cx + 4), ($cy + $CellH - 17))
            }
            $idxFont.Dispose(); $slugFont.Dispose(); $pen.Dispose()
        } finally { $g.Dispose() }

        $png = Join-Path $outDir ("{0}-sheet-{1:D2}.png" -f $Kind, $sheet)
        $bmp.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)

        $lines = for ($k = 0; $k -lt $batch.Count; $k++) {
            "{0}`t{1}`t{2}" -f ($i + $k + 1), $batch[$k].File, $batch[$k].Name
        }
        Set-Content -Path (Join-Path $outDir ("{0}-sheet-{1:D2}.txt" -f $Kind, $sheet)) -Value $lines -Encoding UTF8
        Write-Host "  sheet $sheet : $($batch.Count) cells"
    } finally { $bmp.Dispose() }
}
