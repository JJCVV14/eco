from __future__ import annotations

from datetime import date
from typing import Iterable

from eco_game.data import PRODUCTION_TEMPLATES, generate_objectives
from eco_game.models import BuildingProject, BuildingType, Nation, Objective, ProductionLine, Resource, TradeDeal, WorldState


class GameEngine:
    def __init__(self, world: WorldState):
        self.world = world

    def add_log(self, message: str) -> None:
        stamp = self.world.current_date.isoformat()
        self.world.event_log.append(f"[{stamp}] {message}")

    def queue_construction(self, nation: Nation, kind: BuildingType) -> None:
        costs = {
            BuildingType.CIVILIAN: (110, 18),
            BuildingType.MILITARY: (95, 15),
            BuildingType.INFRA: (70, 11),
            BuildingType.SYNTH: (85, 13),
            BuildingType.EXTRACT: (80, 14),
        }
        price, weeks = costs[kind]
        if nation.treasury < price:
            raise ValueError("Insufficient treasury for project.")
        nation.treasury -= price
        nation.construction_queue.append(BuildingProject(kind, weeks))
        self.add_log(f"{nation.name} queued {kind.value} ({weeks} weeks).")

    def add_trade(self, buyer: Nation, seller: Nation, resource: Resource, units: float, weeks: int = 16) -> None:
        if seller.tag == buyer.tag:
            raise ValueError("Cannot trade with self")
        if seller.tag in buyer.embargoed_by:
            raise ValueError("Trade blocked by embargo.")
        reliability = 0.9
        if not seller.coastline_access and buyer.tag not in seller.neighbors:
            reliability = 0.6
        deal_in = TradeDeal(seller.tag, resource, units, True, reliability, weeks)
        deal_out = TradeDeal(buyer.tag, resource, units, False, reliability, weeks)
        buyer.trade_deals.append(deal_in)
        seller.trade_deals.append(deal_out)
        buyer.treasury -= int(6 * units)
        seller.treasury += int(6 * units)
        self.add_log(f"{buyer.name} imports {units:.1f} {resource.value}/wk from {seller.name}.")

    def cancel_trade(self, nation: Nation, index: int) -> None:
        if index < 0 or index >= len(nation.trade_deals):
            return
        deal = nation.trade_deals.pop(index)
        partner = self.world.nations.get(deal.partner)
        if partner:
            partner.trade_deals = [d for d in partner.trade_deals if not (d.partner == nation.tag and d.resource == deal.resource)]
        self.add_log(f"{nation.name} canceled trade with {deal.partner} for {deal.resource.value}.")

    def assign_factory(self, nation: Nation, template_name: str, delta: int) -> None:
        for line in nation.production_lines:
            if line.template_name == template_name:
                line.factories = max(0, line.factories + delta)
                if line.factories == 0:
                    nation.production_lines.remove(line)
                return
        if delta > 0:
            nation.production_lines.append(ProductionLine(template_name, delta))

    def _resource_balance(self, nation: Nation) -> tuple[dict[Resource, float], dict[Resource, float]]:
        produced = nation.weekly_resource_output()
        for deal in nation.trade_deals:
            if deal.import_to_me:
                produced[deal.resource] = produced.get(deal.resource, 0.0) + deal.units * deal.reliability
            else:
                produced[deal.resource] = produced.get(deal.resource, 0.0) - deal.units
        demand: dict[Resource, float] = {r: 0.0 for r in Resource}
        for line in nation.production_lines:
            tpl = PRODUCTION_TEMPLATES[line.template_name]
            for res, unit in tpl.resource_cost.items():
                demand[res] += unit * line.factories
        for r in Resource:
            produced.setdefault(r, 0.0)
        return produced, demand

    def _apply_construction(self, nation: Nation) -> None:
        speed_bonus = 1.0 + nation.infrastructure * 0.01 + nation.available_civ_for_construction() * 0.015
        completed: list[BuildingProject] = []
        for proj in nation.construction_queue:
            proj.weeks_remaining -= max(1, int(speed_bonus))
            if proj.weeks_remaining <= 0:
                completed.append(proj)
        for proj in completed:
            nation.construction_queue.remove(proj)
            if proj.building_type == BuildingType.CIVILIAN:
                nation.civ_factories += 1
            elif proj.building_type == BuildingType.MILITARY:
                nation.mil_factories += 1
            elif proj.building_type == BuildingType.INFRA:
                nation.infrastructure += 1
            elif proj.building_type == BuildingType.SYNTH:
                nation.synthetic_plants += 1
            elif proj.building_type == BuildingType.EXTRACT:
                nation.extraction_level += 1
            nation.score += 8
            self.add_log(f"{nation.name} completed {proj.building_type.value}.")

    def _apply_production(self, nation: Nation) -> None:
        produced, demand = self._resource_balance(nation)
        shortage_mult = 1.0
        for res, needed in demand.items():
            if needed > 0 and produced.get(res, 0.0) < needed:
                ratio = produced.get(res, 0.0) / needed
                shortage_mult = min(shortage_mult, max(0.2, ratio))
        for line in nation.production_lines:
            tpl = PRODUCTION_TEMPLATES[line.template_name]
            line.efficiency = min(1.0, line.efficiency + 0.02 + nation.infrastructure * 0.001)
            out = tpl.base_output * line.factories * line.efficiency * shortage_mult
            nation.stockpiles[tpl.name] = nation.stockpiles.get(tpl.name, 0.0) + round(out, 1)
        if shortage_mult < 0.95:
            nation.economic_strain += (1 - shortage_mult) * 1.2
        else:
            nation.economic_strain = max(0.0, nation.economic_strain - 0.2)

    def _apply_war(self, nation: Nation) -> None:
        total_equipment = (
            nation.stockpiles.get("Rifle Kits", 0)
            + nation.stockpiles.get("Field Cannons", 0) * 3
            + nation.stockpiles.get("Armored Vehicles", 0) * 5
            + nation.stockpiles.get("Aircraft Frames", 0) * 4
            + nation.stockpiles.get("Logistics Packs", 0) * 2
        )
        industry_factor = nation.civ_factories * 0.8 + nation.mil_factories * 1.4 + nation.infrastructure * 0.5
        nation.war_readiness = min(100.0, (total_equipment / 120.0) + industry_factor - nation.economic_strain * 1.5)
        if nation.at_war_with:
            upkeep = max(15.0, len(nation.at_war_with) * 18.0)
            nation.stockpiles["Rifle Kits"] = max(0.0, nation.stockpiles.get("Rifle Kits", 0) - upkeep)
            nation.stockpiles["Field Cannons"] = max(0.0, nation.stockpiles.get("Field Cannons", 0) - upkeep / 4)
            nation.treasury -= 20 * len(nation.at_war_with)
            nation.stability = max(0.2, nation.stability - 0.004 * len(nation.at_war_with))
        nation.score += nation.war_readiness * 0.03

    def _expire_trades(self, nation: Nation) -> None:
        expired: list[TradeDeal] = []
        for d in nation.trade_deals:
            d.weeks_remaining -= 1
            if d.weeks_remaining <= 0:
                expired.append(d)
        for d in expired:
            nation.trade_deals.remove(d)
            self.add_log(f"{nation.name} trade expired: {d.resource.value} with {d.partner}.")

    def _update_objectives(self, nation: Nation) -> None:
        if not nation.objectives:
            nation.objectives = generate_objectives(nation, self.world.current_date)
            return
        for obj in nation.objectives:
            if obj.completed or obj.failed:
                continue
            if obj.name == "Industrial Surge":
                obj.progress = nation.civ_factories
            elif obj.name == "Arsenal Standard":
                obj.progress = nation.mil_factories
            elif obj.name == "Strategic Reserve":
                obj.progress = nation.stockpiles.get("Rifle Kits", 0)
            elif obj.name == "War Readiness":
                obj.progress = nation.war_readiness
            if obj.progress >= obj.target_value:
                obj.completed = True
                nation.treasury += obj.reward
                nation.score += 25
                self.add_log(f"{nation.name} completed objective: {obj.name}.")
            elif self.world.current_date > obj.deadline:
                obj.failed = True
                nation.treasury -= obj.penalty
                nation.stability = max(0.1, nation.stability - 0.05)
                self.add_log(f"{nation.name} failed objective: {obj.name}.")

    def _random_events(self, nation: Nation, ai: bool = False) -> None:
        rng = self.world.rng()
        if rng.random() > 0.20:
            return
        roll = rng.randint(1, 8)
        if roll == 1:
            nation.treasury += 90
            self.add_log(f"{nation.name} enjoyed an export boom (+90 treasury).")
        elif roll == 2:
            nation.stability = max(0.1, nation.stability - 0.04)
            nation.economic_strain += 1.5
            self.add_log(f"Labor strikes disrupt {nation.name}.")
        elif roll == 3:
            nation.resource_base[Resource.IRON] = nation.resource_base.get(Resource.IRON, 0) + 1.5
            self.add_log(f"New iron vein discovered in {nation.name}.")
        elif roll == 4:
            nation.embargoed_by = list(set(nation.embargoed_by + [rng.choice(list(self.world.nations.keys()))]))
            self.add_log(f"{nation.name} faces a fresh embargo from rivals.")
        elif roll == 5:
            nation.treasury -= 70
            nation.infrastructure = max(1, nation.infrastructure - 1)
            self.add_log(f"Severe storms damage infrastructure in {nation.name}.")
        elif roll == 6:
            nation.synthetic_plants += 1
            self.add_log(f"{nation.name} funded a synthetic fuels breakthrough.")
        elif roll == 7 and not ai:
            nation.score += 10
            self.add_log(f"{nation.name} propaganda campaign raised morale.")
        elif roll == 8:
            nation.war_pressure += 3
            self.add_log(f"Border skirmishes increase war pressure for {nation.name}.")

    def _war_diplomacy_phase(self) -> None:
        tags = list(self.world.nations.keys())
        rng = self.world.rng()
        for tag in tags:
            nation = self.world.nations[tag]
            if nation.war_pressure > 65 and nation.war_readiness > 45 and rng.random() < 0.10:
                potential = [t for t in tags if t != tag and t not in nation.at_war_with]
                if potential:
                    target = rng.choice(potential)
                    nation.at_war_with.append(target)
                    self.world.nations[target].at_war_with.append(tag)
                    self.add_log(f"WAR: {nation.name} declared war on {self.world.nations[target].name}.")
            if nation.at_war_with and nation.war_readiness > 70 and rng.random() < 0.08:
                enemy_tag = rng.choice(nation.at_war_with)
                enemy = self.world.nations[enemy_tag]
                my_power = nation.war_readiness + nation.mil_factories * 2 + nation.infrastructure
                enemy_power = enemy.war_readiness + enemy.mil_factories * 2 + enemy.infrastructure
                if my_power > enemy_power * 1.2:
                    nation.score += 80
                    enemy.score -= 30
                    nation.at_war_with.remove(enemy_tag)
                    if tag in enemy.at_war_with:
                        enemy.at_war_with.remove(tag)
                    self.add_log(f"{nation.name} forced a favorable armistice on {enemy.name}.")

    def _ai_choose_projects(self, nation: Nation) -> None:
        if len(nation.construction_queue) > 3 or nation.treasury < 70:
            return
        try:
            if nation.civ_factories < 18:
                self.queue_construction(nation, BuildingType.CIVILIAN)
            elif nation.mil_factories < nation.civ_factories:
                self.queue_construction(nation, BuildingType.MILITARY)
            elif nation.infrastructure < 8:
                self.queue_construction(nation, BuildingType.INFRA)
            elif nation.synthetic_plants < 4:
                self.queue_construction(nation, BuildingType.SYNTH)
        except ValueError:
            return

    def _ai_trade(self, nation: Nation) -> None:
        if len(nation.trade_deals) > 5:
            return
        produced, demand = self._resource_balance(nation)
        deficits = [r for r in Resource if demand.get(r, 0) > produced.get(r, 0) + 0.3]
        for res in deficits[:2]:
            sellers = [n for n in self.world.nations.values() if n.tag != nation.tag and n.weekly_resource_output().get(res, 0) > 2]
            if sellers and nation.treasury > 80:
                seller = max(sellers, key=lambda n: n.weekly_resource_output().get(res, 0))
                self.add_trade(nation, seller, res, 2.0, weeks=12)

    def _ai_manage_production(self, nation: Nation) -> None:
        if nation.free_mil_factories() > 0:
            priorities = ["Rifle Kits", "Field Cannons", "Armored Vehicles", "Aircraft Frames", "Logistics Packs"]
            pick = priorities[(self.world.current_date.month + len(nation.production_lines)) % len(priorities)]
            self.assign_factory(nation, pick, min(2, nation.free_mil_factories()))
        if nation.economic_strain > 8:
            for line in nation.production_lines:
                if line.template_name == "Armored Vehicles" and line.factories > 1:
                    line.factories -= 1
                    break

    def _weekly_income(self, nation: Nation) -> None:
        export_gain = sum(d.units * 4 for d in nation.trade_deals if not d.import_to_me)
        upkeep = nation.civ_factories * 2 + nation.mil_factories * 3 + max(0, len(nation.at_war_with) * 10)
        nation.treasury += int(35 + export_gain - upkeep + nation.stability * 20)

    def step_week(self) -> None:
        for nation in self.world.nations.values():
            self._weekly_income(nation)
            self._expire_trades(nation)
            self._apply_construction(nation)
            self._apply_production(nation)
            self._apply_war(nation)
            self._update_objectives(nation)
            self._random_events(nation, ai=nation.tag != self.world.player_tag)
        for nation in self.world.nations.values():
            if nation.tag != self.world.player_tag:
                self._ai_choose_projects(nation)
                self._ai_trade(nation)
                self._ai_manage_production(nation)
                nation.war_pressure += 0.2
        self._war_diplomacy_phase()
        self.world.advance_week()


START_YEARS = [1936, 1938, 1940, 1942, 1944, 1946, 1948, 1950]


def initialize_world(player_tag: str, start_year: int, nations: dict[str, Nation]) -> WorldState:
    world = WorldState(current_date=date(start_year, 1, 1), nations=nations, player_tag=player_tag)
    for nation in world.nations.values():
        nation.objectives = generate_objectives(nation, world.current_date)
    return world


def rankings(nations: Iterable[Nation]) -> list[Nation]:
    return sorted(
        nations,
        key=lambda n: n.score + n.civ_factories * 3 + n.mil_factories * 4 + n.war_readiness * 2,
        reverse=True,
    )
