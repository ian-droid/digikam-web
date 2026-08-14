# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir build for DigiKam Web
#
#   pip install pyinstaller
#   pyinstaller digikam-web.spec
#
# Output: dist/digikam-web/  (folder you can zip and distribute)

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = []
hidden += collect_submodules("uvicorn")
hidden += collect_submodules("starlette")
hidden += collect_submodules("fastapi")
hidden += collect_submodules("anyio")
hidden += collect_submodules("pydantic")
hidden += collect_submodules("pydantic_settings")
# image / auth
hidden += ["PIL", "PIL.Image", "PIL.ImageOps", "bcrypt", "click"]

# Optional engines uvicorn may import
hidden += [
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
]

datas = [
    ("templates", "templates"),
    ("static", "static"),
]

a = Analysis(
    ["run_server.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
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
    [],
    exclude_binaries=True,
    name="digikam-web",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # console app (logs + Ctrl+C)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="digikam-web",
)

# Second executable: CLI (init / user / config)
a_cli = Analysis(
    ["run_cli.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden + ["app.cli.init_cmd"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="digikam-web-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll_cli = COLLECT(
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="digikam-web-cli",
)
