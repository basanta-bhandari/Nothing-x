#!/usr/bin/env python3

import os
from pathlib import Path
import shlex
import shutil
import subprocess

source = Path(__file__).resolve().parent
data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
destination = data / "nothingx-linux"
binary = Path.home() / ".local/bin/nothingx-linux"
desktop = data / "applications/nothingx-linux.desktop"
icon = destination / "nothingx/assets/cmf-buds-pro-2/blue_case.png"


def main():
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "nothingx", destination / "nothingx", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin"))
    native_dir = destination / "nothingx/bin"
    native_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "nothingx/bin/nothingx-core", native_dir / ".nothingx-core.new")
    os.replace(native_dir / ".nothingx-core.new", native_dir / "nothingx-core")
    for name in ("LICENSE", "NOTICE", "requirements.txt", "setup.sh", "run.sh", "setup.py", "pyproject.toml", "MANIFEST.in"):
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "licenses", destination / "licenses", dirs_exist_ok=True)
    shutil.copytree(source / "native", destination / "native", dirs_exist_ok=True)
    subprocess.run(["sh", str(destination / "setup.sh")], check=True)
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexec " + shlex.quote(str(destination / "run.sh")) + ' "$@"\n')
    binary.chmod(0o755)
    desktop.parent.mkdir(parents=True, exist_ok=True)

    executable = str(binary).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    desktop.write_text((source / "packaging/nothingx-linux.desktop").read_text().replace("Exec=nothingx-linux", f'Exec="{executable}"').replace("Icon=nothingx-linux", "Icon=" + str(icon)))
    print(f"Installed. Open Nothing X Linux in your application menu, or run {binary}")


if __name__ == "__main__":
    main()
