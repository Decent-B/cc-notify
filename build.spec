# PyInstaller build spec for cc-notify.
# Produces a single-file Windows executable with no console window.
#
# Build locally:   pyinstaller build.spec
# CI:              see .github/workflows/release.yml
#
# The icon file is auto-generated before the build by scripts/create_icon.py.

block_cipher = None

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
        # win11toast pulls in winsdk WinRT bindings dynamically.
        "winsdk",
        "winsdk.windows.ui.notifications",
        "winsdk.windows.data.xml.dom",
        "winsdk.windows.foundation",
        # pystray backend for Windows.
        "pystray._win32",
        # WSGI server and web framework.
        "waitress",
        "waitress.adjustments",
        "flask",
        "flask.logging",
        # Image handling.
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        # Hook setup — local module; listed explicitly in case PyInstaller
        # misses it because it is imported lazily inside a thread callback.
        "hooks_setup",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Trim the bundle — these are never used in a headless tray app.
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas", "pytest"],
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
    name="cc-notify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # No console window — the app lives entirely in the system tray.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
