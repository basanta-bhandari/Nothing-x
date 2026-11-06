import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("rust",), default="rust")
args = parser.parse_args()
suffix = "dylib" if sys.platform == "darwin" else "so"
output = root / "nothingx/bin"
output.mkdir(exist_ok=True)
if args.backend == "rust":
    target = root / "build/rust"
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    subprocess.run(["cargo", "build", "--release", "--locked", "--manifest-path", str(root / "rust-engine/Cargo.toml")], check=True, env=env)
    shutil.copy2(target / f"release/libnothingx_rust.{suffix}", output / f"libnothingx_rust.{suffix}")
