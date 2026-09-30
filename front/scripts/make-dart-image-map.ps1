# Generate the two Dart lookup tables that connect backend names to the bundled
# web-sized jpgs, so no ingredient or dish has to fall back to a generic photo.
#
#   lib/data/ingredient_images.dart   kIngredientImageByName : 590 entries
#   lib/data/dish_images.dart         kDishImageByName       : 500 entries
#
# Keys are the human names exactly as the backend/cleaned DB spells them, which the
# review pass confirmed line up 1:1 with the library manifests.
# Regenerate after re-running generate-images.ps1.
# Pure ASCII.

param([switch]$Check)

$ErrorActionPreference = 'Stop'
$root    = "D:\Deepseek Harness\project4"
$dataDir = Join-Path $root "team\front\mealmind\lib\data"
$imgDir  = Join-Path $root "team\front\mealmind\assets\images"

function Esc-Dart([string]$s) {
    $s.Replace('\', '\\').Replace("'", "\'").Replace('$', '$' + ' ')
}

function Write-Map {
    param(
        [string]$Path,
        [string]$ConstName,
        [string]$Doc,
        [object[]]$Pairs      # objects with .Key and .File
    )

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine('// GENERATED FILE -- do not edit by hand.')
    [void]$sb.AppendLine('// Regenerate with team/front/scripts/make-dart-image-map.ps1')
    [void]$sb.AppendLine('//')
    [void]$sb.AppendLine("// $Doc")
    [void]$sb.AppendLine('//')
    [void]$sb.AppendLine('// The image library shipped alongside the cleaned DB does not always match its')
    [void]$sb.AppendLine('// own filenames; every entry below was visually verified. Do not "fix" a name')
    [void]$sb.AppendLine('// here without re-checking the actual pixels.')
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("const Map<String, String> $ConstName = <String, String>{")
    foreach ($p in $Pairs) {
        [void]$sb.AppendLine("  '$(Esc-Dart $p.Key)': 'assets/images/$($p.File)',")
    }
    [void]$sb.AppendLine('};')
    [void]$sb.AppendLine('')

    if ($Check) {
        Write-Host "[check] $ConstName -> $($Pairs.Count) entries"
        return
    }
    Set-Content -Path $Path -Value $sb.ToString() -Encoding UTF8 -NoNewline
    Write-Host "wrote $Path  ($($Pairs.Count) entries)"
}

# ---------------------------------------------------------------- ingredients
$ingMan = Import-Csv (Join-Path $root "ingredient_image_library\ingredient_image_library\manifest.csv") -Encoding UTF8
$ingPairs = foreach ($r in $ingMan) {
    $file = [System.IO.Path]::ChangeExtension($r.filename, '.jpg')
    if (Test-Path (Join-Path $imgDir $file)) {
        [pscustomobject]@{ Key = $r.name; File = $file }
    }
}
Write-Map -Path (Join-Path $dataDir 'ingredient_images.dart') `
          -ConstName 'kIngredientImageByName' `
          -Doc 'Chinese ingredient name -> bundled photo.' `
          -Pairs $ingPairs

# ---------------------------------------------------------------- dishes
$dishMan = Import-Csv (Join-Path $root "dish_image_library\dish_image_library\manifest.csv") -Encoding UTF8
# Same-named dishes are common (many "红烧肉"), but a Dart const map forbids
# duplicate keys -- keep the first photo per name.
$seenDish = [System.Collections.Generic.HashSet[string]]::new()
$dishPairs = foreach ($r in $dishMan) {
    $file = [System.IO.Path]::ChangeExtension($r.filename, '.jpg')
    if ((Test-Path (Join-Path $imgDir $file)) -and $seenDish.Add($r.dish_name)) {
        [pscustomobject]@{ Key = $r.dish_name; File = $file }
    }
}
Write-Map -Path (Join-Path $dataDir 'dish_images.dart') `
          -ConstName 'kDishImageByName' `
          -Doc 'Dish name -> bundled photo.' `
          -Pairs $dishPairs
