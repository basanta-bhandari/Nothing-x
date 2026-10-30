import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from nothingx import __version__

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=root / "dist/release")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
source = args.output / f"NothingX-source-v{__version__}.tar.gz"
with tarfile.open(source, "w:gz") as archive:
    for name in tracked:
        path = root / name
        if name and path.is_file() and not name.endswith((".AppImage", ".dmg")) and not name.startswith(("cosmic-applet/bin/", "nothingx/bin/")):
            archive.add(path, "NothingX/" + name, recursive=False)
for backend in ("cpp", "rust"):
    binary = root / "cosmic-applet/bin" / f"cosmic-applet-nothingx-{backend}"
    library = root / "nothingx/bin" / f"libnothingx_{backend}.so"
    if binary.is_file() and library.is_file():
        bundle = args.output / f"NothingX-{backend}-applet-linux-{platform.machine()}.tar.gz"
        with tarfile.open(bundle, "w:gz") as archive:
            for name in tracked:
                path = root / name
                if name and path.is_file() and not name.endswith((".AppImage", ".dmg")) and not name.startswith(("cosmic-applet/bin/", "nothingx/bin/", "screenshots/", "preview/")):
                    archive.add(path, "NothingX/" + name, recursive=False)
            archive.add(binary, "NothingX/cosmic-applet/bin/" + binary.name)
            archive.add(library, "NothingX/nothingx/bin/" + library.name)
artifacts = []
for path in sorted(args.output.iterdir()):
    if path.suffix not in (".AppImage", ".dmg", ".gz"):
        continue
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    base = {"file": path.name, "sha256": digest, "size": path.stat().st_size}
    if "-source-" in path.name:
        artifacts += [{**base, "variant": backend + "-manual", "os": "any", "arch": "any"} for backend in ("cpp", "rust")]
        continue
    backend = "rust" if "-rust-" in path.name else "cpp"
    distribution = "applet" if "-applet-" in path.name else "portable"
    system = "macos" if "-macos-" in path.name else "linux"
    architecture = "arm64" if "arm64" in path.name or "aarch64" in path.name else "x86_64"
    artifacts.append({**base, "variant": backend + "-" + distribution, "os": system, "arch": architecture})
manifest = {"schema": 1, "version": __version__, "commit": commit, "artifacts": artifacts}
(args.output / "nothingx-update.json").write_text(json.dumps(manifest, indent=2) + "\n")
(args.output / "SHA256SUMS").write_text("".join(f"{item['sha256']}  {item['file']}\n" for item in {item["file"]: item for item in artifacts}.values()))
print(args.output / "nothingx-update.json")
