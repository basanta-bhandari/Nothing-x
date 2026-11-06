#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from tools.install_support import copy_application
from nothingx.startup import desktop_argument

source = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("rust",), default="rust")
parser.add_argument("--prefix", type=Path)
parser.add_argument("--distribution", choices=("applet",), default="applet")
args = parser.parse_args()
backend = args.backend
if sys.platform == "darwin":
    label = "Rust"
    bundle = source / "dist/macos/Nothing X.app"
    if not bundle.is_dir():
        raise SystemExit(f"Run python packaging/build-macos.py on this Mac first.")
    destination = (args.prefix or Path.home()) / "Applications" / bundle.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + bundle.name)
    shutil.rmtree(temporary, ignore_errors=True)
    subprocess.run(["ditto", str(bundle), str(temporary)], check=True)
    previous = destination.with_name(bundle.name + ".previous")
    shutil.rmtree(previous, ignore_errors=True)
    if destination.exists():
        destination.rename(previous)
    temporary.rename(destination)
    print(f"Installed {destination}. Open Nothing X from Spotlight.")
    raise SystemExit(0)
prefix = args.prefix or Path.home() / ".local"
data = prefix / "share"
destination = data / f"nothingx-{backend}-{args.distribution}"
copy_application(source, destination, backend, args.distribution)
if not (destination / ".venv/bin/python").exists():
    subprocess.run(["python3", "-m", "venv", str(destination / ".venv")], check=True)
    subprocess.run([str(destination / ".venv/bin/python"), "-m", "pip", "install", "-r", str(source / "requirements.txt")], check=True)
binary = prefix / "bin" / f"nothingx-{backend}{'-applet' if args.distribution == 'applet' else ''}"
binary.parent.mkdir(parents=True, exist_ok=True)
binary.write_text("#!/bin/sh\nexport NOTHINGX_BACKEND=" + backend + "\nexec " + shlex.quote(str(destination / "run.sh")) + ' "$@"\n')
binary.chmod(0o755)
desktop = data / "applications" / f"io.github.basanta_bhandari.NothingX.{backend}.{args.distribution}.desktop"
desktop.parent.mkdir(parents=True, exist_ok=True)
icon = destination / "nothingx/assets/cmf-buds-pro-2/blue_case.png"
desktop.write_text(f"[Desktop Entry]\nType=Application\nName=Nothing X ({'Rust'})\nGenericName=Nothing audio controls\nComment=Nothing and CMF earbuds and headphone settings\nExec={desktop_argument(binary)}\nIcon={icon}\nTerminal=false\nCategories=AudioVideo;Audio;Settings;\nKeywords=Nothing;Nothing X;CMF;Buds;Headphones;Bluetooth;\nStartupNotify=true\n")
if shutil.which("update-desktop-database"):
    subprocess.run(["update-desktop-database", str(desktop.parent)], check=False, capture_output=True)
print(f"Installed {binary}. Search for Nothing X in your app launcher.")
