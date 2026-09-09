from pathlib import Path

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
    upx=True,
    console=False,
)
