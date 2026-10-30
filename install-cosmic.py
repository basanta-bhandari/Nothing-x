import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

source = Path(__file__).resolve().parent
app_id = "io.github.basanta_bhandari.NothingXApplet"
install_root = os.environ.get("NOTHINGX_INSTALL_ROOT")
data = Path(install_root) / "share" if install_root else Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
binary_dir = Path(install_root) / "bin" if install_root else Path.home() / ".local/bin"
target = data / "nothingx-cosmic"
executable = source / "cosmic-applet/bin/cosmic-applet-nothingx"
if not executable.is_file():
    executable = source / "cosmic-applet/target/release/cosmic-applet-nothingx"
if len(sys.argv) > 1:
    executable = Path(sys.argv[1]).resolve()
if not executable.is_file():
    raise SystemExit("Build the applet first: cargo build --release --locked --manifest-path cosmic-applet/Cargo.toml")
if not (source / ".venv/bin/python").is_file():
    raise SystemExit("Run ./setup.sh before installing the applet.")
target.mkdir(parents=True, exist_ok=True)
binary_dir.mkdir(parents=True, exist_ok=True)
app_dir = target / "app"
app_dir.mkdir(parents=True, exist_ok=True)
shutil.copytree(source / "nothingx", app_dir / "nothingx", dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin"))
native_dir = app_dir / "nothingx/bin"
native_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(source / "nothingx/bin/nothingx-core", native_dir / ".nothingx-core.new")
os.replace(native_dir / ".nothingx-core.new", native_dir / "nothingx-core")
for name in ("run.sh", "setup.sh", "requirements.txt", "LICENSE", "NOTICE", "setup.py", "pyproject.toml", "MANIFEST.in"):
    shutil.copy2(source / name, app_dir / name)
shutil.copytree(source / "licenses", app_dir / "licenses", dirs_exist_ok=True)
shutil.copytree(source / "native", app_dir / "native", dirs_exist_ok=True)
if not (app_dir / ".venv/bin/python").exists():
    subprocess.run(["cp", "-a", "--reflink=auto", str(source / ".venv"), str(app_dir / ".venv")], check=True)
subprocess.run([str(app_dir / ".venv/bin/python"), "-c", "from PySide6.QtCore import QCoreApplication"], check=True)
shutil.copy2(executable, target / ".cosmic-applet-nothingx.new")
(target / ".cosmic-applet-nothingx.new").chmod(0o755)
os.replace(target / ".cosmic-applet-nothingx.new", target / "cosmic-applet-nothingx")
launcher = binary_dir / "cosmic-applet-nothingx"
launcher.write_text("#!/bin/sh\nexport NOTHINGX_APP_DIR=" + shlex.quote(str(app_dir))
                    + "\nexec " + shlex.quote(str(target / "cosmic-applet-nothingx")) + ' "$@"\n')
launcher.chmod(0o755)
desktop = data / "applications" / (app_id + ".desktop")
desktop.parent.mkdir(parents=True, exist_ok=True)
desktop_exec = str(launcher).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
icon = app_dir / "nothingx/assets/cmf-buds-pro-2/blue_case.png"
desktop.write_text((source / "packaging" / (app_id + ".desktop")).read_text()
                   .replace("Exec=cosmic-applet-nothingx", f'Exec="{desktop_exec}"')
                   .replace("Icon=" + app_id, "Icon=" + str(icon)))
metadata = data / "metainfo" / (app_id + ".metainfo.xml")
metadata.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source / "packaging" / (app_id + ".metainfo.xml"), metadata)
if shutil.which("update-desktop-database"):
    subprocess.run(["update-desktop-database", str(desktop.parent)], check=False, capture_output=True)
print("Installed. Add Nothing X in COSMIC Settings → Desktop → Panel → Applets.")
