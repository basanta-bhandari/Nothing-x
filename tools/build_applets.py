import argparse
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("rust",), default="rust")
parser.add_argument("--profile", choices=("debug", "release"), default="release")
parser.add_argument("--output-dir", type=Path, default=root / "cosmic-applet/bin")
args = parser.parse_args()
target = Path(os.environ.get("CARGO_TARGET_DIR", root / "build/cosmic"))
for backend in ("rust",):
    command = ["cargo", "build", "--locked", "--manifest-path", str(root / "cosmic-applet/Cargo.toml"), "-j2"]
    if args.profile == "release":
        command.append("--release")
    subprocess.run(command, check=True, env={**os.environ, "CARGO_TARGET_DIR": str(target)})
    output = args.output_dir / f"cosmic-applet-nothingx-{backend}"
    output.parent.mkdir(exist_ok=True)
    shutil.copy2(target / args.profile / "cosmic-applet-nothingx", output)
    if shutil.which("strip"):
        subprocess.run(["strip", str(output)], check=True)
    print(output)
