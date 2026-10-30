import json
import os
from pathlib import Path
import shutil


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + ".new")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def copy_application(source, target, backend, distribution):
    source, target = Path(source), Path(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "nothingx", target / "nothingx", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin", "*.so", "*.dylib", "build.json"))
    for library in (source / "nothingx/bin").glob(f"libnothingx_{backend}.*"):
        atomic_copy(library, target / "nothingx/bin" / library.name)
    if not list((target / "nothingx/bin").glob(f"libnothingx_{backend}.*")):
        raise RuntimeError(f"Build the {backend} backend first: ./setup.sh --backend {backend}")
    for extension in (source / "nothingx").glob("*.so"):
        atomic_copy(extension, target / "nothingx" / extension.name)
    for name in ("run.sh", "run-cpp.sh", "run-rust.sh", "setup.sh", "setup.py", "pyproject.toml", "requirements.txt", "requirements-build.txt", "MANIFEST.in", "LICENSE", "NOTICE", "variants.json"):
        atomic_copy(source / name, target / name)
    for directory in ("licenses", "native", "rust-engine", "tools", "packaging"):
        shutil.copytree(source / directory, target / directory, dirs_exist_ok=True, ignore=shutil.ignore_patterns("target", "__pycache__", "*.pyc"))
    from nothingx import __version__
    (target / "nothingx/assets/build.json").write_text(json.dumps({"backend": backend, "distribution": distribution, "version": __version__, "source": str(source)}) + "\n")
