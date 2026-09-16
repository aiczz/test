<#
=====================================================================
 三餐智囊 · Flutter 开发环境一键安装（Windows · 国内镜像自动适配版）
=====================================================================
 用法（普通 PowerShell 窗口，不必管理员）：

   powershell -ExecutionPolicy Bypass -File "D:\Deepseek Harness\project4\scripts\setup-flutter.ps1"

 可选参数：
   -FlutterDir "D:\flutter"                Flutter 安装目录
   -Source auto|google|cfug|tuna|sjtu      强制指定下载源（默认 auto 自动探测）
   -SkipAndroidStudio                      跳过 Android Studio 安装尝试

 本版重点解决：国内访问 storage.googleapis.com 不通的问题。
 会自动依次探测 官方源 → CFUG → 清华 TUNA → 上海交大 SJTU，
 选中「能真正下到文件」的那个，并把镜像环境变量永久写入用户环境。

 脚本可重复运行：任何一步失败，解决后重跑，已完成部分自动跳过。
=====================================================================
#>

[CmdletBinding()]
param(
    [string]$FlutterDir = 'D:\flutter',
    [ValidateSet('auto','google','cfug','tuna','sjtu')]
    [string]$Source = 'auto',
    [switch]$SkipAndroidStudio
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'                      # 大文件下载快很多
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say  ($m) { Write-Host $m }
function Ok   ($m) { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "  [!]    $m" -ForegroundColor Yellow }
function Bad  ($m) { Write-Host "  [X]    $m" -ForegroundColor Red }
function Step ($m) { Write-Host "`n==== $m ====" -ForegroundColor Cyan }

Say ""
Say "==================================================="
Say "  三餐智囊 · Flutter 环境安装（国内镜像适配版）"
Say "==================================================="

# =====================================================================
Step "1/9  前置检查"
# =====================================================================

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) { Ok "以管理员身份运行" }
else { Warn "非管理员运行（装 Flutter 没问题；装 Android Studio 时可能弹权限）" }

if (Get-Command git -ErrorAction SilentlyContinue) {
    Ok "Git 已安装"
} else {
    Bad "没找到 Git —— 请先装 https://git-scm.com/download/win"
    exit 1
}

try {
    $drive = (Split-Path $FlutterDir -Qualifier).TrimEnd(':')
    $freeGB = [math]::Round((Get-PSDrive -Name $drive -ErrorAction Stop).Free / 1GB, 1)
    if ($freeGB -gt 6) { Ok "${drive}: 可用 $freeGB GB" }
    else { Bad "${drive}: 只剩 $freeGB GB，建议预留 15 GB"; exit 1 }
} catch { Warn "无法读取磁盘空间，继续" }

$flutterExe = Join-Path $FlutterDir 'bin\flutter.bat'
$alreadyInstalled = Test-Path $flutterExe
if ($alreadyInstalled) { Ok "检测到已有 Flutter：$FlutterDir" }

# =====================================================================
Step "2/9  探测可用下载源（这一步是关键）"
# =====================================================================
# 每个候选源都用「真实的版本清单文件」测试，
# 保证测的就是下载 SDK 时真正要走的路径。

$SOURCES = @(
    [pscustomobject]@{ Key='google'; Name='官方源 (storage.googleapis.com)'
                       Storage='https://storage.googleapis.com'
                       Pub=$null }
    [pscustomobject]@{ Key='cfug';   Name='Flutter 社区 CFUG (flutter-io.cn)'
                       Storage='https://storage.flutter-io.cn'
                       Pub='https://pub.flutter-io.cn' }
    [pscustomobject]@{ Key='tuna';   Name='清华大学 TUNA'
                       Storage='https://mirrors.tuna.tsinghua.edu.cn/flutter'
                       Pub='https://mirrors.tuna.tsinghua.edu.cn/dart-pub' }
    [pscustomobject]@{ Key='sjtu';   Name='上海交大 SJTU'
                       Storage='https://mirror.sjtu.edu.cn'
                       Pub='https://mirror.sjtu.edu.cn/dart-pub' }
)

if ($Source -ne 'auto') {
    $SOURCES = $SOURCES | Where-Object { $_.Key -eq $Source }
    Say "  已指定源：$Source"
}

$chosen = $null
$metaJson = $null

foreach ($s in $SOURCES) {
    $probe = "$($s.Storage)/flutter_infra_release/releases/releases_windows.json"
    Write-Host "  测试 $($s.Name) ... " -NoNewline
    try {
        $r = Invoke-RestMethod -Uri $probe -TimeoutSec 20
        if ($r.releases -and $r.releases.Count -gt 0) {
            Write-Host "可用" -ForegroundColor Green
            $chosen = $s
            $metaJson = $r
            break
        } else {
            Write-Host "返回内容异常" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "不通" -ForegroundColor Red
    }
}

if (-not $chosen) {
    Bad "所有下载源都不可用！"
    Say "  请检查网络，或稍后重试。"
    Say "  也可手动下载 SDK 后放到 $env:TEMP 再重跑本脚本。"
    exit 1
}

Ok "选定下载源：$($chosen.Name)"

# =====================================================================
Step "3/9  配置镜像环境变量"
# =====================================================================

if ($chosen.Key -eq 'google') {
    Ok "使用官方源，无需配置镜像"
} else {
    [Environment]::SetEnvironmentVariable('FLUTTER_STORAGE_BASE_URL', $chosen.Storage, 'User')
    [Environment]::SetEnvironmentVariable('PUB_HOSTED_URL', $chosen.Pub, 'User')
    $env:FLUTTER_STORAGE_BASE_URL = $chosen.Storage
    $env:PUB_HOSTED_URL = $chosen.Pub
    Ok "FLUTTER_STORAGE_BASE_URL = $($chosen.Storage)"
    Ok "PUB_HOSTED_URL            = $($chosen.Pub)"
    Say ""
    Say "  ★ 这两个变量已永久写入用户环境 —— 以后 flutter pub get 也走镜像，"
    Say "    否则装依赖时会同样卡住。"
}

# =====================================================================
Step "4/9  解析当前 stable 版本"
# =====================================================================

$rel = $metaJson.releases |
    Where-Object { $_.channel -eq 'stable' -and $_.dart_sdk_arch -eq 'x64' } |
    Select-Object -First 1

if (-not $rel) { Bad "版本清单里没找到 stable x64 版本"; exit 1 }

$zipVer = $rel.version
$zipSha = $rel.sha256
$zipUrl = "$($chosen.Storage)/flutter_infra_release/releases/$($rel.archive)"

Ok "当前 stable：$zipVer"
Ok "下载地址：$zipUrl"

# =====================================================================
Step "5/9  下载 Flutter SDK（约 700 MB）"
# =====================================================================

$zipPath = Join-Path $env:TEMP "flutter_$zipVer.zip"

if ($alreadyInstalled) {
    Ok "已安装，跳过下载"
} else {
    $needDownload = $true
    if ((Test-Path $zipPath) -and ((Get-Item $zipPath).Length -gt 100MB)) {
        Write-Host "  临时目录已有安装包，校验中 ... " -NoNewline
        $h = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()
        if ($h -eq $zipSha.ToLower()) { Ok "已存在且校验通过，跳过下载"; $needDownload = $false }
        else { Warn "校验不符，重新下载" }
    }

    if ($needDownload) {
        Say "  开始下载（没有进度条是正常的，请耐心等）..."
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -TimeoutSec 3600 -UseBasicParsing
            $sw.Stop()
            Ok "下载完成：$([math]::Round((Get-Item $zipPath).Length/1MB,1)) MB，用时 $([math]::Round($sw.Elapsed.TotalMinutes,1)) 分钟"
        } catch {
            Bad "下载失败：$($_.Exception.Message)"
            Say ""
            Say "  可手动下载后放到这个位置，再重跑脚本："
            Say "    $zipPath"
            Say "  下载地址（可用浏览器/迅雷加速）："
            Say "    $zipUrl"
            exit 1
        }
    }

    Write-Host "  校验 SHA256 ... " -NoNewline
    $actual = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()
    if ($actual -eq $zipSha.ToLower()) { Ok "通过" }
    else {
        Bad "校验失败，文件可能损坏"
        Say "  期望：$zipSha"
        Say "  实际：$actual"
        Say "  请删除后重跑：$zipPath"
        exit 1
    }
}

# =====================================================================
Step "6/9  解压到 $FlutterDir"
# =====================================================================

if (-not $alreadyInstalled) {
    # ---------------------------------------------------------------
    # ★ 关键：解压临时目录必须「极短」
    #   Windows 传统路径上限 260 字符。Flutter 压缩包里含引擎 iOS 测试资源，
    #   文件名极长（...golden_platform_view_clip_path_with_transform_...png），
    #   若解压到 C:\Users\xxx\AppData\Local\Temp\flutter_extract_xxx（前缀 62 字符）
    #   会超出上限、报「未能找到路径的一部分」。
    # ---------------------------------------------------------------
    $driveLetter = (Split-Path $FlutterDir -Qualifier).TrimEnd(':')
    $shortTmp = "${driveLetter}:\_fx"

    function Reset-ShortTmp {
        if (Test-Path $shortTmp) {
            Remove-Item $shortTmp -Recurse -Force -ErrorAction SilentlyContinue
        }
        New-Item -ItemType Directory -Path $shortTmp -Force | Out-Null
    }

    Reset-ShortTmp
    Ok "解压临时目录（故意选短路径）：$shortTmp"

    Say "  解压中（约 2 GB，需要几分钟）..."
    $extracted = $false

    # ---- 方式一：.NET 解压（最快）
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $shortTmp)
        $extracted = $true
        Ok "解压完成（.NET）"
    } catch {
        Warn "解压失败：$($_.Exception.Message)"
    }

    # ---- 方式二：回退到 Windows 自带 tar（原生支持超长路径，Win10 1803+ 内置）
    if (-not $extracted) {
        Say "  改用 Windows 自带 tar 重试……"
        Reset-ShortTmp
        $tarExe = "$env:SystemRoot\System32\tar.exe"
        if (Test-Path $tarExe) {
            & $tarExe -xf $zipPath -C $shortTmp
            if ($LASTEXITCODE -eq 0) {
                $extracted = $true
                Ok "解压完成（tar）"
            } else {
                Bad "tar 解压也失败（退出码 $LASTEXITCODE）"
            }
        } else {
            Bad "系统里没找到 tar.exe"
        }
    }

    # ---- 方式三：交给用户手动（并给出准确指引）
    if (-not $extracted) {
        Bad "自动解压失败。请手动处理："
        Say ""
        Say "  1. 用 7-Zip 或资源管理器，把这个文件解压到短路径，例如 $shortTmp"
        Say "       $zipPath"
        Say "     （★ 别解压到桌面或深层目录，路径太长会再次失败）"
        Say "  2. 把解压出来的 flutter 文件夹整体移动到：$FlutterDir"
        Say "     最终应存在：$FlutterDir\bin\flutter.bat"
        Say "  3. 【重新运行本脚本】，剩下的步骤会自动完成"
        Say ""
        Say "  SDK 安装包已保留，不需要重新下载。"
        exit 1
    }

    $inner = Join-Path $shortTmp 'flutter'
    if (Test-Path $inner) {
        if (Test-Path $FlutterDir) { Remove-Item $FlutterDir -Recurse -Force }
        Move-Item -Path $inner -Destination $FlutterDir
        Ok "已安装到 $FlutterDir"
    } else {
        Bad "解压结果里没找到 flutter 目录（$inner）"
        exit 1
    }

    Remove-Item $shortTmp -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    Ok "已清理临时文件"
} else {
    Ok "已存在，跳过"
}

# =====================================================================
Step "7/9  配置 PATH 并验证"
# =====================================================================

$flutterBin = Join-Path $FlutterDir 'bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($null -eq $userPath) { $userPath = '' }

if (($userPath -split ';') -contains $flutterBin) {
    Ok "PATH 里已有 flutter/bin"
} else {
    $newPath = if ($userPath.TrimEnd(';') -eq '') { $flutterBin } else { "$($userPath.TrimEnd(';'));$flutterBin" }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Ok "已加入用户 PATH：$flutterBin"
}
if (($env:Path -split ';') -notcontains $flutterBin) { $env:Path = "$env:Path;$flutterBin" }

Say ""
Say "  首次运行会自动下载 Dart SDK，走镜像应该很快……"
& $flutterExe --version
if ($LASTEXITCODE -eq 0) { Ok "Flutter 可用" } else { Bad "flutter --version 失败" }

& $flutterExe --disable-analytics 2>&1 | Out-Null

# =====================================================================
Step "8/9  Android Studio"
# =====================================================================

function Find-AndroidStudio {
    foreach ($c in @("$env:ProgramFiles\Android\Android Studio",
                     "${env:ProgramFiles(x86)}\Android\Android Studio",
                     "$env:LOCALAPPDATA\Programs\Android Studio")) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

$studio = Find-AndroidStudio
$sdkDir = "$env:LOCALAPPDATA\Android\Sdk"

if ($studio) {
    Ok "已安装：$studio"
} elseif ($SkipAndroidStudio) {
    Warn "按要求跳过"
} else {
    Warn "未检测到 Android Studio"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "  尝试用 winget 安装（约 1 GB）..."
        Say "  如果卡住或报错，可去官网手动下载：https://developer.android.com/studio"
        Say ""
        try {
            winget install --id Google.AndroidStudio -e --accept-package-agreements --accept-source-agreements
            $studio = Find-AndroidStudio
            if ($studio) { Ok "安装成功：$studio" } else { Warn "winget 执行完但没找到安装目录" }
        } catch {
            Warn "winget 失败：$($_.Exception.Message)"
        }
    } else {
        Warn "本机没有可用的 winget，请手动下载安装"
    }
}

# =====================================================================
Step "9/9  Android SDK 与许可"
# =====================================================================

if (Test-Path $sdkDir) {
    Ok "找到 Android SDK：$sdkDir"
    [Environment]::SetEnvironmentVariable('ANDROID_HOME', $sdkDir, 'User')
    [Environment]::SetEnvironmentVariable('ANDROID_SDK_ROOT', $sdkDir, 'User')
    $env:ANDROID_HOME = $sdkDir
    Ok "已设置 ANDROID_HOME / ANDROID_SDK_ROOT"

    & $flutterExe config --android-sdk $sdkDir | Out-Null

    Say "  接受 Android 许可（自动）..."
    try {
        ("y`n" * 30) | & $flutterExe doctor --android-licenses 2>&1 | Out-Null
        Ok "许可已处理"
    } catch {
        Warn "自动接受失败，手动跑：flutter doctor --android-licenses"
    }
} else {
    Warn "还没找到 Android SDK"
    Say "  → 打开 Android Studio，走完首次启动向导（它会下载 SDK）"
    Say "  → 然后【重新运行本脚本】，剩下的自动完成"
}

# =====================================================================
Say ""
Say "==================================================="
Say "  完成"
Say "==================================================="
Say ""
Say "  Flutter 位置 ： $FlutterDir"
Say "  下载源       ： $($chosen.Name)"
if ($chosen.Key -ne 'google') { Say "  镜像变量     ： 已永久写入用户环境" }
Say ""
Say "  ★ 请【关掉所有终端重开一个】，再执行 flutter 命令"
Say ""
& $flutterExe doctor
Say ""
Say "  下一步："
Say "    cd `"D:\Deepseek Harness\project4`""
Say "    flutter create mealmind"
Say "    cd mealmind"
Say "    flutter run"
Say ""
Say "  flutter doctor 里若还有 [X]，把完整输出发给我。"
Say ""
