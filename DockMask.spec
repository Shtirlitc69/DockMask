from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPECPATH)
frontend_dist = project_root / "frontend" / "dist"
if not (frontend_dist / "index.html").is_file():
    raise SystemExit("frontend/dist is missing; run pnpm --dir frontend build first")

certificate = project_root / "app" / "resources" / "certs" / "russian_trusted_root_ca_pem.crt"
manifest = project_root / "app" / "resources" / "certs" / "manifest.json"
if not certificate.is_file() or not manifest.is_file():
    raise SystemExit("GigaChat certificate resources are missing")

datas = collect_data_files("app.resources.certs")
datas.append((str(frontend_dist), "frontend/dist"))
ocr_runtime = project_root / "tmp" / "tesseract"
if not (ocr_runtime / "tesseract.exe").is_file():
    raise SystemExit("Tesseract runtime is missing; run scripts/prepare_ocr.ps1 first")
for required_language in ("rus.traineddata", "eng.traineddata"):
    if not (ocr_runtime / "tessdata" / required_language).is_file():
        raise SystemExit(f"Tesseract language is missing: {required_language}")
ocr_archive = project_root / "tmp" / "dockmask-tesseract-runtime.zip"
with ZipFile(ocr_archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(item for item in ocr_runtime.rglob("*") if item.is_file()):
        archive.write(path, path.relative_to(ocr_runtime).as_posix())
datas.append((str(ocr_archive), "ocr"))

a = Analysis(
    [str(project_root / "app" / "desktop.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["keyring.backends.Windows"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DockMask",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
