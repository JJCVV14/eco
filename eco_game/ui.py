from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, filedialog

from eco_game.data import PRODUCTION_TEMPLATES, load_nations
from eco_game.models import BuildingType, Nation, Resource
from eco_game.persistence import SAVE_DIR, load_game, save_game
from eco_game.simulation import GameEngine, START_YEARS, initialize_world, rankings


class NewGameDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, nations: dict[str, Nation]):
        super().__init__(parent)
        self.title("New Campaign")
        self.resizable(False, False)
        self.result: tuple[str, int] | None = None

        ttk.Label(self, text="Choose Nation").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.nation_var = tk.StringVar(value=next(iter(nations.keys())))
        nation_names = [f"{n.tag} - {n.name}" for n in nations.values()]
        self.combo_nation = ttk.Combobox(self, values=nation_names, width=42, state="readonly")
        self.combo_nation.current(0)
        self.combo_nation.grid(row=1, column=0, padx=8, pady=4)

        ttk.Label(self, text="Start Year").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.combo_year = ttk.Combobox(self, values=START_YEARS, width=15, state="readonly")
        self.combo_year.current(0)
        self.combo_year.grid(row=3, column=0, padx=8, pady=4, sticky="w")

        ttk.Button(self, text="Start", command=self._confirm).grid(row=4, column=0, padx=8, pady=10, sticky="e")

    def _confirm(self) -> None:
        chosen = self.combo_nation.get().split(" - ")[0]
        year = int(self.combo_year.get())
        self.result = (chosen, year)
        self.destroy()


class GameUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Forge of Nations: Industry & War Economy")
        self.root.geometry("1250x760")

        self.engine: GameEngine | None = None

        self._build_layout()
        self._new_game()

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)

        self.lbl_date = ttk.Label(top, text="Date: -")
        self.lbl_date.pack(side="left", padx=4)
        self.lbl_nation = ttk.Label(top, text="Nation: -")
        self.lbl_nation.pack(side="left", padx=12)
        self.lbl_treasury = ttk.Label(top, text="Treasury: -")
        self.lbl_treasury.pack(side="left", padx=12)

        ttk.Button(top, text="Advance 1 Week", command=self._advance_one).pack(side="right", padx=3)
        ttk.Button(top, text="Advance 8 Weeks", command=lambda: self._advance_bulk(8)).pack(side="right", padx=3)
        ttk.Button(top, text="Save", command=self._save).pack(side="right", padx=3)
        ttk.Button(top, text="Load", command=self._load).pack(side="right", padx=3)
        ttk.Button(top, text="New Campaign", command=self._new_game).pack(side="right", padx=3)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tabs: dict[str, ttk.Frame] = {}
        for name in ["Overview", "Construction", "Production", "Trade", "Objectives", "World", "Events"]:
            frame = ttk.Frame(self.notebook)
            self.tabs[name] = frame
            self.notebook.add(frame, text=name)

        self._build_overview_tab()
        self._build_construction_tab()
        self._build_production_tab()
        self._build_trade_tab()
        self._build_objectives_tab()
        self._build_world_tab()
        self._build_events_tab()

    def _player(self) -> Nation:
        assert self.engine is not None
        return self.engine.world.player()

    def _build_overview_tab(self) -> None:
        frame = self.tabs["Overview"]
        self.txt_overview = tk.Text(frame, height=30)
        self.txt_overview.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_construction_tab(self) -> None:
        frame = self.tabs["Construction"]
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(frame)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self.lst_buildings = tk.Listbox(left, height=10)
        self.lst_buildings.pack()
        for b in BuildingType:
            self.lst_buildings.insert("end", b.value)
        ttk.Button(left, text="Queue Building", command=self._queue_building).pack(pady=6)

        ttk.Label(right, text="Construction Queue").pack(anchor="w")
        self.lst_queue = tk.Listbox(right)
        self.lst_queue.pack(fill="both", expand=True)

    def _build_production_tab(self) -> None:
        frame = self.tabs["Production"]
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(frame)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        ttk.Label(left, text="Production Templates").pack(anchor="w")
        self.lst_templates = tk.Listbox(left, height=10)
        for name, tpl in PRODUCTION_TEMPLATES.items():
            self.lst_templates.insert("end", f"{name} ({tpl.category})")
        self.lst_templates.pack()

        ttk.Button(left, text="+1 Factory", command=lambda: self._adjust_line(+1)).pack(pady=3)
        ttk.Button(left, text="-1 Factory", command=lambda: self._adjust_line(-1)).pack(pady=3)

        ttk.Label(right, text="Production Lines").pack(anchor="w")
        self.lst_lines = tk.Listbox(right)
        self.lst_lines.pack(fill="both", expand=True)

    def _build_trade_tab(self) -> None:
        frame = self.tabs["Trade"]
        controls = ttk.Frame(frame)
        controls.pack(fill="x", padx=8, pady=8)

        self.partner_var = tk.StringVar()
        self.resource_var = tk.StringVar(value=Resource.IRON.value)
        self.units_var = tk.DoubleVar(value=2.0)

        ttk.Label(controls, text="Partner").grid(row=0, column=0, padx=4)
        self.combo_partner = ttk.Combobox(controls, width=18, state="readonly")
        self.combo_partner.grid(row=0, column=1, padx=4)
        ttk.Label(controls, text="Resource").grid(row=0, column=2, padx=4)
        self.combo_resource = ttk.Combobox(controls, values=[r.value for r in Resource], width=14, state="readonly")
        self.combo_resource.current(0)
        self.combo_resource.grid(row=0, column=3, padx=4)
        ttk.Label(controls, text="Units/wk").grid(row=0, column=4, padx=4)
        ttk.Entry(controls, textvariable=self.units_var, width=8).grid(row=0, column=5, padx=4)
        ttk.Button(controls, text="Create Import", command=self._create_import).grid(row=0, column=6, padx=6)
        ttk.Button(controls, text="Cancel Selected", command=self._cancel_trade).grid(row=0, column=7, padx=6)

        self.lst_trades = tk.Listbox(frame)
        self.lst_trades.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_objectives_tab(self) -> None:
        frame = self.tabs["Objectives"]
        self.lst_objectives = tk.Listbox(frame)
        self.lst_objectives.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_world_tab(self) -> None:
        frame = self.tabs["World"]
        self.lst_world = tk.Listbox(frame)
        self.lst_world.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_events_tab(self) -> None:
        frame = self.tabs["Events"]
        self.lst_events = tk.Listbox(frame)
        self.lst_events.pack(fill="both", expand=True, padx=8, pady=8)

    def _new_game(self) -> None:
        nations = load_nations()
        dlg = NewGameDialog(self.root, nations)
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        tag, year = dlg.result
        world = initialize_world(tag, year, nations)
        self.engine = GameEngine(world)
        self.engine.add_log(f"Campaign begins with {world.player().name} in {year}.")
        self._refresh_all()

    def _save(self) -> None:
        if not self.engine:
            return
        name = simpledialog.askstring("Save Game", "Save name:", parent=self.root)
        if not name:
            return
        path = save_game(self.engine.world, name)
        messagebox.showinfo("Saved", f"Saved to {path}")

    def _load(self) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        path = filedialog.askopenfilename(initialdir=str(SAVE_DIR), filetypes=[("JSON", "*.json")])
        if not path:
            return
        world = load_game(Path(path))
        self.engine = GameEngine(world)
        self._refresh_all()

    def _advance_one(self) -> None:
        if not self.engine:
            return
        self.engine.step_week()
        self._refresh_all()

    def _advance_bulk(self, weeks: int) -> None:
        if not self.engine:
            return
        for _ in range(weeks):
            self.engine.step_week()
        self._refresh_all()

    def _queue_building(self) -> None:
        if not self.engine:
            return
        sel = self.lst_buildings.curselection()
        if not sel:
            return
        kind = list(BuildingType)[sel[0]]
        try:
            self.engine.queue_construction(self._player(), kind)
            self._refresh_all()
        except ValueError as e:
            messagebox.showerror("Construction", str(e))

    def _adjust_line(self, delta: int) -> None:
        if not self.engine:
            return
        sel = self.lst_templates.curselection()
        if not sel:
            return
        name = list(PRODUCTION_TEMPLATES.keys())[sel[0]]
        player = self._player()
        if delta > 0 and player.free_mil_factories() <= 0:
            messagebox.showwarning("Production", "No free military factories.")
            return
        self.engine.assign_factory(player, name, delta)
        self._refresh_all()

    def _create_import(self) -> None:
        if not self.engine:
            return
        player = self._player()
        partner_tag = self.combo_partner.get().split(" - ")[0]
        if not partner_tag:
            return
        partner = self.engine.world.nations[partner_tag]
        resource = Resource(self.combo_resource.get())
        units = max(0.5, float(self.units_var.get()))
        try:
            self.engine.add_trade(player, partner, resource, units)
            self._refresh_all()
        except ValueError as e:
            messagebox.showerror("Trade", str(e))

    def _cancel_trade(self) -> None:
        if not self.engine:
            return
        sel = self.lst_trades.curselection()
        if not sel:
            return
        self.engine.cancel_trade(self._player(), sel[0])
        self._refresh_all()

    def _refresh_all(self) -> None:
        if not self.engine:
            return
        world = self.engine.world
        player = world.player()

        self.lbl_date.configure(text=f"Date: {world.current_date}")
        self.lbl_nation.configure(text=f"Nation: {player.name} ({player.tag})")
        self.lbl_treasury.configure(text=f"Treasury: {player.treasury}")

        self.txt_overview.delete("1.0", "end")
        lines = [
            f"Civilian Foundries: {player.civ_factories}",
            f"Military Works: {player.mil_factories} (free {player.free_mil_factories()})",
            f"Infrastructure: {player.infrastructure}",
            f"Synthetic Plants: {player.synthetic_plants}",
            f"Extraction Level: {player.extraction_level}",
            f"Stability: {player.stability:.2f}",
            f"War Pressure: {player.war_pressure:.1f}",
            f"War Readiness: {player.war_readiness:.1f}",
            f"Economic Strain: {player.economic_strain:.1f}",
            f"At War With: {', '.join(player.at_war_with) if player.at_war_with else 'None'}",
            "",
            "Resource Output (weekly):",
        ]
        for r, v in player.weekly_resource_output().items():
            lines.append(f"  - {r.value}: {v:.1f}")
        lines.append("")
        lines.append("Stockpiles:")
        for k, v in player.stockpiles.items():
            lines.append(f"  - {k}: {v:.1f}")
        self.txt_overview.insert("1.0", "\n".join(lines))

        self.lst_queue.delete(0, "end")
        for q in player.construction_queue:
            self.lst_queue.insert("end", f"{q.building_type.value} | {q.weeks_remaining}w remaining")

        self.lst_lines.delete(0, "end")
        for line in player.production_lines:
            tpl = PRODUCTION_TEMPLATES[line.template_name]
            self.lst_lines.insert(
                "end",
                f"{line.template_name}: {line.factories} fac, eff {line.efficiency:.2f}, base {tpl.base_output}/fac",
            )

        self.combo_partner["values"] = [
            f"{n.tag} - {n.name}" for n in world.nations.values() if n.tag != world.player_tag
        ]
        if self.combo_partner["values"] and not self.combo_partner.get():
            self.combo_partner.current(0)

        self.lst_trades.delete(0, "end")
        for t in player.trade_deals:
            mode = "Import" if t.import_to_me else "Export"
            self.lst_trades.insert(
                "end",
                f"{mode}: {t.resource.value} {t.units:.1f}/wk with {t.partner}, rel {t.reliability:.2f}, {t.weeks_remaining}w",
            )

        self.lst_objectives.delete(0, "end")
        for o in player.objectives:
            status = "Done" if o.completed else "Failed" if o.failed else "Active"
            self.lst_objectives.insert(
                "end",
                f"[{status}] {o.name}: {o.progress:.1f}/{o.target_value:.1f} by {o.deadline.isoformat()} | {o.description}",
            )

        self.lst_world.delete(0, "end")
        for i, n in enumerate(rankings(world.nations.values()), start=1):
            self.lst_world.insert(
                "end",
                f"#{i} {n.name} ({n.tag}) | Score {n.score:.1f} | Civ {n.civ_factories} Mil {n.mil_factories} | WR {n.war_readiness:.1f}",
            )

        self.lst_events.delete(0, "end")
        for e in world.event_log[-200:]:
            self.lst_events.insert("end", e)


def run_app() -> None:
    root = tk.Tk()
    GameUI(root)
    root.mainloop()
