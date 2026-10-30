import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("cpp", "rust", "all"), default=os.environ.get("NOTHINGX_BACKEND", "cpp"))
args = parser.parse_args()
suffix = "dylib" if sys.platform == "darwin" else "so"
output = root / "nothingx/bin"
output.mkdir(exist_ok=True)
if args.backend in ("cpp", "all"):
    subprocess.run(["cmake", "-S", str(root / "native"), "-B", str(root / "build/native"), "-DCMAKE_BUILD_TYPE=Release"], check=True)
    subprocess.run(["cmake", "--build", str(root / "build/native"), "--target", "nothingx_cpp", "-j2"], check=True)
    shutil.copy2(root / f"build/native/libnothingx_cpp.{suffix}", output / f"libnothingx_cpp.{suffix}")
if args.backend in ("rust", "all"):
    target = root / "build/rust"
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    subprocess.run(["cargo", "build", "--release", "--locked", "--manifest-path", str(root / "rust-engine/Cargo.toml")], check=True, env=env)
    shutil.copy2(target / f"release/libnothingx_rust.{suffix}", output / f"libnothingx_rust.{suffix}")
