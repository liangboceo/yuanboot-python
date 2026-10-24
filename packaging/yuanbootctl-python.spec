from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
hiddenimports = []
for package in ("yuanboot", "uvicorn", "grpc_health", "google.protobuf"):
    hiddenimports += collect_submodules(package)
hiddenimports += ["sqlalchemy.dialects.mysql.pymysql", "sqlalchemy.dialects.sqlite.pysqlite"]

analysis = Analysis(
    [str(root / "src/yuanboot/cli/entrypoint.py")],
    pathex=[str(root / "src")],
    datas=collect_data_files("yuanboot", includes=["cli/templates/**/*.tpl", "logging.json"])
    + copy_metadata("yuanboot"),
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "matplotlib", "numpy", "pandas", "tkinter"],
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="yuanbootctl-python",
    console=True,
    upx=False,
)
