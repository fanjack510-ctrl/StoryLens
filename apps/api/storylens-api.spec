# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the StoryLens FastAPI desktop sidecar.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
SPECDIR = Path(SPEC).resolve().parent
REPO = SPECDIR.parents[1]
PYINSTALLER_CODESIGN_IDENTITY = (
    os.environ.get("STORYLENS_PYINSTALLER_CODESIGN_IDENTITY", "").strip() or None
)

datas = [
    (str(REPO / "packages" / "prompts"), "packages/prompts"),
    (str(REPO / "config" / "reader_journey_formulas.json"), "config"),
    (str(REPO / "config" / "reader_journey_formulas_v2.json"), "config"),
    (str(REPO / "config" / "scene_role_targets.json"), "config"),
    (str(REPO / "config" / "scene_evidence_validation.json"), "config"),
    (str(REPO / "config" / "cloud_pricing.example.json"), "config"),
    # Verified official list-price fallback; resolve_cloud_pricing_path prefers this
    # when config/cloud_pricing.json is absent in packaged installs.
    (str(REPO / "config" / "cloud_pricing.default.json"), "config"),
    (str(REPO / "config" / "license_public_keys.production.json"), "config"),
    (
        str(REPO / "packages" / "material_seed" / "storylens_material_seed_v1.json"),
        "packages/material_seed",
    ),
]

hiddenimports = [
    # PDF 摄入（专著读法）。它只在 extract_document 里按需 import，
    # PyInstaller 的静态扫描看不到函数内部的延迟导入。
    "pypdf",
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
    "docx",
    "ebooklib",
    "bs4",
    "httpx",
    # 成品 PDF 的页码走 DevTools 协议（Page.printToPDF 才能传页脚模板），那条路径要用它。
    # 少了它不会报错——`_print_via_devtools` 直接 ImportError 返回 None，静默回落到
    # `--print-to-pdf`，于是每一份付费导出的 PDF 都没有页码，而没人会发现。
    "websockets",
    "anyio",
    "app",
    "app.main",
]

if sys.platform == "win32":
    hiddenimports.append("keyring.backends.Windows")
elif sys.platform == "darwin":
    hiddenimports.append("keyring.backends.macOS")

# keyring discovers backends via package metadata / entry points; collect_all
# pulls submodules + dist-info so Windows Credential Manager backend is usable.
for pkg in ("uvicorn", "fastapi", "starlette", "sqlalchemy", "pydantic", "anyio", "keyring"):
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        hiddenimports += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

hiddenimports += collect_submodules("keyring")
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
    codesign_identity=PYINSTALLER_CODESIGN_IDENTITY,
    entitlements_file=None,
)
