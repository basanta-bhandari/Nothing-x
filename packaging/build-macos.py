#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("cpp", "rust"), required=True)
parser.add_argument("--distribution", choices=("portable", "manual"), default="portable")
parser.add_argument("--no-dmg", action="store_true")
args = parser.parse_args()
if sys.platform != "darwin":
    raise SystemExit("macOS packages must be built on a Mac.")
subprocess.run([sys.executable, str(root / "tools/build_backends.py"), "--backend", args.backend], check=True)
subprocess.run([sys.executable, "setup.py", "build_ext", "--inplace"], cwd=root, check=True)
iconset = root / "build/icons/NothingX.iconset"
iconset.mkdir(parents=True, exist_ok=True)
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
        subprocess.run(["sips", "-z", str(size * scale), str(size * scale), str(root / "nothingx/assets/cmf-buds-pro-2/blue_case.png"), "--out", str(iconset / name)], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["iconutil", "-c", "icns", str(iconset)], check=True)
output = root / (f"build/manual-{args.backend}" if args.distribution == "manual" else f"dist/macos-{args.backend}")
subprocess.run([sys.executable, str(root / "tools/freeze.py"), "--backend", args.backend, "--distribution", args.distribution, "--output", str(output)], check=True)
label = "Cpp" if args.backend == "cpp" else "Rust"
app = output / f"Nothing X {label}.app"
if app.exists():
    shutil.rmtree(app)
shutil.move(str(output / "nothingx.app"), app)
plist_path = app / "Contents/Info.plist"
info = plistlib.loads(plist_path.read_bytes())
sys.path.insert(0, str(root))
from nothingx import __version__
info.update(plistlib.loads((root / "packaging/macos-permissions.plist").read_bytes()))
info.update({"CFBundleName": "Nothing X", "CFBundleDisplayName": f"Nothing X ({label})", "CFBundleShortVersionString": __version__, "CFBundleVersion": __version__, "NSHighResolutionCapable": True})
plist_path.write_bytes(plistlib.dumps(info))
identity = os.environ.get("NOTHINGX_CODESIGN_IDENTITY", "-")
subprocess.run(["codesign", "--force", "--deep", "--sign", identity, str(app)], check=True)
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
if not args.no_dmg:
    stage = root / f"build/dmg-{args.backend}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
    (stage / "Applications").symlink_to("/Applications")
    image = root / f"dist/NothingX-{args.backend}-macos-{platform.machine()}.dmg"
    image.unlink(missing_ok=True)
    subprocess.run(["hdiutil", "create", "-volname", f"Nothing X {label}", "-srcfolder", str(stage), "-format", "UDZO", str(image)], check=True)
    print(image)
print(app)
