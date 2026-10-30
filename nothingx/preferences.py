import json
import os
from pathlib import Path
import sys


def preference_path():
    if os.environ.get("NOTHINGX_PREFERENCES"):
        return Path(os.environ["NOTHINGX_PREFERENCES"])
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/NothingX/preferences.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nothingx/preferences.json"


def read_preferences():
    try:
        result = json.loads(preference_path().read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(**values):
    path = preference_path()
    data = {**read_preferences(), **values}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)
    return data
