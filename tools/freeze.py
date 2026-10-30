import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("cpp", "rust"), required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
backend = args.backend
build = root / "build/freeze" / backend
assets = build / "assets"
if assets.exists():
    shutil.rmtree(assets)
shutil.copytree(root / "nothingx/assets", assets, ignore=shutil.ignore_patterns("references", "build.json"))
sys.path.insert(0, str(root))
from nothingx import __version__
(assets / "build.json").write_text(json.dumps({"backend": backend, "distribution": "portable", "version": __version__}) + "\n")
entry = build / "entry.py"
entry.write_text(f'import os\nos.environ["NOTHINGX_BACKEND"] = "{backend}"\nos.environ["NOTHINGX_DISTRIBUTION"] = "portable"\nfrom nothingx.__main__ import main\nraise SystemExit(main())\n')
suffix = "dylib" if sys.platform == "darwin" else "so"
library = root / "nothingx/bin" / f"libnothingx_{backend}.{suffix}"
if not library.is_file():
    raise SystemExit(f"Build the {backend} backend first.")
command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "nothingx", "--paths", str(root), "--collect-submodules", "nothingx"]
for module in ("QtCore", "QtGui", "QtWidgets", "QtBluetooth", "QtNetwork"):
    command += ["--hidden-import", "PySide6." + module]
command += ["--add-binary", f"{library}:nothingx/bin", "--add-data", f"{assets}:nothingx/assets"]
for name in ("LICENSE", "NOTICE", "licenses"):
    command += ["--add-data", f"{root / name}:{'licenses' if name == 'licenses' else '.'}"]
command += ["--distpath", str(args.output), "--workpath", str(build / "pyinstaller"), "--specpath", str(build), str(entry)]
subprocess.run(command, check=True, cwd=root, env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(build / "cache")})
