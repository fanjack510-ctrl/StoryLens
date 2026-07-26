# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for StoryLens FastAPI sidecar (Windows).

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
SPECDIR = Path(SPEC).resolve().parent
REPO = SPECDIR.parents[1]

datas = [
    (str(REPO / "packages" / "prompts"), "packages/prompts"),
    (str(REPO / "config" / "reader_journey_formulas.json"), "config"),
    (str(REPO / "config" / "cloud_pricing.example.json"), "config"),
    # Verified official list-price fallback; resolve_cloud_pricing_path prefers this
    # when config/cloud_pricing.json is absent in packaged installs.
    (str(REPO / "config" / "cloud_pricing.default.json"), "config"),
    (str(REPO / "config" / "license_public_keys.production.json"), "config"),
]

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "pydantic",
    "pydantic_settings",
    "keyring",
    "keyring.backends",
    "keyring.backends.Windows",
    "docx",
    "ebooklib",
    "bs4",
    "httpx",
    "anyio",
    "app",
    "app.main",
]

for pkg in ("uvicorn", "fastapi", "starlette", "sqlalchemy", "pydantic", "anyio"):
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        hiddenimports += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

hiddenimports += collect_submodules("app")

# Optional Private Native Overview Engine (closed-source package).
# Must be importable in the build venv (e.g. pip install -e ../private-engine).
# Never silently invent a Fixture default; absence means loader returns UNAVAILABLE.
try:
    import storylens_private_engine  # noqa: F401

    hiddenimports += collect_submodules("storylens_private_engine")
    try:
        priv = collect_all("storylens_private_engine")
        datas += priv[0]
        hiddenimports += priv[1]
        hiddenimports += priv[2]
    except Exception:
        pass
except Exception:
    pass

a = Analysis(
    [str(SPECDIR / "sidecar_main.py")],
    pathex=[str(SPECDIR), str(REPO)],
    binaries=[],
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="storylens-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
