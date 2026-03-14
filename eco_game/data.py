from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from eco_game.models import Nation, Objective, ProductionLine, ProductionTemplate, Resource


CONTENT_DIR = Path(__file__).resolve().parent / "content"

PRODUCTION_TEMPLATES: dict[str, ProductionTemplate] = {
    "Rifle Kits": ProductionTemplate(
        name="Rifle Kits",
        category="Infantry",
        base_output=26.0,
        resource_cost={Resource.IRON: 1.5, Resource.ALLOY: 0.6},
    ),
    "Field Cannons": ProductionTemplate(
        name="Field Cannons",
        category="Artillery",
        base_output=10.0,
        resource_cost={Resource.IRON: 1.0, Resource.TUNGSTEN: 0.5, Resource.CHROMITE: 0.2},
    ),
    "Armored Vehicles": ProductionTemplate(
        name="Armored Vehicles",
        category="Vehicles",
        base_output=5.0,
        resource_cost={Resource.IRON: 1.2, Resource.FUEL: 1.0, Resource.CHROMITE: 0.7},
    ),
    "Aircraft Frames": ProductionTemplate(
        name="Aircraft Frames",
        category="Aircraft",
        base_output=4.0,
        resource_cost={Resource.ALLOY: 1.0, Resource.FUEL: 0.8, Resource.LATEX: 0.6},
    ),
    "Logistics Packs": ProductionTemplate(
        name="Logistics Packs",
        category="Support",
        base_output=15.0,
        resource_cost={Resource.ALLOY: 0.3, Resource.LATEX: 0.3},
    ),
}


def load_nations() -> dict[str, Nation]:
    raw = json.loads((CONTENT_DIR / "nations.json").read_text())
    nations: dict[str, Nation] = {}
    for item in raw["nations"]:
        rb = {Resource(k): float(v) for k, v in item["resource_base"].items()}
        nation = Nation(
            name=item["name"],
            tag=item["tag"],
            civ_factories=item["civ_factories"],
            mil_factories=item["mil_factories"],
            infrastructure=item["infrastructure"],
            synthetic_plants=item["synthetic_plants"],
            extraction_level=item["extraction_level"],
            treasury=item["treasury"],
            stability=item["stability"],
            war_pressure=item["war_pressure"],
            coastline_access=item["coastline_access"],
            neighbors=item["neighbors"],
            resource_base=rb,
            stockpiles={
                "Rifle Kits": item["starting_stock"]["rifles"],
                "Field Cannons": item["starting_stock"]["artillery"],
                "Armored Vehicles": item["starting_stock"]["vehicles"],
                "Aircraft Frames": item["starting_stock"]["aircraft"],
                "Logistics Packs": item["starting_stock"]["support"],
            },
            production_lines=[
                ProductionLine("Rifle Kits", max(1, item["mil_factories"] // 3)),
                ProductionLine("Field Cannons", max(1, item["mil_factories"] // 4)),
            ],
        )
        nations[nation.tag] = nation
    return nations


def generate_objectives(nation: Nation, now: date) -> list[Objective]:
    return [
        Objective(
            name="Industrial Surge",
            description="Reach target civilian foundries for accelerated growth.",
            target_value=nation.civ_factories + 6,
            deadline=date(now.year + 2, 1, 1),
            reward=140,
            penalty=100,
        ),
        Objective(
            name="Arsenal Standard",
            description="Grow military works to sustain wartime output.",
            target_value=nation.mil_factories + 5,
            deadline=date(now.year + 2, 7, 1),
            reward=170,
            penalty=120,
        ),
        Objective(
            name="Strategic Reserve",
            description="Build reserve of key infantry equipment.",
            target_value=nation.stockpiles.get("Rifle Kits", 0) + 900,
            deadline=date(now.year + 1, 7, 1),
            reward=120,
            penalty=90,
        ),
        Objective(
            name="War Readiness",
            description="Raise readiness by drills, stockpiles, and stable logistics.",
            target_value=min(95.0, nation.war_readiness + 35),
            deadline=date(now.year + 1, 12, 1),
            reward=180,
            penalty=140,
        ),
    ]
