$ErrorActionPreference = "Stop"

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test -- --run
pnpm --dir frontend typecheck
pnpm --dir frontend build

$env:UV_CACHE_DIR = Join-Path $env:TEMP "dockmask-uv-cache"
$env:GIGACHAT_RUN_INTEGRATION = "0"
uv run pytest -q
uv run ruff check .
uv lock --check
uv run pyinstaller --noconfirm --clean --distpath output/exe --workpath tmp/pyinstaller DockMask.spec
