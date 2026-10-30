import os
import platform
from pathlib import Path

BACKENDS = ("cpp", "rust")
DISTRIBUTIONS = ("portable", "applet", "manual")


def backend_name(value=None):
    value = value or os.environ.get("NOTHINGX_BACKEND", "cpp")
    if value not in BACKENDS:
        raise ValueError("Choose the cpp or rust backend.")
    return value


def variant_id(backend=None, distribution="manual"):
    if distribution not in DISTRIBUTIONS:
        raise ValueError("Unknown distribution format.")
    return f"{backend_name(backend)}-{distribution}"


def package_format(system=None):
    system = system or platform.system()
    return {"Linux": "AppImage", "Darwin": "dmg"}.get(system)


def backend_path(root, backend=None):
    root = Path(root)
    backend = backend_name(backend)
    if backend == "cpp":
        return root / "bin/nothingx-core"
    return root / "bin/nothingx-rust-core"
