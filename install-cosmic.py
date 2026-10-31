#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from tools.install_support import atomic_copy
from nothingx.startup import desktop_argument

source = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("cpp", "rust"), default=os.environ.get("NOTHINGX_BACKEND", "cpp"))
parser.add_argument("--prefix", type=Path)
parser.add_argument("--executable", type=Path)
args = parser.parse_args()
backend = args.backend
prefix = args.prefix or Path.home() / ".local"
executable = args.executable or source / "cosmic-applet/bin" / f"cosmic-applet-nothingx-{backend}"
if not executable.is_file():
    raise SystemExit(f"Build the applet first: python tools/build_applets.py --backend {backend}")
subprocess.run([str(source / ".venv/bin/python"), str(source / "install-local.py"), "--backend", backend, "--prefix", str(prefix), "--distribution", "applet"], check=True)
app_dir = prefix / "share" / f"nothingx-{backend}-applet"
binary = app_dir / f"cosmic-applet-nothingx-{backend}"
atomic_copy(executable, binary)
binary.chmod(0o755)
launcher = prefix / "bin" / binary.name
launcher.write_text("#!/bin/sh\nexport NOTHINGX_APP_DIR=" + shlex.quote(str(app_dir)) + "\nexport NOTHINGX_BACKEND=" + backend + "\nexec " + shlex.quote(str(binary)) + ' "$@"\n')
launcher.chmod(0o755)
app_id = "io.github.basanta_bhandari.NothingXApplet." + backend.title()
label = "C++" if backend == "cpp" else "Rust"
desktop = prefix / "share/applications" / (app_id + ".desktop")
icon = app_dir / "nothingx/assets/cmf-buds-pro-2/blue_case.png"
desktop.write_text(f"[Desktop Entry]\nType=Application\nName=Nothing X ({label})\nComment=Nothing and CMF audio controls\nExec={desktop_argument(launcher)}\nIcon={icon}\nTerminal=false\nCategories=COSMIC;\nKeywords=COSMIC;Applet;Bluetooth;Nothing;CMF;\nNoDisplay=true\nX-CosmicApplet=true\nX-CosmicHoverPopup=Auto\nX-OverflowPriority=10\n")
metadata = prefix / "share/metainfo" / (app_id + ".metainfo.xml")
metadata.parent.mkdir(parents=True, exist_ok=True)
metadata.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{app_id}</id>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <name>Nothing X ({label})</name>
  <summary>Nothing and CMF controls for the COSMIC panel</summary>
  <description><p>View battery levels and control audio devices.</p></description>
  <url type="homepage">https://github.com/basanta-bhandari/Nothing-x</url>
  <launchable type="desktop-id">{app_id}.desktop</launchable>
  <provides><id>com.system76.CosmicApplet</id><binary>{binary.name}</binary></provides>
  <categories><category>COSMIC</category></categories>
  <content_rating type="oars-1.1"/>
</component>
""")
if shutil.which("update-desktop-database"):
    subprocess.run(["update-desktop-database", str(desktop.parent)], check=False, capture_output=True)
print(f"Installed {label} applet and searchable full settings. Add Nothing X ({label}) in COSMIC Settings → Desktop → Panel → Applets.")
