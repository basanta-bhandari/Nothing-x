import os
import json
import platform
from pathlib import Path

BACKENDS = ("cpp", "rust")
DISTRIBUTIONS = ("portable", "applet", "manual")


def build_info():
    try:
        result = json.loads((Path(__file__).resolve().parent / "assets/build.json").read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def backend_name(value=None):
    value = value or os.environ.get("NOTHINGX_BACKEND") or build_info().get("backend", "cpp")
    if value not in BACKENDS:
        raise ValueError("Choose the cpp or rust backend.")
    return value


def variant_id(backend=None, distribution=None):
    distribution = distribution or os.environ.get("NOTHINGX_DISTRIBUTION") or build_info().get("distribution", "manual")
    if distribution not in DISTRIBUTIONS:
        raise ValueError("Unknown distribution format.")
    return f"{backend_name(backend)}-{distribution}"


def package_format(system=None):
    system = system or platform.system()
    return {"Linux": "AppImage", "Darwin": "dmg"}.get(system)
