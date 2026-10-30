import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "assets"
MODELS = {model["id"]: model for model in json.loads((DATA / "models.json").read_text())["models"]}


def model_info(model=None):
    return MODELS.get(model, {"id": model or "", "name": "Nothing audio device", "kind": "unknown", "artwork": "generic", "features": [], "anc_modes": [], "eq_presets": []})
