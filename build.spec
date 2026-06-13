# PyInstaller build spec for cc-notify.
# Produces a single-file Windows executable with no console window.
#
# Build locally:   uv run pyinstaller build.spec
# CI:              see .github/workflows/release.yml
#
# The icon file is generated before the build by scripts/create_icon.py.
# Note: block_cipher / cipher= were removed in PyInstaller 6 — do not add them back.

# collect_data_files gathers non-Python resource files from an installed package.
# certifi's cacert.pem must be collected this way — listing "certifi" in
# hiddenimports only includes the Python code, not the certificate bundle file
# that certifi.where() points to at runtime.
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    datas=collect_data_files("certifi"),
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
        # certifi is imported lazily in updater._ssl_context().
        "certifi",
        # Local modules imported lazily inside thread callbacks — list them
        # explicitly so PyInstaller's static analyser does not miss them.
        "hooks_setup",
        "state",
        "updater",
        "version",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Trim the bundle — these are never used in a headless tray app.
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

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
