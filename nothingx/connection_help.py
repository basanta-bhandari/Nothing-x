import json
from pathlib import Path

from .models import model_info

HINTS = json.loads((Path(__file__).resolve().parent / "assets/connection-hints.json").read_text())


def connection_hint(model=None):
    kind = model_info(model)["kind"]
    return HINTS["headphones" if kind in ("headphones", "neckband") else "earbuds"]
