"""Hand calculations and failure regressions for the concept-only energy tool."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import random
import xml.etree.ElementTree as ET

import pytest

from polder_research.energy import (
    NOTICE, Sample, Scenario, build_project, canonical, dc_current_a,
    demo_profile, demo_scenario, init_project, main, read_json, read_profile,
    simulate, topology_svg, validate_project,
)

START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def rows(*pairs):
    return [Sample(START + timedelta(minutes=15 * i), tuple(load), tuple(pv)) for i, (load, pv) in enumerate(pairs)]


def test_hand_calculated_lossless_charge_discharge():
    s = replace(demo_scenario(1), auxiliary_kw_ac=0, charge_efficiency=1, discharge_efficiency=1)
    result = simulate(s, rows(([0], [2]), ([2], [0])))
    assert result["totals"]["charge_kwh_ac"] == pytest.approx(0.5)
    assert result["totals"]["discharge_kwh_ac"] == pytest.approx(0.5)
    assert result["totals"]["grid_import_kwh"] == pytest.approx(0)
    assert result["stored_energy_delta_kwh"] == pytest.approx(0)
    assert result["release_status"] == "concept_only"


def test_losses_soc_and_power_limits():
    s = replace(demo_scenario(1), nominal_kwh=1, auxiliary_kw_ac=0, charge_limit_kw_ac=2)
    result = simulate(s, rows(([0], [20]), ([0], [20]), ([20], [0]), ([20], [0])))
    assert max(row["charge_kw_ac"] for row in result["trace"]) <= 2
    assert max(row["stored_kwh"] for row in result["trace"]) <= 0.9 + 1e-12
    assert result["final_stored_kwh"] == pytest.approx(0.1)
    assert result["totals"]["discharge_kwh_ac"] == pytest.approx(0.8 * 0.95)
    assert result["totals"]["charge_kwh_ac"] == pytest.approx(0.8 / 0.95)
    assert result["energy_balance_error_kwh"] == pytest.approx(0, abs=1e-12)


def test_phase_summing_is_not_physical_fuse_relief():
    s = replace(demo_scenario(3), topology="single_phase", battery_phase=2,
                initial_soc=0.8, discharge_limit_kw_ac=6, auxiliary_kw_ac=0)
    result = simulate(s, rows(([5, 0, 0], [0, 0, 0])))
    assert result["trace"][0]["grid_kw_by_phase"] == pytest.approx([5, -5, 0])
    assert result["totals"]["grid_import_kwh"] == pytest.approx(0)
    assert result["peak_interval_import_kw_by_phase"][0] == pytest.approx(5)


def test_balanced_three_phase_does_not_zero_every_phase():
    s = replace(demo_scenario(3), initial_soc=0.8, discharge_limit_kw_ac=6, auxiliary_kw_ac=0)
    result = simulate(s, rows(([6, 0, 0], [0, 0, 0])))
    assert result["trace"][0]["grid_kw_by_phase"] == pytest.approx([4, -2, -2])
    assert result["totals"]["grid_import_kwh"] == pytest.approx(0)


def test_auxiliary_consumption_is_not_free():
    s = demo_scenario(1)
    result = simulate(s, rows(([0], [0])))
    assert result["totals"]["grid_import_kwh"] == pytest.approx(s.auxiliary_kw_ac * 0.25)
    assert result["totals"]["baseline_import_kwh"] == 0


def test_initial_energy_is_disclosed():
    s = replace(demo_scenario(1), initial_soc=0.9, auxiliary_kw_ac=0)
    result = simulate(s, rows(([2], [0])))
    assert result["stored_energy_delta_kwh"] < 0
    assert result["initial_stored_kwh"] == pytest.approx(9)
    assert result["final_stored_kwh"] < 9


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "10"])
def test_reject_invalid_numeric_inputs(value):
    with pytest.raises(ValueError):
        replace(demo_scenario(1), nominal_kwh=value)


@pytest.mark.parametrize("kwargs", [
    {"grid_phases": 2}, {"grid_phases": True}, {"charge_efficiency": 0},
    {"discharge_efficiency": 1.01}, {"initial_soc": 0.99},
    {"battery_phase": 2}, {"topology": "automatic"},
    {"topology": "three_phase_balanced"}, {"interval_minutes": True},
    {"minimum_soc": 0.9, "maximum_soc": 0.9, "initial_soc": 0.9},
])
def test_reject_invalid_scenario(kwargs):
    with pytest.raises(ValueError):
        replace(demo_scenario(1), **kwargs)


def test_unknown_scenario_field_rejected():
    data = asdict(demo_scenario(1)) | {"approved": True}
    with pytest.raises(ValueError):
        Scenario.from_dict(data)


@pytest.mark.parametrize("timestamp", [
    "2025-01-01T00:00:00+00:00", "2025-01-01T00:30:00+00:00", "2024-12-31T23:45:00+00:00"
])
def test_duplicate_gap_and_order_rejected(timestamp):
    text = "timestamp,load_l1_kw,pv_l1_kw\n2025-01-01T00:00:00+00:00,1,0\n" + timestamp + ",1,0\n"
    with pytest.raises(ValueError):
        read_profile(text, demo_scenario(1))


@pytest.mark.parametrize("bad_row", [
    "2025-01-01T00:00:00,1,0", "2025-01-01T00:00:00Z,nan,0",
    "2025-01-01T00:00:00Z,-1,0", "2025-01-01T00:00:00Z,1",
    "2025-01-01T00:00:00Z,1,0,unexpected",
])
def test_bad_csv_rows_rejected(bad_row):
    with pytest.raises(ValueError):
        read_profile("timestamp,load_l1_kw,pv_l1_kw\n" + bad_row + "\n", demo_scenario(1))


def test_timezone_offsets_are_normalised_before_gap_check():
    text = "timestamp,load_l1_kw,pv_l1_kw\n2025-10-26T02:45:00+02:00,1,0\n2025-10-26T02:00:00+01:00,1,0\n"
    assert len(read_profile(text, demo_scenario(1))) == 2


def test_empty_profile_and_wrong_headers_rejected():
    with pytest.raises(ValueError):
        read_profile("timestamp,load_l1_kw,pv_l1_kw\n", demo_scenario(1))
    with pytest.raises(ValueError):
        read_profile("timestamp,grid_import_kwh\n", demo_scenario(1))


@pytest.mark.parametrize("text", ['{"id":1,"id":2}', '{"n":NaN}', '{"n":Infinity}'])
def test_invalid_json_rejected(text):
    with pytest.raises(ValueError):
        read_json(text)


def test_seeded_replay_conserves_energy_and_bounds():
    randomizer = random.Random(42)
    for phases in (1, 3):
        scenario = demo_scenario(phases)
        samples = [Sample(START + timedelta(minutes=15 * i),
                          tuple(randomizer.random() * 4 for _ in range(phases)),
                          tuple(randomizer.random() * 5 for _ in range(phases))) for i in range(400)]
        result = simulate(scenario, samples)
        assert result["energy_balance_error_kwh"] == pytest.approx(0, abs=1e-8)
        assert canonical(result) == canonical(simulate(scenario, samples))
        for row in result["trace"]:
            assert 1 - 1e-10 <= row["stored_kwh"] <= 9 + 1e-10
            assert not (row["charge_kw_ac"] > 0 and row["discharge_kw_ac"] > 0)


def test_dc_current_is_explicit_steady_state_estimate():
    assert dc_current_a(4, 48, 0.93) == pytest.approx(89.605734767)
    with pytest.raises(ValueError):
        dc_current_a(4, 0, 0.93)


def test_customer_init_has_no_invented_scenario(tmp_path):
    directory = init_project(tmp_path, "customer-a")
    project = read_json((directory / "project.json").read_text())
    assert project["data_class"] == "customer"
    assert validate_project(project) is None
    with pytest.raises(ValueError, match="unknown"):
        build_project(tmp_path, "customer-a")
    assert not (directory / "runs").exists()


@pytest.mark.parametrize("phases", [1, 3])
def test_demo_bundle_determinism_hashes_and_notice(tmp_path, phases):
    init_project(tmp_path, "demo", phases)
    output = build_project(tmp_path, "demo")
    assert output == build_project(tmp_path, "demo")
    manifest = json.loads((output / "manifest.json").read_text())
    for name, expected in manifest["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected
    assert NOTICE in (output / "topology.svg").read_text()
    assert "synthetic concept" in (output / "report.md").read_text()
    ET.fromstring((output / "topology.svg").read_text())
    with pytest.raises(ValueError, match="overwrite"):
        init_project(tmp_path, "demo", phases)
    (output / "report.md").write_text("changed")
    with pytest.raises(ValueError, match="modified"):
        build_project(tmp_path, "demo")


def test_customer_directories_are_separate(tmp_path):
    a = init_project(tmp_path, "a", 1)
    b = init_project(tmp_path, "b", 3)
    assert a != b
    assert build_project(tmp_path, "a").is_relative_to(a)
    assert build_project(tmp_path, "b").is_relative_to(b)


@pytest.mark.parametrize("project_id", ["../other", "/tmp/test", "Case A", "x/y", "x\\y", "<script>", ""])
def test_unsafe_ids_rejected(tmp_path, project_id):
    with pytest.raises(ValueError):
        init_project(tmp_path, project_id)


def test_symlink_workspace_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".research").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        init_project(tmp_path, "a", 1)


def test_cli_failure_is_nonzero(tmp_path):
    assert main(["--root", str(tmp_path), "init", "a"]) == 0
    assert main(["--root", str(tmp_path), "build", "a"]) == 2


def test_svg_escapes_labels():
    document = topology_svg(demo_scenario(1), "<injected>")
    ET.fromstring(document)
    assert "&lt;injected&gt;" in document


def test_demo_profile_contract():
    scenario = demo_scenario(3)
    samples = read_profile(demo_profile(scenario), scenario)
    assert len(samples) == 96
    assert all(sample.pv_kw[1:] == (0, 0) for sample in samples)
