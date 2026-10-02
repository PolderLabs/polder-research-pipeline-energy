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
import textwrap
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .schemas import SchemaError, package_registry

MODEL_VERSION = "energy-ac-self-consumption-v0.1"
NOTICE = "CONCEPT ONLY - NOT FOR INSTALLATION"


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
    # The workspace root stores private inputs, not executable schema policy.
    # Use the installed/checkout canonical registry even with a separate --root.
    try:
        package_registry().validate("energy-project", project)
    except SchemaError as exc:
        raise ValueError(str(exc)) from exc
    # JSON Schema accepts 1.0 as an integer; the v1 Python contract does not.
    if type(project["schema_version"]) is not int:
        raise ValueError("unsupported schema_version")
    check_id(project["id"])
    fact_ids = [fact["fact_id"] for fact in project.get("site_facts", [])]
    if len(fact_ids) != len(set(fact_ids)):
        raise ValueError("site_facts fact_id values must be unique")
    for fact in project.get("site_facts", []):
        if type(fact["value"]) is float and not math.isfinite(fact["value"]):
            raise ValueError(f"site fact {fact['fact_id']} value must be finite")
    if project["scenario"] is None:
        return None
    return Scenario.from_dict(project["scenario"])


def resolve_site_facts(root: Path, project: dict[str, Any]) -> dict[str, Any] | None:
    """Validate local evidence links and return a content-pinned, non-sensitive snapshot."""
    facts = project.get("site_facts", [])
    if not facts or not any(fact["evidence"] for fact in facts):
        return None

    workspace = root.expanduser().resolve()
    research_dir = workspace / ".research"
    if research_dir.is_symlink():
        raise ValueError("symlinked evidence workspace paths are not supported")
    registry = package_registry()
    source_snapshots: dict[str, dict[str, Any]] = {}
    segment_snapshots: dict[str, dict[str, Any]] = {}

    def record(kind: str, record_id: str) -> tuple[dict[str, Any], str]:
        directory = research_dir / ("sources" if kind == "source" else "segments")
        path = directory / f"{record_id}.json"
        if directory.is_symlink() or path.is_symlink():
            raise ValueError(f"symlinked {kind} evidence paths are not supported")
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise ValueError(f"missing {kind} evidence record {record_id}") from None
        except OSError:
            raise ValueError(f"cannot read {kind} evidence record {record_id}") from None
        try:
            value = read_json(raw.decode("utf-8"))
        except UnicodeError:
            raise ValueError(f"invalid UTF-8 in {kind} evidence record {record_id}") from None
        except ValueError:
            raise ValueError(f"invalid JSON in {kind} evidence record {record_id}") from None
        try:
            registry.validate(kind, value)
        except SchemaError:
            errors = registry.iter_record_errors(kind, value)
            error_path = errors[0]["path"] if errors else ""
            # Nested schema maps may have private, user-controlled keys. Report
            # only the canonical top-level field, never an arbitrary path segment.
            location = error_path.partition(".")[0] or "<root>"
            raise ValueError(
                f"invalid {kind} evidence record {record_id} (schema validation at {location})"
            ) from None
        try:
            registry.validate_filename_identity(kind, path.name, value)
        except SchemaError:
            raise ValueError(
                f"invalid {kind} evidence record {record_id} (filename identity mismatch)"
            ) from None
        return value, hashlib.sha256(raw).hexdigest()

    for fact in facts:
        for link in fact["evidence"]:
            source_id = link["source_id"]
            if not re.fullmatch(
                r"src_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                source_id,
            ):
                raise ValueError("invalid source evidence ID")
            if source_id not in source_snapshots:
                source, source_hash = record("source", source_id)
                acquisition_status = source.get("acquisition_status")
                if acquisition_status is None:
                    acquisition_status = (
                        "unacquired" if source["source_status"] == "unacquired" else "acquired"
                    )
                if acquisition_status != "acquired":
                    raise ValueError(f"source evidence {source_id} is not acquired")
                source_snapshots[source_id] = {
                    "source_id": source_id,
                    "source_status": source["source_status"],
                    "acquisition_status": acquisition_status,
                    "sha256": source_hash,
                }
            segment_id = link.get("segment_id")
            if segment_id:
                if not re.fullmatch(
                    r"seg_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                    segment_id,
                ):
                    raise ValueError("invalid segment evidence ID")
                if segment_id not in segment_snapshots:
                    segment, segment_hash = record("segment", segment_id)
                    segment_snapshots[segment_id] = {
                        "segment_id": segment_id,
                        "source_id": segment["source_id"],
                        "sha256": segment_hash,
                    }
                if segment_snapshots[segment_id]["source_id"] != source_id:
                    raise ValueError(
                        f"segment evidence {segment_id} does not belong to source {source_id}"
                    )

    if not source_snapshots:
        return None
    return {
        "sources": [source_snapshots[key] for key in sorted(source_snapshots)],
        "segments": [segment_snapshots[key] for key in sorted(segment_snapshots)],
    }


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


def _profile_sample(record: dict[str, Any], scenario: Scenario) -> Sample:
    if None in record or any(v is None for v in record.values()):
        raise ValueError("unexpected or missing columns")
    timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp needs a UTC offset")
    load = tuple(float(record[f"load_l{i}_kw"]) for i in range(1, scenario.grid_phases + 1))
    pv = tuple(float(record[f"pv_l{i}_kw"]) for i in range(1, scenario.grid_phases + 1))
    return Sample(timestamp.astimezone(UTC), load, pv)


def read_profile(text: str, scenario: Scenario) -> list[Sample]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != profile_headers(scenario.grid_phases):
        raise ValueError(
            "CSV headers/order must be " + ",".join(profile_headers(scenario.grid_phases))
        )
    rows = []
    for line, record in enumerate(reader, start=2):
        try:
            rows.append(_profile_sample(record, scenario))
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


def profile_preflight(text: str, scenario: Scenario) -> dict[str, Any]:
    """Report the exact CSV contract without repairing data or simulating storage."""
    headers = profile_headers(scenario.grid_phases)
    report: dict[str, Any] = {
        "report_version": 1,
        "notice": NOTICE,
        "valid": False,
        "grid_phases": scenario.grid_phases,
        "interval_minutes": scenario.interval_minutes,
        "power_unit": "kW",
        "power_semantics": "interval_average_active_power",
        "timestamp_semantics": "interval_start_with_explicit_UTC_offset",
        "expected_headers": headers,
        "row_count": 0,
        "errors": [],
        "coverage": None,
        "channel_energy_kwh": None,
        "source_boundary": {
            "channels": "separate load and PV per supply phase",
            "original_units_verified": False,
            "meter_boundary_verified": False,
            "phase_assignment_verified": False,
            "evidence": "CSV syntax cannot establish measurement provenance",
        },
    }
    reader = csv.DictReader(io.StringIO(text))
    errors = report["errors"]
    try:
        if reader.fieldnames != headers:
            errors.append({"row": 1, "message": "CSV headers/order must be " + ",".join(headers)})
            return report
        previous = None
        for line, record in enumerate(reader, start=2):
            report["row_count"] += 1
            try:
                sample = _profile_sample(record, scenario)
                validate_samples([sample], scenario)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                errors.append({"row": line, "message": str(exc)})
                previous = None
                continue
            if previous is not None and sample.timestamp - previous != timedelta(
                minutes=scenario.interval_minutes
            ):
                errors.append(
                    {
                        "row": line,
                        "message": "profile has duplicates, gaps, overlaps or unsorted timestamps",
                    }
                )
            previous = sample.timestamp
    except csv.Error as exc:
        errors.append({"row": None, "message": f"CSV parsing failed: {exc}"})
        return report
    if not report["row_count"]:
        errors.append({"row": None, "message": "profile is empty"})
    if errors:
        return report
    # The build parser remains the final authority; never total rejected data.
    samples = read_profile(text, scenario)
    try:
        end = samples[-1].timestamp + timedelta(minutes=scenario.interval_minutes)
        energy = {
            name: math.fsum(
                (sample.load_kw if name.startswith("load") else sample.pv_kw)[phase]
                * (scenario.interval_minutes / 60)
                for sample in samples
            )
            for phase in range(scenario.grid_phases)
            for name in (f"load_l{phase + 1}_kw", f"pv_l{phase + 1}_kw")
        }
        if not all(math.isfinite(value) for value in energy.values()):
            raise ValueError("channel energy exceeds finite numeric range")
    except (ValueError, OverflowError) as exc:
        errors.append({"row": None, "message": str(exc)})
        return report
    report.update(
        valid=True,
        coverage={
            "start_utc": samples[0].timestamp.isoformat(),
            "end_exclusive_utc": end.isoformat(),
            "interval_count": len(samples),
            "duration_hours": len(samples) * scenario.interval_minutes / 60,
        },
        channel_energy_kwh=energy,
    )
    return report


def preflight_project(root: Path, project_id: str) -> dict[str, Any]:
    target = project_path(root, project_id)
    project_file, profile_file = target / "project.json", target / "profile.csv"
    if project_file.is_symlink() or profile_file.is_symlink():
        raise ValueError("input symlinks are not supported")
    project_bytes = project_file.read_bytes()
    project = read_json(project_bytes.decode("utf-8"))
    scenario = validate_project(project)
    evidence_snapshot = resolve_site_facts(root, project)
    if project["id"] != project_id:
        raise ValueError("project id differs from directory")
    if scenario is None:
        raise ValueError("scenario is unknown; explicit phases and interval require a scenario")
    profile_bytes = profile_file.read_bytes()
    report = profile_preflight(profile_bytes.decode("utf-8-sig"), scenario)
    report["inputs"] = {
        "project_sha256": hashlib.sha256(project_bytes).hexdigest(),
        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "data_class": project["data_class"],
    }
    if evidence_snapshot is not None:
        report["inputs"]["evidence_snapshot"] = evidence_snapshot
    return report


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
    baseline_phase_import = [0.0] * scenario.grid_phases
    baseline_phase_export = [0.0] * scenario.grid_phases
    baseline_peak_import = [0.0] * scenario.grid_phases
    baseline_peak_export = [0.0] * scenario.grid_phases
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
        for i, value in enumerate(base):
            baseline_phase_import[i] += max(0, value) * dt
            baseline_phase_export[i] += max(0, -value) * dt
            baseline_peak_import[i] = max(baseline_peak_import[i], value)
            baseline_peak_export[i] = max(baseline_peak_export[i], -value)
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
        "comparison": {
            "basis": "same validated profile and interval window; phase-summed aggregate meter",
            "baseline_import_kwh": totals["baseline_import_kwh"],
            "concept_import_kwh": totals["grid_import_kwh"],
            "baseline_minus_concept_import_kwh": (
                totals["baseline_import_kwh"] - totals["grid_import_kwh"]
            ),
            "baseline_export_kwh": totals["baseline_export_kwh"],
            "concept_export_kwh": totals["grid_export_kwh"],
            "baseline_minus_concept_export_kwh": (
                totals["baseline_export_kwh"] - totals["grid_export_kwh"]
            ),
            "baseline_phase_import_kwh": baseline_phase_import,
            "baseline_phase_export_kwh": baseline_phase_export,
            "concept_phase_peak_interval_import_kw": peak_import,
            "concept_phase_peak_interval_export_kw": peak_export,
            "baseline_phase_peak_interval_import_kw": baseline_peak_import,
            "baseline_phase_peak_interval_export_kw": baseline_peak_export,
            "initial_stored_kwh": initial_energy,
            "final_stored_kwh": energy,
            "stored_energy_delta_kwh": delta,
            "conversion_loss_kwh": totals["conversion_loss_kwh"],
            "auxiliary_kwh": totals["auxiliary_kwh"],
            "notices": [
                "Signed differences are arithmetic, not savings, guarantees, or a tariff result.",
                "Initial and terminal stored energy are not normalized against a battery-free baseline.",
                "Per-phase interval-average kW is not RMS current or protection evidence.",
            ],
        },
        "initial_stored_kwh": initial_energy,
        "final_stored_kwh": energy,
        "stored_energy_delta_kwh": delta,
        "energy_balance_error_kwh": balance,
        "peak_interval_import_kw_by_phase": peak_import,
        "peak_interval_export_kw_by_phase": peak_export,
        "trace": trace,
    }


def concept_model(project_id: str, scenario: Scenario, run_id: str) -> dict[str, Any]:
    """Shared semantic source for editable customer and electrical concept views."""
    phases = f"{scenario.grid_phases}-phase supply"
    battery = (
        f"Single-phase battery inverter on L{scenario.battery_phase}"
        if scenario.topology == "single_phase"
        else "Balanced three-phase battery inverter"
    )
    return {
        "title": f"{project_id} | Energy concept",
        "run_id": run_id,
        "notice": NOTICE,
        "facts": [
            f"Supply model: {phases}",
            f"Storage model: {battery}",
            f"Battery model: {scenario.nominal_kwh:g} kWh nominal",
        ],
        "nodes": [
            {
                "id": "GRID-01",
                "label": "Utility grid",
                "detail": phases,
                "x": 70,
                "y": 250,
                "w": 210,
                "h": 105,
                "kind": "grid",
            },
            {
                "id": "MTR-01",
                "label": "Whole-site meter",
                "detail": "Boundary / phase summing to verify",
                "x": 350,
                "y": 250,
                "w": 210,
                "h": 105,
                "kind": "meter",
            },
            {
                "id": "MDB-01",
                "label": "Main AC board",
                "detail": "Existing distribution; survey required",
                "x": 650,
                "y": 250,
                "w": 240,
                "h": 115,
                "kind": "board",
            },
            {
                "id": "LOAD-01",
                "label": "Site loads",
                "detail": "Circuits and feeder route unknown",
                "x": 1100,
                "y": 180,
                "w": 220,
                "h": 100,
                "kind": "load",
            },
            {
                "id": "PV-01",
                "label": "Existing PV inverter(s)",
                "detail": "Count, make, and phases to verify",
                "x": 1100,
                "y": 375,
                "w": 220,
                "h": 100,
                "kind": "pv",
            },
            {
                "id": "INV-01",
                "label": battery,
                "detail": "Functional block only; protection TBD",
                "x": 650,
                "y": 510,
                "w": 240,
                "h": 115,
                "kind": "inverter",
            },
            {
                "id": "BAT-01",
                "label": "Battery bank",
                "detail": f"{scenario.nominal_kwh:g} kWh nominal model",
                "x": 350,
                "y": 510,
                "w": 210,
                "h": 105,
                "kind": "battery",
            },
            {
                "id": "CTRL-01",
                "label": "Local controller",
                "detail": "Data / bounded setpoints only",
                "x": 70,
                "y": 510,
                "w": 210,
                "h": 105,
                "kind": "control",
            },
        ],
        "edges": [
            {
                "id": "E-GRID-MTR",
                "source": "GRID-01",
                "target": "MTR-01",
                "label": "AC connection",
                "kind": "power_bidir",
            },
            {
                "id": "E-MTR-MDB",
                "source": "MTR-01",
                "target": "MDB-01",
                "label": "meter boundary",
                "kind": "power_bidir",
            },
            {
                "id": "E-PV-MDB",
                "source": "PV-01",
                "target": "MDB-01",
                "label": "existing generation",
                "kind": "power",
            },
            {
                "id": "E-MDB-LOAD",
                "source": "MDB-01",
                "target": "LOAD-01",
                "label": "normal circuits",
                "kind": "power",
            },
            {
                "id": "E-MDB-INV",
                "source": "MDB-01",
                "target": "INV-01",
                "label": "bidirectional AC concept",
                "kind": "power_bidir",
            },
            {
                "id": "E-INV-BAT",
                "source": "INV-01",
                "target": "BAT-01",
                "label": "protected DC path TBD",
                "kind": "power_bidir",
            },
            {
                "id": "E-MTR-CTRL",
                "source": "MTR-01",
                "target": "CTRL-01",
                "label": "measurement",
                "kind": "data",
            },
            {
                "id": "E-CTRL-INV",
                "source": "CTRL-01",
                "target": "INV-01",
                "label": "bounded setpoints",
                "kind": "data",
            },
        ],
    }


def concept_sheet_drawio(model: dict[str, Any]) -> str:
    """Emit a native editable draw.io file with stable semantic cell IDs."""
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "type": "device"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "concept-sheet", "name": "Concept sheet"})
    graph = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "1600",
            "dy": "900",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": "1600",
            "pageHeight": "900",
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    def text_cell(cell_id: str, value: str, x: int, y: int, w: int, h: int, style: str) -> None:
        cell = ET.SubElement(
            root,
            "mxCell",
            {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": "1"},
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"},
        )

    text_cell(
        "TITLE",
        model["title"],
        70,
        35,
        1000,
        45,
        "text;html=1;align=left;verticalAlign=middle;fontSize=28;fontStyle=1;fontColor=#0f172a;",
    )
    text_cell(
        "NOTICE",
        model["notice"],
        70,
        82,
        720,
        34,
        "rounded=1;whiteSpace=wrap;html=1;fillColor=#fee2e2;strokeColor=#dc2626;fontColor=#991b1b;fontStyle=1;fontSize=16;",
    )
    text_cell(
        "RUN",
        f"Concept revision {model['run_id'][:12]}",
        1180,
        43,
        350,
        30,
        "text;html=1;align=right;verticalAlign=middle;fontSize=13;fontColor=#475569;",
    )
    text_cell(
        "FACTS",
        "  ·  ".join(model["facts"]),
        70,
        132,
        1460,
        32,
        "text;html=1;align=left;verticalAlign=middle;fontSize=14;fontColor=#334155;",
    )
    style_by_kind = {
        "grid": "fillColor=#e0f2fe;strokeColor=#0284c7",
        "meter": "fillColor=#fef3c7;strokeColor=#d97706",
        "board": "fillColor=#dbeafe;strokeColor=#2563eb",
        "load": "fillColor=#f1f5f9;strokeColor=#64748b",
        "pv": "fillColor=#fef9c3;strokeColor=#ca8a04",
        "inverter": "fillColor=#ede9fe;strokeColor=#7c3aed",
        "battery": "fillColor=#dcfce7;strokeColor=#16a34a",
        "control": "fillColor=#fce7f3;strokeColor=#db2777",
    }
    by_id = {node["id"]: node for node in model["nodes"]}
    for node in model["nodes"]:
        obj = ET.SubElement(
            root,
            "object",
            {
                "id": node["id"],
                "label": f"{node['label']}<br>{node['detail']}",
                "componentId": node["id"],
                "role": node["kind"],
            },
        )
        cell = ET.SubElement(
            obj,
            "mxCell",
            {
                "style": f"rounded=1;whiteSpace=wrap;html=1;arcSize=12;{style_by_kind[node['kind']]};fontColor=#0f172a;fontSize=16;align=center;verticalAlign=middle;spacing=12;",
                "vertex": "1",
                "parent": "1",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": str(node["x"]),
                "y": str(node["y"]),
                "width": str(node["w"]),
                "height": str(node["h"]),
                "as": "geometry",
            },
        )
    for edge in model["edges"]:
        source, target = by_id[edge["source"]], by_id[edge["target"]]
        style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeWidth=2;strokeColor=#475569;endArrow=block;endFill=1;"
        if edge["kind"] == "power_bidir":
            style += "startArrow=block;startFill=1;"
        elif edge["kind"] == "data":
            style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;dashed=1;dashPattern=5 4;strokeWidth=2;strokeColor=#db2777;endArrow=open;endFill=0;"
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": edge["id"],
                "value": edge["label"],
                "style": style,
                "edge": "1",
                "parent": "1",
                "source": source["id"],
                "target": target["id"],
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    note = "Verify meter/phase behaviour, PV equipment, cable routes, clearances and protection with site evidence and qualified review. This picture does not specify terminals, cable sizes, switching, backup, or protective devices."
    text_cell(
        "OPEN-ITEMS",
        note,
        70,
        690,
        1460,
        105,
        "rounded=1;whiteSpace=wrap;html=1;fillColor=#f8fafc;strokeColor=#cbd5e1;fontColor=#334155;fontSize=14;align=left;verticalAlign=middle;spacing=14;",
    )
    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True) + "\n"


def concept_sheet_svg(model: dict[str, Any]) -> str:
    """Customer-facing SVG preview from the same node/edge model as draw.io."""
    colors = {
        "grid": ("#e0f2fe", "#0284c7"),
        "meter": ("#fef3c7", "#d97706"),
        "board": ("#dbeafe", "#2563eb"),
        "load": ("#f1f5f9", "#64748b"),
        "pv": ("#fef9c3", "#ca8a04"),
        "inverter": ("#ede9fe", "#7c3aed"),
        "battery": ("#dcfce7", "#16a34a"),
        "control": ("#fce7f3", "#db2777"),
    }

    def multiline_text(
        text: str,
        *,
        element_id: str,
        x: float,
        y: float,
        max_width: float,
        font_size: int,
        line_height: int,
        color: str,
        weight: str = "",
    ) -> tuple[str, int]:
        # Conservative average glyph width for the sans-serif fonts used here;
        # split long labels before they can cross a component card boundary.
        width = max(8, int(max_width / (font_size * 0.62)))
        lines = textwrap.wrap(text, width=width, break_long_words=True) or [""]
        attrs = f' id="{element_id}" x="{x}" y="{y}" text-anchor="middle" font-family="sans-serif" font-size="{font_size}"{weight} fill="{color}"'
        tspans = "".join(
            f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{escape(line)}</tspan>'
            for index, line in enumerate(lines)
        )
        return f"<text{attrs}>{tspans}</text>", len(lines)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#475569"/></marker><marker id="arrow-start" markerWidth="10" markerHeight="10" refX="1" refY="3" orient="auto"><path d="M9,0 L9,6 L0,3 z" fill="#475569"/></marker><marker id="data-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#db2777"/></marker></defs>',
        '<rect width="1600" height="900" fill="#f8fafc"/>',
        '<text x="70" y="67" font-family="sans-serif" font-size="30" font-weight="700" fill="#0f172a">'
        + escape(model["title"])
        + "</text>",
        '<rect x="70" y="84" width="660" height="38" rx="8" fill="#fee2e2" stroke="#dc2626"/>',
        '<text x="88" y="109" font-family="sans-serif" font-size="17" font-weight="700" fill="#991b1b">'
        + NOTICE
        + "</text>",
        f'<text x="1530" y="68" text-anchor="end" font-family="sans-serif" font-size="14" fill="#475569">Concept revision {model["run_id"][:12]}</text>',
        f'<text x="70" y="153" font-family="sans-serif" font-size="14" fill="#334155">{escape("  ·  ".join(model["facts"]))}</text>',
    ]
    # Routed connectors; these are diagrammatic, never to scale or installation routes.
    paths = {
        "E-GRID-MTR": "M 280 302 H 350",
        "E-MTR-MDB": "M 560 302 H 650",
        "E-PV-MDB": "M 1100 425 H 1000 V 307 H 890",
        "E-MDB-LOAD": "M 890 285 H 990 V 230 H 1100",
        "E-MDB-INV": "M 770 365 V 510",
        "E-INV-BAT": "M 650 567 H 560",
        "E-MTR-CTRL": "M 455 355 V 445 H 175 V 510",
        "E-CTRL-INV": "M 280 563 H 310 V 660 H 770 V 625",
    }
    for edge in model["edges"]:
        dash = ' stroke-dasharray="8 6"' if edge["kind"] == "data" else ""
        color = "#db2777" if edge["kind"] == "data" else "#475569"
        arrows = (
            ' marker-end="url(#data-arrow)"'
            if edge["kind"] == "data"
            else ' marker-end="url(#arrow)"'
        )
        if edge["kind"] == "power_bidir":
            arrows += ' marker-start="url(#arrow-start)"'
        parts.append(
            f'<path id="{edge["id"]}" d="{paths[edge["id"]]}" fill="none" stroke="{color}" stroke-width="3"{dash}{arrows}/>'
        )
        if edge["id"] in ("E-MDB-INV", "E-INV-BAT", "E-MTR-CTRL"):
            label_x, label_y = {
                "E-MDB-INV": (788, 440),
                "E-INV-BAT": (605, 553),
                "E-MTR-CTRL": (320, 438),
            }[edge["id"]]
            parts.append(
                f'<text x="{label_x}" y="{label_y}" font-family="sans-serif" font-size="13" fill="{color}">{escape(edge["label"])}</text>'
            )
    for node in model["nodes"]:
        fill, stroke = colors[node["kind"]]
        x, y, w, h = (node[key] for key in ("x", "y", "w", "h"))
        text_x = x + w / 2
        label, label_lines = multiline_text(
            node["label"],
            element_id=f"{node['id']}-LABEL",
            x=text_x,
            y=y + 35,
            max_width=w - 24,
            font_size=14,
            line_height=15,
            color="#0f172a",
            weight=' font-weight="700"',
        )
        detail, _ = multiline_text(
            node["detail"],
            element_id=f"{node['id']}-DETAIL",
            x=text_x,
            y=y + 35 + label_lines * 15 + 2,
            max_width=w - 24,
            font_size=12,
            line_height=12,
            color="#475569",
        )
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>',
                f'<rect x="{x + 16}" y="{y + 14}" width="34" height="4" rx="2" fill="{stroke}"/>',
                label,
                detail,
                f'<text x="{x + w / 2}" y="{y + h - 10}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#64748b">{node["id"]}</text>',
            ]
        )
    parts.extend(
        [
            '<rect x="70" y="710" width="1460" height="100" rx="14" fill="#ffffff" stroke="#cbd5e1"/>',
            '<text x="95" y="742" font-family="sans-serif" font-size="16" font-weight="700" fill="#0f172a">Open checks before a site-specific design</text>',
            '<text x="95" y="770" font-family="sans-serif" font-size="14" fill="#334155">Meter/phase behaviour · PV equipment · feeder routes · equipment clearances · protection and isolation</text>',
            '<text x="95" y="793" font-family="sans-serif" font-size="13" fill="#64748b">Functional connections only: not to scale; no terminal, cable, backup, or protection specification.</text>',
            f'<text x="1530" y="850" text-anchor="end" font-family="sans-serif" font-size="12" fill="#64748b">Source run {model["run_id"][:12]} · Editable companion: concept-sheet.drawio</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


QET_SYMBOLS = {
    "grid": {"name": "Grid supply", "ports": [(80, 0, "e")]},
    "meter": {"name": "Whole-site meter", "ports": [(-80, 0, "w"), (80, 0, "e")]},
    "board": {
        "name": "Main AC board",
        "ports": [(-80, 0, "w"), (80, 0, "e"), (0, -40, "n"), (0, 40, "s")],
    },
    "load": {"name": "Site loads", "ports": [(-80, 0, "w")]},
    "pv": {"name": "PV inverter", "ports": [(0, 40, "s")]},
    "inverter": {"name": "Battery inverter", "ports": [(0, -40, "n"), (0, 40, "s")]},
    "battery": {"name": "Battery bank", "ports": [(0, -40, "n")]},
}


def qet_schematic(model: dict[str, Any], scenario: Scenario) -> str:
    """Emit a QElectroTech-editable functional-block schematic, not a wiring plan."""
    project = ET.Element("project", {"version": "0.21", "title": model["title"]})
    diagram = ET.SubElement(
        project,
        "diagram",
        {
            "title": "Functional concept - not installation wiring",
            "author": "Polder Energy Workbench",
            "filename": "electrical-schematic.qet",
            "folio": "1/1",
            "cols": "32",
            "colsize": "50",
            "rows": "24",
            "rowsize": "40",
            "height": "960",
            "displayrows": "false",
            "displaycols": "false",
        },
    )
    ET.SubElement(diagram, "defaultconductor", {"type": "simple"})
    elements = ET.SubElement(diagram, "elements")
    # QET's grid is intentionally sparse and function-oriented; x/y are hotspots.
    qet_positions = {
        "GRID-01": (150, 340),
        "MTR-01": (400, 340),
        "MDB-01": (700, 340),
        "LOAD-01": (1040, 340),
        "PV-01": (700, 140),
        "INV-01": (700, 540),
        "BAT-01": (700, 740),
    }
    model_nodes = {node["id"]: node for node in model["nodes"]}
    terminals: dict[tuple[str, str], int] = {}
    next_terminal = 1
    for component_id, (x, y) in qet_positions.items():
        node = model_nodes[component_id]
        kind, label = node["kind"], node["label"]
        symbol = QET_SYMBOLS[kind]
        element = ET.SubElement(
            elements,
            "element",
            {
                "x": str(x),
                "y": str(y),
                "type": f"embed://polder-concept/{kind}.elmt",
                "orientation": "0",
            },
        )
        ports = ET.SubElement(element, "terminals")
        for px, py, direction in symbol["ports"]:
            terminals[(component_id, direction)] = next_terminal
            orientation = {"n": "0", "e": "1", "s": "2", "w": "3"}[direction]
            ET.SubElement(
                ports,
                "terminal",
                {"x": str(px), "y": str(py), "id": str(next_terminal), "orientation": orientation},
            )
            next_terminal += 1
        inputs = ET.SubElement(element, "inputs")
        ET.SubElement(inputs, "input", {"x": "-70", "y": "0", "text": label})
        ET.SubElement(inputs, "input", {"x": "-70", "y": "22", "text": component_id})

    conductors = ET.SubElement(diagram, "conductors")
    opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
    for edge in model["edges"]:
        source, target = edge["source"], edge["target"]
        if (
            edge["kind"] not in ("power", "power_bidir")
            or source not in qet_positions
            or target not in qet_positions
        ):
            continue
        dx = qet_positions[target][0] - qet_positions[source][0]
        dy = qet_positions[target][1] - qet_positions[source][1]
        source_side = ("e" if dx >= 0 else "w") if abs(dx) >= abs(dy) else ("s" if dy >= 0 else "n")
        target_side = opposite[source_side]
        ET.SubElement(
            conductors,
            "conductor",
            {
                "terminal1": str(terminals[(source, source_side)]),
                "terminal2": str(terminals[(target, target_side)]),
                "type": "simple",
            },
        )
    annotations = ET.SubElement(diagram, "inputs")
    ET.SubElement(
        annotations, "input", {"x": "40", "y": "30", "text": f"Source run {model['run_id']}"}
    )
    ET.SubElement(annotations, "input", {"x": "40", "y": "60", "text": " | ".join(model["facts"])})
    ET.SubElement(annotations, "input", {"x": "40", "y": "880", "text": NOTICE})
    ET.SubElement(
        annotations,
        "input",
        {
            "x": "40",
            "y": "920",
            "text": "Functional blocks only. No standard symbols, protection ratings, terminals, cable sizes, backup modes, or PE/N design.",
        },
    )
    collection = ET.SubElement(project, "collection")
    category = ET.SubElement(collection, "category", {"name": "polder-concept"})
    names = ET.SubElement(category, "names")
    ET.SubElement(names, "name", {"lang": "en"}).text = "Polder Concept Blocks"
    for kind, symbol in QET_SYMBOLS.items():
        embedded = ET.SubElement(category, "element", {"name": f"{kind}.elmt"})
        definition = ET.SubElement(
            embedded,
            "definition",
            {
                "type": "element",
                "width": "160",
                "height": "80",
                "hotspot_x": "80",
                "hotspot_y": "40",
                "orientation": "dyyy",
                "version": "0.2",
            },
        )
        names = ET.SubElement(definition, "names")
        ET.SubElement(names, "name", {"lang": "en"}).text = symbol["name"]
        description = ET.SubElement(definition, "description")
        ET.SubElement(
            description,
            "rect",
            {
                "x": "-80",
                "y": "-40",
                "width": "160",
                "height": "80",
                "style": "filling:white;color:black;line-weight:normal;",
            },
        )
        ET.SubElement(
            description, "text", {"x": "-72", "y": "-22", "size": "8", "text": symbol["name"]}
        )
        # QET instance text fills existing definition slots by exact coordinates.
        ET.SubElement(description, "input", {"x": "-70", "y": "0", "size": "8", "text": "Label"})
        ET.SubElement(
            description, "input", {"x": "-70", "y": "22", "size": "8", "text": "Component ID"}
        )
        for px, py, direction in symbol["ports"]:
            ET.SubElement(
                description, "terminal", {"x": str(px), "y": str(py), "orientation": direction}
            )
    ET.indent(project, space="  ")
    return ET.tostring(project, encoding="unicode", xml_declaration=True) + "\n"


def topology_mermaid(scenario: Scenario) -> str:
    title = (
        f"Single-phase storage on L{scenario.battery_phase}"
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
        f"1-phase battery inverter on L{scenario.battery_phase}"
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


def report_markdown(
    project: dict[str, Any], result: dict[str, Any], evidence_snapshot: dict[str, Any] | None = None
) -> str:
    lines = [
        f"# {project['id']} - {project['data_class']} concept",
        "",
        f"**{NOTICE}**",
        "",
        "Generated from the same validated scenario as the drawing files and results.json.",
        "",
        "## Drawing files",
        "",
        "- `concept-sheet.drawio` is the editable customer-facing functional concept; `concept-sheet.svg` is its preview.",
        "- `electrical-schematic.qet` is an editable QElectroTech functional-block schematic, not a wiring or protection design.",
        "- All drawing files are generated from this run's scenario and revision. Manual edits are not fed back into calculations.",
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
    ]
    comparison = result["comparison"]
    lines += [
        "",
        "## Same-period no-storage baseline comparison",
        "",
        "Both columns use this run's validated profile and the same interval window. The baseline is phase-summed net load/PV without storage or battery auxiliaries.",
        "",
        "| Aggregate meter quantity | No-storage baseline (kWh) | Storage concept (kWh) | Baseline minus concept (kWh) |",
        "|---|---:|---:|---:|",
        f"| Import | {comparison['baseline_import_kwh']:.6f} | {comparison['concept_import_kwh']:.6f} | {comparison['baseline_minus_concept_import_kwh']:.6f} |",
        f"| Export | {comparison['baseline_export_kwh']:.6f} | {comparison['concept_export_kwh']:.6f} | {comparison['baseline_minus_concept_export_kwh']:.6f} |",
        "",
        "Signed differences are arithmetic only, not savings, guaranteed performance, or a tariff result. The baseline and concept do not have equivalent stored-energy boundaries; account for the initial, final and delta stored energy shown below before interpreting the comparison.",
        "",
        "Per-phase baseline and concept interval-average peaks (kW):",
        "",
        f"- Baseline import: `{comparison['baseline_phase_peak_interval_import_kw']}`; export: `{comparison['baseline_phase_peak_interval_export_kw']}`.",
        f"- Storage concept import: `{comparison['concept_phase_peak_interval_import_kw']}`; export: `{comparison['concept_phase_peak_interval_export_kw']}`.",
        "- These are interval-average active power, not RMS current, fuse relief or protection evidence.",
        "",
    ]
    lines += [
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
    if project.get("site_facts"):
        facts = [
            {
                key: fact[key]
                for key in ("fact_id", "subject", "property", "value", "unit", "status", "evidence")
                if key in fact
            }
            for fact in project["site_facts"]
        ]
        lines += [
            "### Typed site facts",
            "",
            "Statuses describe the evidence basis, not engineering verification or approval.",
            "Source and segment records are referenced only by ID; their private contents are not copied into this report.",
            "",
            "```json",
            canonical(facts).replace("`", "\\u0060").rstrip(),
            "```",
            "",
        ]
        if evidence_snapshot is not None:
            lines += ["Evidence record fingerprints (SHA-256):", ""]
            for item in evidence_snapshot["sources"]:
                lines.append(
                    f"- Source `{item['source_id']}` ({item['source_status']}; {item['acquisition_status']}): `{item['sha256']}`."
                )
            for item in evidence_snapshot["segments"]:
                lines.append(
                    f"- Segment `{item['segment_id']}` for `{item['source_id']}`: `{item['sha256']}`."
                )
            lines.append("")
    # JSON-encode user text in a code block; escape fences so notes cannot alter the report structure.
    notes = canonical({k: project[k] for k in ("assumptions", "unknowns", "evidence_refs")})
    lines += [
        "```json",
        notes.replace("`", "\\u0060").rstrip(),
        "```",
        "",
        "Legacy evidence_refs remain unvalidated pointers. Typed site-fact evidence IDs are checked against local canonical records, but that check does not establish authority, truth, or engineering review.",
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
    evidence_snapshot = resolve_site_facts(root, project)
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
    if evidence_snapshot is not None:
        inputs["evidence_snapshot"] = evidence_snapshot
    run_id = sha(canonical(inputs).encode())
    drawing_model = concept_model(project_id, scenario, run_id)
    output_text = {
        "results.json": canonical(result),
        "report.md": report_markdown(project, result, evidence_snapshot),
        "topology.mmd": topology_mermaid(scenario),
        "topology.svg": topology_svg(scenario, project_id),
        "concept-sheet.drawio": concept_sheet_drawio(drawing_model),
        "concept-sheet.svg": concept_sheet_svg(drawing_model),
        "electrical-schematic.qet": qet_schematic(drawing_model, scenario),
    }
    outputs = {name: text.encode("utf-8") for name, text in output_text.items()}
    manifest = {
        "inputs": inputs,
        "run_id": run_id,
        "release_status": "concept_only",
        "artifacts": {name: sha(data) for name, data in sorted(outputs.items())},
    }
    destination = target / "runs" / run_id
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError("output symlinks are not supported")
    if destination.exists():
        expected = {**outputs, "manifest.json": canonical(manifest).encode("utf-8")}
        if any(
            (destination / name).is_symlink() or (destination / name).read_bytes() != data
            for name, data in expected.items()
        ):
            raise ValueError("existing run was modified; refusing to overwrite")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".build-") as tmp:
        staged = Path(tmp) / run_id
        staged.mkdir()
        for name, data in outputs.items():
            (staged / name).write_bytes(data)
        (staged / "manifest.json").write_bytes(canonical(manifest).encode("utf-8"))
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
    preflight = sub.add_parser("preflight", help="read-only CSV quality report as JSON")
    preflight.add_argument("project_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            report = preflight_project(args.root, args.project_id)
            print(canonical(report), end="")
            return 0 if report["valid"] else 2
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
