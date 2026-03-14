from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from enum import Enum
from typing import Any
import random


class Resource(str, Enum):
    IRON = "Iron"
    FUEL = "Fuel"
    ALLOY = "Alloy"
    LATEX = "Latex"
    TUNGSTEN = "Tungsten"
    CHROMITE = "Chromite"


class BuildingType(str, Enum):
    CIVILIAN = "Civilian Foundry"
    MILITARY = "Military Works"
    INFRA = "Logistics Infrastructure"
    SYNTH = "Synthetic Plant"
    EXTRACT = "Extraction Upgrade"


@dataclass
class BuildingProject:
    building_type: BuildingType
    weeks_remaining: int
    location: str = "National"


@dataclass
class ProductionTemplate:
    name: str
    category: str
    base_output: float
    resource_cost: dict[Resource, float]


@dataclass
class ProductionLine:
    template_name: str
    factories: int
    efficiency: float = 0.25


@dataclass
class TradeDeal:
    partner: str
    resource: Resource
    units: float
    import_to_me: bool
    reliability: float
    weeks_remaining: int


@dataclass
class Objective:
    name: str
    description: str
    target_value: float
    deadline: date
    progress: float = 0.0
    reward: int = 0
    penalty: int = 0
    completed: bool = False
    failed: bool = False


@dataclass
class Nation:
    name: str
    tag: str
    civ_factories: int
    mil_factories: int
    infrastructure: int
    synthetic_plants: int
    extraction_level: int
    treasury: int
    stability: float
    war_pressure: float
    coastline_access: bool
    neighbors: list[str]
    resource_base: dict[Resource, float]
    stockpiles: dict[str, float]
    production_lines: list[ProductionLine] = field(default_factory=list)
    construction_queue: list[BuildingProject] = field(default_factory=list)
    trade_deals: list[TradeDeal] = field(default_factory=list)
    objectives: list[Objective] = field(default_factory=list)
    at_war_with: list[str] = field(default_factory=list)
    embargoed_by: list[str] = field(default_factory=list)
    war_readiness: float = 0.0
    economic_strain: float = 0.0
    score: float = 0.0

    def available_civ_for_construction(self) -> int:
        reserved = len([d for d in self.trade_deals if d.import_to_me])
        return max(1, self.civ_factories - reserved)

    def active_mil_factories(self) -> int:
        assigned = sum(line.factories for line in self.production_lines)
        return min(assigned, self.mil_factories)

    def free_mil_factories(self) -> int:
        return max(0, self.mil_factories - self.active_mil_factories())

    def weekly_resource_output(self) -> dict[Resource, float]:
        factor = 1.0 + (self.infrastructure * 0.02) + (self.extraction_level * 0.04)
        out: dict[Resource, float] = {}
        for k, v in self.resource_base.items():
            out[k] = round(v * factor, 2)
        out[Resource.FUEL] = out.get(Resource.FUEL, 0.0) + self.synthetic_plants * 3.5
        out[Resource.LATEX] = out.get(Resource.LATEX, 0.0) + self.synthetic_plants * 1.5
        return out

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resource_base"] = {k.value: v for k, v in self.resource_base.items()}
        for deal in data["trade_deals"]:
            deal["resource"] = deal["resource"].value
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Nation":
        rb = {Resource(k): v for k, v in data["resource_base"].items()}
        nation = Nation(
            name=data["name"],
            tag=data["tag"],
            civ_factories=data["civ_factories"],
            mil_factories=data["mil_factories"],
            infrastructure=data["infrastructure"],
            synthetic_plants=data["synthetic_plants"],
            extraction_level=data["extraction_level"],
            treasury=data["treasury"],
            stability=data["stability"],
            war_pressure=data["war_pressure"],
            coastline_access=data["coastline_access"],
            neighbors=data["neighbors"],
            resource_base=rb,
            stockpiles=data["stockpiles"],
            production_lines=[ProductionLine(**line) for line in data["production_lines"]],
            construction_queue=[
                BuildingProject(BuildingType(p["building_type"]), p["weeks_remaining"], p["location"])
                for p in data["construction_queue"]
            ],
            trade_deals=[
                TradeDeal(
                    partner=d["partner"],
                    resource=Resource(d["resource"]),
                    units=d["units"],
                    import_to_me=d["import_to_me"],
                    reliability=d["reliability"],
                    weeks_remaining=d["weeks_remaining"],
                )
                for d in data["trade_deals"]
            ],
            objectives=[
                Objective(
                    name=o["name"],
                    description=o["description"],
                    target_value=o["target_value"],
                    deadline=date.fromisoformat(o["deadline"]),
                    progress=o["progress"],
                    reward=o["reward"],
                    penalty=o["penalty"],
                    completed=o["completed"],
                    failed=o["failed"],
                )
                for o in data["objectives"]
            ],
            at_war_with=data["at_war_with"],
            embargoed_by=data["embargoed_by"],
            war_readiness=data["war_readiness"],
            economic_strain=data["economic_strain"],
            score=data["score"],
        )
        return nation


@dataclass
class WorldState:
    current_date: date
    nations: dict[str, Nation]
    player_tag: str
    event_log: list[str] = field(default_factory=list)
    seed: int = 42

    def player(self) -> Nation:
        return self.nations[self.player_tag]

    def advance_week(self) -> None:
        self.current_date += timedelta(days=7)

    def rng(self) -> random.Random:
        return random.Random(self.seed + self.current_date.toordinal())

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_date": self.current_date.isoformat(),
            "nations": {k: n.to_dict() for k, n in self.nations.items()},
            "player_tag": self.player_tag,
            "event_log": self.event_log[-250:],
            "seed": self.seed,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "WorldState":
        world = WorldState(
            current_date=date.fromisoformat(data["current_date"]),
            nations={k: Nation.from_dict(v) for k, v in data["nations"].items()},
            player_tag=data["player_tag"],
            event_log=data.get("event_log", []),
            seed=data.get("seed", 42),
        )
        return world
