# Bulk-generate web-sized jpgs for EVERY ingredient (590) and EVERY dish (500)
# from the two image libraries, so nothing falls back to a generic category photo.
#
# Naming follows the libraries' own manifest filenames, only the extension changes:
#   ingredient_image_library/food-0001-scallion.png -> assets/images/food-0001-scallion.jpg
#   dish_image_library/dish-026598-....png          -> assets/images/dish-026598-....jpg
#
# The libraries are NOT trustworthy: full visual review found ~17% of the sampled
# PNGs contain a different ingredient than their filename claims. $sourceOverride
# below records every confirmed mismatch as "target file -> file that really holds
# that content". $skip lists targets with no usable source anywhere.
#
# Pure ASCII on purpose (the Chinese strings are read from the CSVs at runtime).

param(
    [ValidateSet('ingredient', 'dish', 'all')]
    [string]$Kind = 'all',
    [switch]$Apply,
    [int]$Width = 480,
    [int]$Height = 300,
    [int]$Quality = 78
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root      = "D:\Deepseek Harness\project4"
$ingSrcDir = Join-Path $root "ingredient_image_library\ingredient_image_library"
$ingMan    = Join-Path $ingSrcDir "manifest.csv"
$dishSrcDir = Join-Path $root "dish_image_library\dish_image_library"
$dishMan   = Join-Path $dishSrcDir "manifest.csv"
$outDir    = Join-Path $root "team\front\mealmind\assets\images"

# --- confirmed content mismatches: target file -> file that actually has it -------
$sourceOverride = @{
    'food-0055-blueberry.png'  = 'food-0056-apple.png'      # holds blueberry
    'food-0053-broccoli.png'   = 'food-0055-blueberry.png'  # holds broccoli
    'food-0051-basil.png'      = 'food-0053-broccoli.png'   # holds basil
    'food-0043-strawberry.png' = 'food-0051-basil.png'      # holds strawberry
    'food-0042-mango.png'      = 'food-0043-strawberry.png' # holds mango
    'food-0061-banana.png'     = 'food-0063-daikon.png'     # holds banana
    'food-0063-daikon.png'     = 'food-0061-banana.png'     # holds daikon
    # food-0056-apple.png itself holds blueberries, so borrow the real apple photo
    # that the library also ships under a variety name.
    'food-0056-apple.png'      = 'food-0565-guoguang-apple.png'
}
# Nothing is skipped any more: every target has a verified source image.
$skip = @()

function Emit-Jpgs {
    param(
        [string]$SrcDir,
        [object[]]$Rows,          # objects with .filename
        [string]$Label
    )

    $jpgCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
                Where-Object { $_.MimeType -eq 'image/jpeg' }
    $encParams = New-Object System.Drawing.Imaging.EncoderParameters 1
    $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
        [System.Drawing.Imaging.Encoder]::Quality, [int64]$Quality)

    $made = 0; $skipped = 0; $missing = @()
    foreach ($r in $Rows) {
        $target = $r.filename
        if ($skip -contains $target) { $skipped++; continue }
        $src = if ($sourceOverride.ContainsKey($target)) { $sourceOverride[$target] } else { $target }
        $srcPath = Join-Path $SrcDir $src
        if (-not (Test-Path $srcPath)) { $missing += $target; continue }

        $outName = [System.IO.Path]::ChangeExtension($target, '.jpg')
        $outPath = Join-Path $outDir $outName

        $img = [System.Drawing.Image]::FromFile($srcPath)
        try {
            $bmp = New-Object System.Drawing.Bitmap $Width, $Height
            try {
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                try {
                    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                    $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                    $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                    # cover-crop
                    $scale = [Math]::Max($Width / $img.Width, $Height / $img.Height)
                    $sw = [int][Math]::Round($Width  / $scale)
                    $sh = [int][Math]::Round($Height / $scale)
                    $sx = [int](($img.Width  - $sw) / 2)
                    $sy = [int](($img.Height - $sh) / 2)
                    $g.DrawImage($img,
                        (New-Object System.Drawing.Rectangle 0, 0, $Width, $Height),
                        (New-Object System.Drawing.Rectangle $sx, $sy, $sw, $sh),
                        [System.Drawing.GraphicsUnit]::Pixel)
                    $bmp.Save($outPath, $jpgCodec, $encParams)
                    $made++
                } finally { $g.Dispose() }
            } finally { $bmp.Dispose() }
        } finally { $img.Dispose() }
    }
    Write-Host ("[{0}] rows={1} wrote={2} skipped={3} missing={4}" -f $Label, $Rows.Count, $made, $skipped, $missing.Count)
    if ($missing.Count) { Write-Host ("[{0}] MISSING: {1}" -f $Label, ($missing -join ', ')) -ForegroundColor Red }

    $sum = (Get-ChildItem $outDir -Filter ($(if ($Label -eq 'ingredient') { 'food-*.jpg' } else { 'dish-*.jpg' })) |
            Measure-Object Length -Sum).Sum
    Write-Host ("[{0}] total on disk: {1:N2} MB" -f $Label, ($sum / 1MB))
}

if ($Kind -in @('ingredient', 'all')) {
    $all = Import-Csv $ingMan -Encoding UTF8
    Write-Host "ingredient library: $($all.Count) rows"
    if ($Apply) { Emit-Jpgs -SrcDir $ingSrcDir -Rows $all -Label 'ingredient' }
    else { $all | Select-Object -First 5 name, filename | Format-Table -AutoSize }
}

if ($Kind -in @('dish', 'all')) {
    $all = Import-Csv $dishMan -Encoding UTF8
    Write-Host "dish library: $($all.Count) rows"
    if ($Apply) { Emit-Jpgs -SrcDir $dishSrcDir -Rows $all -Label 'dish' }
    else { $all | Select-Object -First 5 dish_name, filename | Format-Table -AutoSize }
}
