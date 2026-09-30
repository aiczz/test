# Map the ingredient-*-wide.png references in backend_api.dart to the real PNGs in
# ingredient_image_library, joining on the Chinese name via manifest.csv.
# Read-only analysis unless -Apply is passed (then it writes the jpgs).
# NOTE: keep this file pure ASCII -- only ASCII literals are used here, the Chinese
# strings are read out of backend_api.dart / manifest.csv at runtime.

param(
    [switch]$Apply,
    [int]$Width = 480,
    [int]$Height = 300,
    [int]$Quality = 82
)

$ErrorActionPreference = 'Stop'

$root     = "D:\Deepseek Harness\project4"
$dartPath = Join-Path $root "team\front\mealmind\lib\services\backend_api.dart"
$manPath  = Join-Path $root "ingredient_image_library\ingredient_image_library\manifest.csv"
$srcDir   = Join-Path $root "ingredient_image_library\ingredient_image_library"
$outDir   = Join-Path $root "team\front\mealmind\assets\images"

# ---------------------------------------------------------------- 1. parse Dart
$dart  = Get-Content $dartPath -Raw -Encoding UTF8
$start = $dart.IndexOf('const generated =')
if ($start -lt 0) { throw "cannot find 'const generated' list" }
$end   = $dart.IndexOf('];', $start)
if ($end -lt 0) { throw "cannot find end of generated list" }
$block = $dart.Substring($start, $end - $start)

$refs    = [System.Collections.Generic.List[object]]::new()
$pending = $null
foreach ($ln in ($block -split "`r?`n")) {
    $km = [regex]::Match($ln, "keywords:\s*\[([^\]]*)\]")
    $am = [regex]::Match($ln, "asset:\s*'([^']+)'")
    if ($km.Success) {
        $pending = @($km.Groups[1].Value -split ',' |
                     ForEach-Object { $_.Trim().Trim("'").Trim('"') } |
                     Where-Object { $_ })
    }
    if ($am.Success -and $pending) {
        $refs.Add([pscustomobject]@{
            Asset    = $am.Groups[1].Value
            Keywords = $pending
        })
        $pending = $null
    }
}
Write-Host "Dart references : $($refs.Count) -wide.png entries" -ForegroundColor Cyan

# ---------------------------------------------------------------- 2. read manifest
$man = Import-Csv $manPath -Encoding UTF8
Write-Host "manifest.csv    : $($man.Count) ingredients" -ForegroundColor Cyan

# ---------------------------------------------------------------- 3. build mapping
$map     = [System.Collections.Generic.List[object]]::new()
$missing = [System.Collections.Generic.List[object]]::new()

foreach ($r in $refs) {
    $hit = $null
    $via = $null
    foreach ($k in $r.Keywords) {
        $cand = $man | Where-Object { $_.name -eq $k } | Select-Object -First 1
        if ($cand) { $hit = $cand; $via = $k; break }
    }
    if ($hit) {
        $map.Add([pscustomobject]@{
            Asset   = $r.Asset
            Keyword = $via
            Src     = $hit.filename
            Exists  = (Test-Path (Join-Path $srcDir $hit.filename))
        })
    } else {
        $missing.Add([pscustomobject]@{
            Asset    = $r.Asset
            Keywords = ($r.Keywords -join '/')
        })
    }
}

# --- Verified corrections -------------------------------------------------------
# The library's PNG *contents* do not always match their manifest names. Every
# entry below was checked one by one with a vision model, and the mapping was
# rewritten to point at the file that actually CONTAINS the right ingredient:
#
#   food-0056-apple.png      actually contains  blueberry     (id 55)
#   food-0055-blueberry.png  actually contains  broccoli      (id 53)
#   food-0053-broccoli.png   actually contains  basil         (id 51)
#   food-0051-basil.png      actually contains  strawberry    (id 43)
#   food-0043-strawberry.png actually contains  mango         (id 42)
#   food-0042-mango.png      actually contains  cherry tomato (id 39, correct there)
#   food-0063-daikon.png     actually contains  banana        (id 61)
#   food-0061-banana.png     actually contains  daikon        (id 63)
#
# apple has no source image anywhere in the library, so its rule is skipped here
# and the Dart side drops the keyword (it falls back to the category default).
$overrides = @{
    'assets/images/ingredient-blueberry-wide.jpg'  = 'food-0056-apple.png'
    'assets/images/ingredient-broccoli-wide.jpg'   = 'food-0055-blueberry.png'
    'assets/images/ingredient-basil-wide.jpg'      = 'food-0053-broccoli.png'
    'assets/images/ingredient-strawberry-wide.jpg' = 'food-0051-basil.png'
    'assets/images/ingredient-mango-wide.jpg'      = 'food-0043-strawberry.png'
    'assets/images/ingredient-banana-wide.jpg'     = 'food-0063-daikon.png'
    'assets/images/ingredient-radish-wide.jpg'     = 'food-0061-banana.png'
}
$skip = @('assets/images/ingredient-apple-wide.jpg')

foreach ($m in $map) {
    if ($overrides.ContainsKey($m.Asset)) {
        $m.Src     = $overrides[$m.Asset]
        $m.Keyword = 'VERIFIED'
        $m.Exists  = Test-Path (Join-Path $srcDir $m.Src)
    }
}

$ok   = @($map | Where-Object { $_.Exists -and ($skip -notcontains $_.Asset) })
$dead = @($map | Where-Object { -not $_.Exists })

Write-Host ""
Write-Host "MATCHED + source present : $($ok.Count)" -ForegroundColor Green
$ok | Format-Table Asset, Keyword, Src -AutoSize

if ($dead.Count) {
    Write-Host "MATCHED but PNG missing on disk : $($dead.Count)" -ForegroundColor Yellow
    $dead | Format-Table Asset, Src -AutoSize
}
if ($missing.Count) {
    Write-Host "NO manifest hit for any keyword : $($missing.Count)" -ForegroundColor Red
    $missing | Format-Table Asset, Keywords -AutoSize
}

# ---------------------------------------------------------------- 4. emit jpgs
if ($Apply) {
    Add-Type -AssemblyName System.Drawing
    $jpgCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
                Where-Object { $_.MimeType -eq 'image/jpeg' }
    $encParams = New-Object System.Drawing.Imaging.EncoderParameters 1
    $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
        [System.Drawing.Imaging.Encoder]::Quality, [int64]$Quality)

    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $made = 0
    foreach ($m in $ok) {
        $outName = Split-Path ($m.Asset -replace '\.png$', '.jpg') -Leaf
        $outPath = Join-Path $outDir $outName
        $img = [System.Drawing.Image]::FromFile((Join-Path $srcDir $m.Src))
        try {
            $bmp = New-Object System.Drawing.Bitmap $Width, $Height
            try {
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                try {
                    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                    $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                    $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality

                    # cover-crop: scale to fill, then centre-crop the overflow
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
    Write-Host ""
    Write-Host "wrote $made jpgs to $outDir" -ForegroundColor Green
    $sum = (Get-ChildItem $outDir -Filter 'ingredient-*-wide.jpg' |
            Measure-Object Length -Sum).Sum
    Write-Host ("total {0:N2} MB" -f ($sum / 1MB)) -ForegroundColor Green
}
