import argparse
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--prepare-only", action="store_true")
args = parser.parse_args()
stage = root / "build/flatpak-source"
stage.mkdir(parents=True, exist_ok=True)
for directory in ("nothingx", "rust-engine", "packaging", "licenses", "tests"):
    target = stage / directory
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(root / directory, target, ignore=shutil.ignore_patterns("bin", "*.so", "*.dylib", "__pycache__", "target", "build.json"))
for name in ("LICENSE", "NOTICE"):
    shutil.copy2(root / name, stage / name)
sys.path.insert(0, str(root))
from nothingx import __version__
(stage / "nothingx/assets/build.json").write_text(json.dumps({"backend": "rust", "distribution": "flatpak", "version": __version__, "managed": True}) + "\n")
vendor = stage / "vendor"
subprocess.run(["cargo", "vendor", "--locked", "--manifest-path", str(root / "rust-engine/Cargo.toml"), str(vendor)], check=True)
(stage / ".cargo").mkdir(exist_ok=True)
(stage / ".cargo/config.toml").write_text('[source.crates-io]\nreplace-with = "vendored-sources"\n[source.vendored-sources]\ndirectory = "vendor"\n')
wheels = stage / "wheels"
wheels.mkdir(exist_ok=True)
subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--dest", str(wheels), "PySide6-Essentials==6.12.0", "PySide6-Addons==6.12.0", "dbus-next==0.2.3"], check=True)
if args.prepare_only:
    raise SystemExit(0)
manifest = root / "packaging/flatpak/io.github.basanta_bhandari.NothingX.json"
builder = ["flatpak-builder"] if shutil.which("flatpak-builder") else ["flatpak", "run", "org.flatpak.Builder"]
repository = root / "build/flatpak-repo"
log_path = root / "build/flatpak-build.log"
print("Building Flatpak. Log:", log_path, flush=True)
with log_path.open("w") as log:
    result = subprocess.run([*builder, "--force-clean", "--user", "--install-deps-from=flathub", "--repo=" + str(repository), str(root / "build/flatpak-app"), str(manifest)], cwd=root, stdout=log, stderr=subprocess.STDOUT)
if result.returncode:
    lines = log_path.read_text(errors="replace").splitlines()
    print("\n".join([line for line in lines if "error:" in line.lower()][-12:] + lines[-15:]), file=sys.stderr)
    raise SystemExit(result.returncode)
(root / "dist").mkdir(exist_ok=True)
subprocess.run(["flatpak", "build-bundle", str(repository), str(root / f"dist/NothingX-linux-{platform.machine()}.flatpak"), "io.github.basanta_bhandari.NothingX", "--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo"], check=True)
