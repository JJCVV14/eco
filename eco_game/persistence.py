from __future__ import annotations

import json
from pathlib import Path

from eco_game.models import WorldState


SAVE_DIR = Path("saves")


def save_game(world: WorldState, filename: str) -> Path:
    SAVE_DIR.mkdir(exist_ok=True)
    if not filename.endswith(".json"):
        filename += ".json"
    path = SAVE_DIR / filename
    path.write_text(json.dumps(world.to_dict(), indent=2))
    return path


def load_game(path: Path) -> WorldState:
    raw = json.loads(path.read_text())
    return WorldState.from_dict(raw)
