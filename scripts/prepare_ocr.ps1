$ErrorActionPreference = "Stop"

$version = "5.4.0.20240606"
$installerUrl = "https://github.com/UB-Mannheim/tesseract/releases/download/v$version/tesseract-ocr-w64-setup-$version.exe"
$installerSha256 = "C885FFF6998E0608BA4BB8AB51436E1C6775C2BAFC2559A19B423E18678B60C9"
$sevenZipVersion = "26.03"
$sevenZipBootstrapUrl = "https://www.7-zip.org/a/7zr.exe"
$sevenZipBootstrapSha256 = "AD4C82FADCBDF93C03B4FC440F300509C7D60C5C2F4D183E35D9D70D6957037D"
$sevenZipUrl = "https://www.7-zip.org/a/7z2603-x64.exe"
$sevenZipSha256 = "0859C524B8A63551848F0C246ABDDCB1D0B7B656B0FBFE879F8D85E61A9E6EDD"
$languages = @{
    "eng.traineddata" = @(
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata",
        "7D4322BD2A7749724879683FC3912CB542F19906C83BCC1A52132556427170B2"
    )
    "rus.traineddata" = @(
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/rus.traineddata",
        "E16E5E036CCE1D9EC2B00063CF8B54472625B9E14D893A169E2B0DEDEB4DF225"
    )
}

function Assert-Hash([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) {
        throw "Checksum mismatch for $Path"
    }
    return $true
}

function Get-VerifiedFile([string]$Url, [string]$Path, [string]$Hash) {
    if (Assert-Hash $Path $Hash) { return }
    Invoke-WebRequest -Uri $Url -OutFile $Path
    if (-not (Assert-Hash $Path $Hash)) { throw "Unable to verify $Path" }
}

$cacheBase = Join-Path $env:LOCALAPPDATA "DockMaskBuildCache"
$cacheRoot = Join-Path $cacheBase "tesseract-runtime-$version"
$extractedRoot = Join-Path $cacheBase "tesseract-extracted-$version"
$installer = Join-Path $cacheBase "tesseract-$version.exe"
New-Item -ItemType Directory -Force -Path $cacheBase, $cacheRoot | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $cacheRoot "tesseract.exe") -PathType Leaf)) {
    Get-VerifiedFile $installerUrl $installer $installerSha256
    $sevenZipBootstrap = Join-Path $cacheBase "7zr-$sevenZipVersion.exe"
    $sevenZipInstaller = Join-Path $cacheBase "7z-$sevenZipVersion-x64.exe"
    $sevenZipRoot = Join-Path $cacheBase "7z-$sevenZipVersion"
    Get-VerifiedFile $sevenZipBootstrapUrl $sevenZipBootstrap $sevenZipBootstrapSha256
    Get-VerifiedFile $sevenZipUrl $sevenZipInstaller $sevenZipSha256
    New-Item -ItemType Directory -Force -Path $sevenZipRoot, $extractedRoot | Out-Null
    & $sevenZipBootstrap x "-o$sevenZipRoot" -y $sevenZipInstaller | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to prepare 7-Zip" }
    & (Join-Path $sevenZipRoot "7z.exe") x "-o$extractedRoot" -y $installer | Out-Null
    if ($LASTEXITCODE -gt 1) { throw "Unable to extract Tesseract runtime" }

    Copy-Item -LiteralPath (Join-Path $extractedRoot "tesseract.exe") -Destination $cacheRoot -Force
    Copy-Item -Path (Join-Path $extractedRoot "*.dll") -Destination $cacheRoot -Force
    $sourceTessdata = Join-Path $extractedRoot "tessdata"
    $runtimeTessdata = Join-Path $cacheRoot "tessdata"
    New-Item -ItemType Directory -Force -Path $runtimeTessdata | Out-Null
    foreach ($directory in @("configs", "tessconfigs")) {
        $sourceDirectory = Join-Path $sourceTessdata $directory
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            Copy-Item -LiteralPath $sourceDirectory -Destination $runtimeTessdata -Recurse -Force
        }
    }
}

$tessdata = Join-Path $cacheRoot "tessdata"
New-Item -ItemType Directory -Force -Path $tessdata | Out-Null
foreach ($entry in $languages.GetEnumerator()) {
    Get-VerifiedFile $entry.Value[0] (Join-Path $tessdata $entry.Key) $entry.Value[1]
}

$target = Join-Path $PSScriptRoot "..\tmp\tesseract"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $cacheRoot "*") -Destination $target -Recurse -Force
$previousPath = $env:PATH
try {
    $env:PATH = "$target;$previousPath"
    $env:TESSDATA_PREFIX = Join-Path $target "tessdata"
    $availableLanguages = & (Join-Path $target "tesseract.exe") --list-langs 2>&1
    $languageText = $availableLanguages -join "`n"
    if ($LASTEXITCODE -ne 0 -or $languageText -notmatch "(?m)^eng$" -or $languageText -notmatch "(?m)^rus$") {
        throw "Prepared Tesseract runtime failed its rus/eng self-check"
    }
} finally {
    $env:PATH = $previousPath
    Remove-Item Env:TESSDATA_PREFIX -ErrorAction SilentlyContinue
}
Write-Host "Tesseract OCR runtime prepared: $target"
