Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$output = Join-Path $root "dist\assets"
New-Item -ItemType Directory -Force -Path $output | Out-Null

function Export-Crop {
    param(
        [string]$Source,
        [string]$Name,
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height
    )

    $image = [System.Drawing.Image]::FromFile((Join-Path $root $Source))
    try {
        $bitmap = New-Object System.Drawing.Bitmap $Width, $Height
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.DrawImage($image, (New-Object System.Drawing.Rectangle 0, 0, $Width, $Height), (New-Object System.Drawing.Rectangle $X, $Y, $Width, $Height), [System.Drawing.GraphicsUnit]::Pixel)
                $bitmap.Save((Join-Path $output $Name), [System.Drawing.Imaging.ImageFormat]::Jpeg)
            }
            finally { $graphics.Dispose() }
        }
        finally { $bitmap.Dispose() }
    }
    finally { $image.Dispose() }
}

Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "hero-soup.jpg" 382 268 458 286
Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "lotus.jpg" 108 651 230 128
Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "pumpkin.jpg" 356 651 230 128
Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "tomato.jpg" 603 651 230 128
Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "bokchoy.jpg" 108 986 230 115
Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "carrot.jpg" 356 986 230 115
Export-Crop "image\82b72c5e33b58b4ac1f11af5de2229a9.png" "egg.jpg" 603 986 230 115
Export-Crop "image\2d6fdd4c-430c-485d-8da1-ab3c22e7cdd8.png" "tomato-egg.jpg" 357 646 233 145
Export-Crop "image\2d6fdd4c-430c-485d-8da1-ab3c22e7cdd8.png" "cabbage.jpg" 108 1040 236 144
Export-Crop "image\2d6fdd4c-430c-485d-8da1-ab3c22e7cdd8.png" "mushroom-chicken.jpg" 602 1040 237 144
Export-Crop "image\a5e2316b-d198-446f-8b96-078cbbec7bc4.png" "avatar.jpg" 135 273 115 115
Export-Crop "image\2d293bf6-7d40-49ce-bc8d-10adf3024126.png" "pantry.jpg" 547 274 287 238

