"""Local, deterministic AC-storage concept workbench; never an installation approval.

Interval-average active-power model, not a protection, RMS-current, transient,
islanding or tariff engine. See docs/energy/CALCULATION_CONTRACT.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

MODEL_VERSION = "energy-ac-self-consumption-v0.1"
NOTICE = "CONCEPT ONLY - NOT FOR INSTALLATION"
PROJECT_KEYS = {
    "schema_version",
    "id",
    "data_class",
    "evidence_refs",
    "assumptions",
    "unknowns",
    "scenario",
}


def number(value: Any, name: str, minimum: float = 0.0) -> float:
    """Reject booleans, numeric strings, negative and non-finite values."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    return float(value)


@dataclass(frozen=True)
class Scenario:
    grid_phases: int
    topology: str
    battery_phase: int
    nominal_kwh: float
    minimum_soc: float
    maximum_soc: float
    initial_soc: float
    charge_limit_kw_ac: float
    discharge_limit_kw_ac: float
    charge_efficiency: float
    discharge_efficiency: float
    auxiliary_kw_ac: float
    interval_minutes: int

    def __post_init__(self) -> None:
        if type(self.grid_phases) is not int or self.grid_phases not in (1, 3):
            raise ValueError("grid_phases must be 1 or 3")
        if self.topology not in ("single_phase", "three_phase_balanced"):
            raise ValueError("unsupported topology")
        if self.topology == "three_phase_balanced" and self.grid_phases != 3:
            raise ValueError("three_phase_balanced requires three grid phases")
        if type(self.battery_phase) is not int or not 1 <= self.battery_phase <= self.grid_phases:
            raise ValueError("battery_phase must identify an existing phase (1-based)")
        if self.topology == "three_phase_balanced" and self.battery_phase != 1:
            raise ValueError("battery_phase must be 1 (unused) for a balanced system")
        for name in (
            "nominal_kwh",
            "minimum_soc",
            "maximum_soc",
            "initial_soc",
            "charge_limit_kw_ac",
            "discharge_limit_kw_ac",
            "charge_efficiency",
            "discharge_efficiency",
            "auxiliary_kw_ac",
        ):
            number(getattr(self, name), name)
        if self.nominal_kwh <= 0:
            raise ValueError("nominal_kwh must be positive")
        if not 0 <= self.minimum_soc <= self.initial_soc <= self.maximum_soc <= 1:
            raise ValueError("require 0 <= minimum_soc <= initial_soc <= maximum_soc <= 1")
        if self.minimum_soc == self.maximum_soc:
            raise ValueError("SOC operating window must be nonzero")
        if not 0 < self.charge_efficiency <= 1 or not 0 < self.discharge_efficiency <= 1:
            raise ValueError("efficiencies must be in (0, 1]")
        if type(self.interval_minutes) is not int or not 1 <= self.interval_minutes <= 60:
            raise ValueError("interval_minutes must be an integer from 1 through 60")

    @classmethod
    def from_dict(cls, data: Any) -> Scenario:
        if not isinstance(data, dict) or set(data) != {f.name for f in fields(cls)}:
            raise ValueError("scenario fields must match the documented contract exactly")
        return cls(**data)

    def allocation(self, power_kw: float) -> list[float]:
        if self.topology == "three_phase_balanced":
            return [power_kw / 3.0] * 3
        return [power_kw if i == self.battery_phase - 1 else 0.0 for i in range(self.grid_phases)]


def validate_project(project: Any) -> Scenario | None:
    if not isinstance(project, dict) or set(project) != PROJECT_KEYS:
        raise ValueError("project fields must match the documented contract exactly")
    if type(project["schema_version"]) is not int or project["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    check_id(project["id"])
    if project["data_class"] not in ("synthetic", "customer"):
        raise ValueError("data_class must be synthetic or customer")
    for key in ("evidence_refs", "assumptions", "unknowns"):
        values = project[key]
        if not isinstance(values, list) or any(
            not isinstance(v, str) or not v.strip() or len(v) > 2000 for v in values
        ):
            raise ValueError(f"{key} must contain nonempty strings of at most 2000 characters")
    if not project["assumptions"]:
        raise ValueError("record the model/input assumptions explicitly")
    if project["scenario"] is None:
        return None
    return Scenario.from_dict(project["scenario"])


def check_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value):
        raise ValueError("project id must be 1-64 lowercase letters, digits or hyphens")
    return value


def read_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique)


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n"


@dataclass(frozen=True)
class Sample:
    timestamp: datetime
    load_kw: tuple[float, ...]
    pv_kw: tuple[float, ...]


def profile_headers(phases: int) -> list[str]:
    return ["timestamp"] + [
        name for i in range(1, phases + 1) for name in (f"load_l{i}_kw", f"pv_l{i}_kw")
    ]


def read_profile(text: str, scenario: Scenario) -> list[Sample]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != profile_headers(scenario.grid_phases):
        raise ValueError(
            "CSV headers/order must be " + ",".join(profile_headers(scenario.grid_phases))
        )
    rows = []
    for line, record in enumerate(reader, start=2):
        try:
            if None in record or any(v is None for v in record.values()):
                raise ValueError("unexpected or missing columns")
            timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("timestamp needs a UTC offset")
            load = tuple(float(record[f"load_l{i}_kw"]) for i in range(1, scenario.grid_phases + 1))
            pv = tuple(float(record[f"pv_l{i}_kw"]) for i in range(1, scenario.grid_phases + 1))
            rows.append(Sample(timestamp.astimezone(UTC), load, pv))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"invalid CSV row {line}: {exc}") from exc
    validate_samples(rows, scenario)
    return rows


def validate_samples(samples: list[Sample], scenario: Scenario) -> None:
    if not samples:
        raise ValueError("profile is empty")
    previous = None
    for sample in samples:
        if sample.timestamp.tzinfo is None or sample.timestamp.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        stamp = sample.timestamp.astimezone(UTC)
        if previous is not None and stamp - previous != timedelta(
            minutes=scenario.interval_minutes
        ):
            raise ValueError("profile has duplicates, gaps, overlaps or unsorted timestamps")
        previous = stamp
        if len(sample.load_kw) != scenario.grid_phases or len(sample.pv_kw) != scenario.grid_phases:
            raise ValueError("sample phase count differs from scenario")
        for value in sample.load_kw + sample.pv_kw:
            number(value, "sample power")


def dc_current_a(ac_power_kw: float, minimum_battery_v: float, efficiency: float) -> float:
    """Steady-state estimate only; does not select a fuse, conductor or BMS."""
    power = number(ac_power_kw, "ac_power_kw")
    voltage = number(minimum_battery_v, "minimum_battery_v")
    eta = number(efficiency, "efficiency")
    if voltage <= 0 or not 0 < eta <= 1:
        raise ValueError("positive minimum battery voltage and efficiency in (0,1] required")
    return power * 1000 / (voltage * eta)


def simulate(scenario: Scenario, samples: list[Sample]) -> dict[str, Any]:
    """Greedy self-consumption, aggregate phase-summed meter, no tariff optimisation."""
    validate_samples(samples, scenario)
    dt = scenario.interval_minutes / 60.0
    energy = scenario.initial_soc * scenario.nominal_kwh
    initial_energy = energy
    low = scenario.minimum_soc * scenario.nominal_kwh
    high = scenario.maximum_soc * scenario.nominal_kwh
    totals = dict.fromkeys(
        (
            "load_kwh",
            "pv_kwh",
            "baseline_import_kwh",
            "baseline_export_kwh",
            "grid_import_kwh",
            "grid_export_kwh",
            "charge_kwh_ac",
            "discharge_kwh_ac",
            "conversion_loss_kwh",
            "auxiliary_kwh",
        ),
        0.0,
    )
    peak_import = [0.0] * scenario.grid_phases
    peak_export = [0.0] * scenario.grid_phases
    trace = []
    for sample in samples:
        base = [load - pv for load, pv in zip(sample.load_kw, sample.pv_kw, strict=True)]
        aux = scenario.allocation(scenario.auxiliary_kw_ac)
        net = sum(base) + scenario.auxiliary_kw_ac
        charge = discharge = 0.0
        before = energy
        if net < 0:
            charge = min(
                -net,
                scenario.charge_limit_kw_ac,
                max(0, high - energy) / (scenario.charge_efficiency * dt),
            )
            energy += charge * scenario.charge_efficiency * dt
        else:
            discharge = min(
                net,
                scenario.discharge_limit_kw_ac,
                max(0, energy - low) * scenario.discharge_efficiency / dt,
            )
            energy -= discharge * dt / scenario.discharge_efficiency
        allocated = scenario.allocation(charge - discharge)
        grid = [base[i] + aux[i] + allocated[i] for i in range(scenario.grid_phases)]
        summed = sum(grid)
        loss = charge * dt - discharge * dt - (energy - before)
        totals["load_kwh"] += sum(sample.load_kw) * dt
        totals["pv_kwh"] += sum(sample.pv_kw) * dt
        totals["baseline_import_kwh"] += max(0, sum(base)) * dt
        totals["baseline_export_kwh"] += max(0, -sum(base)) * dt
        totals["grid_import_kwh"] += max(0, summed) * dt
        totals["grid_export_kwh"] += max(0, -summed) * dt
        totals["charge_kwh_ac"] += charge * dt
        totals["discharge_kwh_ac"] += discharge * dt
        totals["conversion_loss_kwh"] += loss
        totals["auxiliary_kwh"] += scenario.auxiliary_kw_ac * dt
        for i, value in enumerate(grid):
            peak_import[i] = max(peak_import[i], value)
            peak_export[i] = max(peak_export[i], -value)
        trace.append(
            {
                "timestamp": sample.timestamp.astimezone(UTC).isoformat(),
                "grid_kw_by_phase": grid,
                "charge_kw_ac": charge,
                "discharge_kw_ac": discharge,
                "stored_kwh": energy,
            }
        )
    delta = energy - initial_energy
    balance = (
        totals["pv_kwh"]
        + totals["grid_import_kwh"]
        - totals["load_kwh"]
        - totals["grid_export_kwh"]
        - totals["auxiliary_kwh"]
        - totals["conversion_loss_kwh"]
        - delta
    )
    if abs(balance) > 1e-7 * max(1, totals["pv_kwh"] + totals["grid_import_kwh"]):
        raise ArithmeticError("energy conservation check failed")
    return {
        "model_version": MODEL_VERSION,
        "release_status": "concept_only",
        "interval_count": len(samples),
        "duration_hours": len(samples) * dt,
        "first_interval_start": trace[0]["timestamp"],
        "last_interval_end": (
            samples[-1].timestamp.astimezone(UTC) + timedelta(minutes=scenario.interval_minutes)
        ).isoformat(),
        "totals": totals,
        "initial_stored_kwh": initial_energy,
        "final_stored_kwh": energy,
        "stored_energy_delta_kwh": delta,
        "energy_balance_error_kwh": balance,
        "peak_interval_import_kw_by_phase": peak_import,
        "peak_interval_export_kw_by_phase": peak_export,
        "trace": trace,
    }


def topology_mermaid(scenario: Scenario) -> str:
    title = (
        "Single-phase storage"
        if scenario.topology == "single_phase"
        else "Balanced three-phase storage"
    )
    return f'''flowchart TB
    GRID["Utility grid - {scenario.grid_phases} phase(s)"] <--> METER["Whole-site measurement"]
    METER <--> BOARD["Main AC distribution"]
    PV["Existing PV inverter(s) - verify count and phases"] --> BOARD
    BOARD --> LOAD["Normal loads"]
    BOARD <-->|"Dedicated AC feeder; protection TBD"| INV["{title}"]
    INV <-->|"Short protected DC path; BMS shutdown"| BAT["Battery bank - {scenario.nominal_kwh:g} kWh nominal"]
    METER -. "Data only" .-> CTRL["Local energy controller"]
    CTRL -. "Setpoints within hardware limits" .-> INV
    NOTE["{NOTICE}: no backup output or grid-isolation design included"]
'''


def topology_svg(scenario: Scenario, project_id: str) -> str:
    label = (
        "1-phase battery inverter"
        if scenario.topology == "single_phase"
        else "3-phase battery inverter system"
    )

    def box(x: int, y: int, w: int, text: str) -> str:
        return f'<rect x="{x}" y="{y}" width="{w}" height="56" rx="5" fill="white" stroke="#334155"/><text x="{x + w / 2}" y="{y + 33}" text-anchor="middle">{escape(text)}</text>'

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="700" viewBox="0 0 1100 700">',
        '<rect width="1100" height="700" fill="#f8fafc"/>',
        '<g font-family="sans-serif" font-size="17" fill="#0f172a">',
        f'<text x="40" y="40" font-size="24">{escape(project_id)} - functional AC-coupled topology</text>',
        f'<text x="40" y="72" fill="#b91c1c">{NOTICE}</text>',
        '<g fill="none" stroke="#334155" stroke-width="2">',
        '<path d="M550 166V204 M550 260V310 M400 338H290 M700 338H810 M550 366V442 M550 498V564"/>',
        "</g>",
        box(400, 110, 300, f"Grid ({scenario.grid_phases} phases)"),
        box(400, 204, 300, "Whole-site meter / CTs"),
        box(400, 310, 300, "Main AC distribution"),
        box(40, 310, 250, "PV inverter(s): verify"),
        box(810, 310, 250, "Normal loads"),
        box(350, 442, 400, label),
        box(350, 564, 400, f"Battery: {scenario.nominal_kwh:g} kWh nominal"),
        '<text x="570" y="407">Dedicated bidirectional AC feeder</text>',
        '<text x="570" y="541">Protected DC path + BMS</text>',
        '<text x="40" y="658" font-size="15">Functional connections only; PE/N, protection ratings, terminals and transfer switching are omitted.</text>',
        '<text x="40" y="682" font-size="15">No backup operation, code-compliance approval, or cable/fuse selection is provided by this diagram.</text>',
        "</g></svg>\n",
    ]
    return "\n".join(parts)


def project_path(root: Path, project_id: str) -> Path:
    check_id(project_id)
    root = root.expanduser().resolve()
    path = root / ".research" / "energy" / "projects" / project_id
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            raise ValueError("symlinked engineering workspace paths are not supported")
    return path


def demo_scenario(phases: int) -> Scenario:
    return Scenario(
        phases,
        "single_phase" if phases == 1 else "three_phase_balanced",
        1,
        10.0,
        0.1,
        0.9,
        0.1,
        3.0,
        3.0,
        0.95,
        0.95,
        0.02,
        15,
    )


def demo_profile(scenario: Scenario) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(profile_headers(scenario.grid_phases))
    start = datetime(2025, 6, 21, tzinfo=UTC)
    for index in range(96):
        hour = index / 4
        solar = max(0, 4.5 * math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0
        values: list[Any] = [(start + timedelta(minutes=15 * index)).isoformat()]
        for phase in range(scenario.grid_phases):
            values.extend(
                [
                    0.4 + (1.0 if 17 <= hour < 22 and phase == 0 else 0),
                    round(solar, 6) if phase == 0 else 0,
                ]
            )
        writer.writerow(values)
    return output.getvalue()


def init_project(root: Path, project_id: str, demo_phases: int | None = None) -> Path:
    target = project_path(root, project_id)
    if target.exists():
        raise ValueError("project already exists; refusing to overwrite")
    scenario = demo_scenario(demo_phases) if demo_phases is not None else None
    project = {
        "schema_version": 1,
        "id": project_id,
        "data_class": "synthetic" if scenario else "customer",
        "evidence_refs": [],
        "assumptions": [
            "Phase-summed interval-average active-power model; constant efficiencies; no backup or protection calculation.",
            "All demo inputs are invented; not a measurement or a recommendation."
            if scenario
            else "No site values have been verified yet.",
        ],
        "unknowns": [
            "Connection identity and main fuse rating; trace PV circuits and upstairs/cabin feeder.",
            "Earthing, RCD coordination, conductor ratings, fault protection and islanding design.",
            "Battery/inverter compatibility, temperature derating, placement, insurer and site-specific requirements.",
        ],
        "scenario": asdict(scenario) if scenario else None,
    }
    validate_project(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".init-") as tmp:
        staged = Path(tmp) / project_id
        staged.mkdir()
        (staged / "project.json").write_text(canonical(project), encoding="utf-8")
        (staged / "SURVEY.md").write_text(
            f"# {project_id}: survey\n\n{NOTICE}\n\n"
            "Use docs/energy/SITE_SURVEY.md. Keep evidence local; record facts, assumptions and unknowns separately.\n"
            "Never use a branch-breaker label as evidence of the utility fuse rating.\n",
            encoding="utf-8",
        )
        if scenario:
            (staged / "profile.csv").write_text(demo_profile(scenario), encoding="utf-8")
        staged.rename(target)
    return target


def report_markdown(project: dict[str, Any], result: dict[str, Any]) -> str:
    lines = [
        f"# {project['id']} - {project['data_class']} concept",
        "",
        f"**{NOTICE}**",
        "",
        "Generated from the same validated scenario as topology.svg and results.json.",
        "",
        f"Model: `{MODEL_VERSION}`. Period: {result['duration_hours']:g} hours. No annualisation.",
        "",
        "| Quantity | Value |",
        "|---|---:|",
    ]
    for name, value in result["totals"].items():
        lines.append(f"| {name} | {value:.6f} |")
    lines += [
        f"| initial_stored_kwh | {result['initial_stored_kwh']:.6f} |",
        f"| final_stored_kwh | {result['final_stored_kwh']:.6f} |",
        f"| stored_energy_delta_kwh | {result['stored_energy_delta_kwh']:.6f} |",
        "",
        "Initial/final stored energy must be accounted for before comparing economics.",
        "",
        f"Peak **interval-average** import by phase (kW): `{result['peak_interval_import_kw_by_phase']}`.",
        f"Peak **interval-average** export by phase (kW): `{result['peak_interval_export_kw_by_phase']}`.",
        "",
        "These are not RMS currents, motor starting peaks or proof that a main fuse can be reduced.",
        "The meter is assumed to sum phases; verify actual metering. No tariff or payback claim is calculated.",
        "",
        "## Assumptions and unresolved work",
        "",
    ]
    # JSON-encode user text in a code block; escape fences so notes cannot alter the report structure.
    notes = canonical({k: project[k] for k in ("assumptions", "unknowns", "evidence_refs")})
    lines += [
        "```json",
        notes.replace("`", "\\u0060").rstrip(),
        "```",
        "",
        "Evidence references are pointers only: this prototype does not validate their existence, authority or review status.",
        "No approvals are inferred from successful execution. Independent design review and commissioning remain outstanding.",
        "",
    ]
    return "\n".join(lines)


def build_project(root: Path, project_id: str) -> Path:
    target = project_path(root, project_id)
    project_file, profile_file = target / "project.json", target / "profile.csv"
    for path in (project_file, profile_file):
        if path.is_symlink():
            raise ValueError("input symlinks are not supported")
    project_bytes = project_file.read_bytes()
    project = read_json(project_bytes.decode("utf-8"))
    scenario = validate_project(project)
    if project["id"] != project_id:
        raise ValueError("project id differs from directory")
    if scenario is None:
        raise ValueError(
            "scenario is unknown; complete the survey and explicit concept inputs first"
        )
    profile_bytes = profile_file.read_bytes()
    result = simulate(scenario, read_profile(profile_bytes.decode("utf-8-sig"), scenario))

    def sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    inputs = {
        "project_sha256": sha(project_bytes),
        "profile_sha256": sha(profile_bytes),
        "engine_sha256": sha(Path(__file__).read_bytes()),
        "model_version": MODEL_VERSION,
        "python_version": sys.version.split()[0],
    }
    run_id = sha(canonical(inputs).encode())
    outputs = {
        "results.json": canonical(result),
        "report.md": report_markdown(project, result),
        "topology.mmd": topology_mermaid(scenario),
        "topology.svg": topology_svg(scenario, project_id),
    }
    manifest = {
        "inputs": inputs,
        "run_id": run_id,
        "release_status": "concept_only",
        "artifacts": {name: sha(text.encode()) for name, text in sorted(outputs.items())},
    }
    destination = target / "runs" / run_id
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError("output symlinks are not supported")
    if destination.exists():
        expected = {**outputs, "manifest.json": canonical(manifest)}
        if any(
            (destination / name).is_symlink()
            or (destination / name).read_text(encoding="utf-8") != text
            for name, text in expected.items()
        ):
            raise ValueError("existing run was modified; refusing to overwrite")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".build-") as tmp:
        staged = Path(tmp) / run_id
        staged.mkdir()
        for name, text in outputs.items():
            (staged / name).write_text(text, encoding="utf-8")
        (staged / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
        staged.rename(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="local workspace, never a server URL"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create an unknown-valued customer project")
    init.add_argument("project_id")
    demo = sub.add_parser("demo", help="create explicitly synthetic data")
    demo.add_argument("project_id")
    demo.add_argument("--phases", type=int, choices=(1, 3), required=True)
    build = sub.add_parser("build", help="validate, replay and emit a concept bundle")
    build.add_argument("project_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            output = init_project(args.root, args.project_id)
        elif args.command == "demo":
            output = init_project(args.root, args.project_id, args.phases)
        else:
            output = build_project(args.root, args.project_id)
    except (ValueError, OSError, ArithmeticError) as exc:
        print(f"energy: {exc}", file=sys.stderr)
        return 2
    print(f"{NOTICE}\n{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
