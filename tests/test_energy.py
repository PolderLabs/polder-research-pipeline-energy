"""Hand calculations and failure regressions for the concept-only energy tool."""

import hashlib
import json
import random
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from polder_research.energy import (
    NOTICE,
    Sample,
    Scenario,
    build_project,
    canonical,
    concept_model,
    concept_sheet_svg,
    dc_current_a,
    demo_profile,
    demo_scenario,
    init_project,
    main,
    qet_schematic,
    read_json,
    read_profile,
    simulate,
    topology_mermaid,
    topology_svg,
    validate_project,
)

START = datetime(2025, 1, 1, tzinfo=UTC)


def rows(*pairs):
    return [
        Sample(START + timedelta(minutes=15 * i), tuple(load), tuple(pv))
        for i, (load, pv) in enumerate(pairs)
    ]


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
    s = replace(
        demo_scenario(3),
        topology="single_phase",
        battery_phase=2,
        initial_soc=0.8,
        discharge_limit_kw_ac=6,
        auxiliary_kw_ac=0,
    )
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


@pytest.mark.parametrize("phases", [1, 3])
def test_same_profile_baseline_comparison_discloses_soc_and_phase_flows(phases):
    scenario = replace(
        demo_scenario(phases),
        nominal_kwh=1,
        minimum_soc=0.1,
        maximum_soc=0.9,
        initial_soc=0.5,
        charge_limit_kw_ac=1,
        discharge_limit_kw_ac=1,
        charge_efficiency=1,
        discharge_efficiency=1,
        auxiliary_kw_ac=0,
    )
    if phases == 1:
        samples = rows(([0], [2]), ([2], [0]))
    else:
        samples = rows(([0, 0, 0], [2, 2, 2]), ([2, 2, 2], [0, 0, 0]))
    result = simulate(scenario, samples)
    comparison = result["comparison"]
    assert comparison["baseline_import_kwh"] == pytest.approx(0.5 * phases)
    assert comparison["concept_import_kwh"] == pytest.approx(0.5 * phases - 0.25)
    assert comparison["baseline_export_kwh"] == pytest.approx(0.5 * phases)
    assert comparison["concept_export_kwh"] == pytest.approx(0.5 * phases - 0.25)
    assert comparison["baseline_minus_concept_import_kwh"] == pytest.approx(0.25)
    assert comparison["baseline_minus_concept_export_kwh"] == pytest.approx(0.25)
    assert comparison["stored_energy_delta_kwh"] == pytest.approx(0)
    assert comparison["conversion_loss_kwh"] == pytest.approx(0)
    assert comparison["auxiliary_kwh"] == pytest.approx(0)
    assert len(comparison["baseline_phase_import_kwh"]) == phases
    assert len(comparison["concept_phase_peak_interval_import_kw"]) == phases
    assert "not savings" in comparison["notices"][0]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "10"])
def test_reject_invalid_numeric_inputs(value):
    with pytest.raises(ValueError):
        replace(demo_scenario(1), nominal_kwh=value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"grid_phases": 2},
        {"grid_phases": True},
        {"charge_efficiency": 0},
        {"discharge_efficiency": 1.01},
        {"initial_soc": 0.99},
        {"battery_phase": 2},
        {"topology": "automatic"},
        {"topology": "three_phase_balanced"},
        {"interval_minutes": True},
        {"minimum_soc": 0.9, "maximum_soc": 0.9, "initial_soc": 0.9},
    ],
)
def test_reject_invalid_scenario(kwargs):
    with pytest.raises(ValueError):
        replace(demo_scenario(1), **kwargs)


def test_unknown_scenario_field_rejected():
    data = asdict(demo_scenario(1)) | {"approved": True}
    with pytest.raises(ValueError):
        Scenario.from_dict(data)


@pytest.mark.parametrize(
    "timestamp",
    ["2025-01-01T00:00:00+00:00", "2025-01-01T00:30:00+00:00", "2024-12-31T23:45:00+00:00"],
)
def test_duplicate_gap_and_order_rejected(timestamp):
    text = "timestamp,load_l1_kw,pv_l1_kw\n2025-01-01T00:00:00+00:00,1,0\n" + timestamp + ",1,0\n"
    with pytest.raises(ValueError):
        read_profile(text, demo_scenario(1))


@pytest.mark.parametrize(
    "bad_row",
    [
        "2025-01-01T00:00:00,1,0",
        "2025-01-01T00:00:00Z,nan,0",
        "2025-01-01T00:00:00Z,-1,0",
        "2025-01-01T00:00:00Z,1",
        "2025-01-01T00:00:00Z,1,0,unexpected",
    ],
)
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
        samples = [
            Sample(
                START + timedelta(minutes=15 * i),
                tuple(randomizer.random() * 4 for _ in range(phases)),
                tuple(randomizer.random() * 5 for _ in range(phases)),
            )
            for i in range(400)
        ]
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
    drawio = ET.parse(output / "concept-sheet.drawio").getroot()
    assert drawio.find(".//object[@id='GRID-01']") is not None
    assert drawio.find(".//mxCell[@id='E-GRID-MTR']") is not None
    assert "concept-sheet.drawio" in (output / "report.md").read_text()
    assert NOTICE in (output / "concept-sheet.svg").read_text()
    ET.fromstring((output / "concept-sheet.svg").read_text())
    qet = ET.parse(output / "electrical-schematic.qet").getroot()
    terminal_ids = {
        terminal.get("id")
        for terminal in qet.findall("./diagram/elements/element/terminals/terminal")
    }
    assert len(terminal_ids) == 12
    conductors = qet.findall("./diagram/conductors/conductor")
    assert len(conductors) == 6
    assert all(
        conductor.get("terminal1") in terminal_ids and conductor.get("terminal2") in terminal_ids
        for conductor in conductors
    )
    assert len(qet.findall("./collection/category/element")) == 7
    assert NOTICE in (output / "electrical-schematic.qet").read_text()
    report = (output / "report.md").read_text()
    assert "Same-period no-storage baseline comparison" in report
    assert "Signed differences are arithmetic only, not savings" in report
    assert report.index("| initial_stored_kwh |") < report.index(
        "## Same-period no-storage baseline comparison"
    )
    with pytest.raises(ValueError, match="overwrite"):
        init_project(tmp_path, "demo", phases)
    (output / "report.md").write_text("changed")
    with pytest.raises(ValueError, match="modified"):
        build_project(tmp_path, "demo")


def test_newline_only_artifact_tampering_is_detected(tmp_path):
    init_project(tmp_path, "demo", 1)
    output = build_project(tmp_path, "demo")
    report = output / "report.md"
    report.write_bytes(report.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="modified"):
        build_project(tmp_path, "demo")


def test_customer_directories_are_separate(tmp_path):
    a = init_project(tmp_path, "a", 1)
    b = init_project(tmp_path, "b", 3)
    assert a != b
    assert build_project(tmp_path, "a").is_relative_to(a)
    assert build_project(tmp_path, "b").is_relative_to(b)


@pytest.mark.parametrize(
    "project_id", ["../other", "/tmp/test", "Case A", "x/y", "x\\y", "<script>", ""]
)
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


def test_single_phase_topology_identifies_battery_phase():
    phase_one = demo_scenario(3)
    phase_two = replace(phase_one, topology="single_phase", battery_phase=2)
    phase_one = replace(phase_one, topology="single_phase", battery_phase=1)
    assert "on L1" in topology_svg(phase_one, "case")
    assert "on L2" in topology_svg(phase_two, "case")
    assert topology_svg(phase_one, "case") != topology_svg(phase_two, "case")
    assert topology_mermaid(phase_one) != topology_mermaid(phase_two)


def test_demo_profile_contract():
    scenario = demo_scenario(3)
    samples = read_profile(demo_profile(scenario), scenario)
    assert len(samples) == 96
    assert all(sample.pv_kw[1:] == (0, 0) for sample in samples)


def test_project_schema_is_canonical_and_validates_both_init_modes(tmp_path, monkeypatch):
    from polder_research.schemas import SchemaRegistry, package_registry

    registry = package_registry()
    schema = registry.get("energy-project")
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    calls = []
    original = SchemaRegistry.validate

    def observe(self, name, instance):
        calls.append((name, instance["data_class"]))
        return original(self, name, instance)

    monkeypatch.setattr(SchemaRegistry, "validate", observe)
    # A private workspace is not a schema checkout or an override mechanism.
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "energy-project.schema.json").write_text("{}")
    for name, phases in (("customer", None), ("demo", 3)):
        target = init_project(tmp_path, name, phases)
        project = read_json((target / "project.json").read_text())
        registry.validate("energy-project", project)
    output = build_project(tmp_path, "demo")
    assert json.loads((output / "results.json").read_text())["release_status"] == "concept_only"
    assert calls.count(("energy-project", "customer")) == 2
    assert calls.count(("energy-project", "synthetic")) == 3


@pytest.mark.parametrize(
    "update",
    [
        {"approved": True},
        {"release_status": "approved"},
        {"schema_version": 2},
        {"schema_version": True},
        {"id": "bad\n"},
        {"data_class": "public"},
        {"assumptions": []},
        {"assumptions": [" \t\n"]},
        {"evidence_refs": ["x" * 2001]},
        {"unknowns": [None]},
        {"scenario": {}},
    ],
)
def test_project_schema_rejects_invalid_envelopes(tmp_path, update):
    from polder_research.schemas import SchemaError, package_registry

    target = init_project(tmp_path, "case", 1)
    project = read_json((target / "project.json").read_text()) | update
    with pytest.raises(SchemaError):
        package_registry().validate("energy-project", project)
    with pytest.raises(ValueError):
        validate_project(project)
    (target / "project.json").write_text(canonical(project))
    with pytest.raises(ValueError):
        build_project(tmp_path, "case")
    assert not (target / "runs").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("grid_phases", 1.0),
        ("battery_phase", 1.0),
        ("interval_minutes", 15.0),
        ("nominal_kwh", float("nan")),
        ("nominal_kwh", float("inf")),
        ("initial_soc", 0.99),
        ("battery_phase", 2),
        ("topology", "three_phase_balanced"),
    ],
)
def test_schema_integration_keeps_strict_scenario_validation(tmp_path, field, value):
    target = init_project(tmp_path, "case", 1)
    project = read_json((target / "project.json").read_text())
    project["scenario"][field] = value
    with pytest.raises(ValueError):
        validate_project(project)


def test_project_schema_version_keeps_strict_integer_contract(tmp_path):
    target = init_project(tmp_path, "case")
    project = read_json((target / "project.json").read_text())
    project["schema_version"] = 1.0
    with pytest.raises(ValueError, match="unsupported schema_version"):
        validate_project(project)


def test_project_schema_failure_is_value_error_before_init_writes(tmp_path, monkeypatch):
    from polder_research.schemas import SchemaError, SchemaRegistry

    def reject(self, name, instance):
        assert name == "energy-project"
        raise SchemaError("test schema failure")

    monkeypatch.setattr(SchemaRegistry, "validate", reject)
    with pytest.raises(ValueError, match="test schema failure"):
        init_project(tmp_path, "case", 1)
    assert not (tmp_path / ".research").exists()


def test_qet_instance_labels_and_component_ids_match_definition_slots():
    scenario = demo_scenario(1)
    model = concept_model("demo", scenario, "a" * 64)
    root = ET.fromstring(qet_schematic(model, scenario))
    definitions = {
        element.get("name"): element.find("./definition/description")
        for element in root.findall("./collection/category/element")
    }
    expected_labels = {node["id"]: node["label"] for node in model["nodes"]}
    for element in root.findall("./diagram/elements/element"):
        name = element.get("type").rsplit("/", 1)[1]
        slots = definitions[name].findall("input")
        assert len(slots) == 2
        assert all({"x", "y", "size", "text"} <= set(slot.attrib) for slot in slots)
        fields = element.findall("./inputs/input")
        component_id = fields[1].get("text")
        assert {(f.get("x"), f.get("y")) for f in fields} == {
            (f.get("x"), f.get("y")) for f in slots
        }
        assert fields[0].get("text") == expected_labels[component_id]


def test_qet_records_exact_run_and_supply_storage_facts():
    scenarios = [demo_scenario(1), demo_scenario(3)] + [
        replace(demo_scenario(3), topology="single_phase", battery_phase=phase)
        for phase in (1, 2, 3)
    ]
    outputs = set()
    for scenario in scenarios:
        for run_id in ("a" * 64, "b" * 64):
            model = concept_model("demo", scenario, run_id)
            text = qet_schematic(model, scenario)
            outputs.add(text)
            annotations = [
                field.get("text") for field in ET.fromstring(text).findall("./diagram/inputs/input")
            ]
            assert f"Source run {run_id}" in annotations
            assert " | ".join(model["facts"]) in annotations
            assert NOTICE in annotations
    assert len(outputs) == len(scenarios) * 2


def test_svg_controller_route_avoids_all_node_interiors():
    model = concept_model("demo", demo_scenario(1), "a" * 64)
    root = ET.fromstring(concept_sheet_svg(model))
    route = root.find("{http://www.w3.org/2000/svg}path[@id='E-CTRL-INV']")
    # Parse the deliberately orthogonal SVG path so future coordinate changes
    # must retain geometric clearance, not merely match a snapshot string.
    tokens = iter(route.get("d").split())
    assert next(tokens) == "M"
    points = [(float(next(tokens)), float(next(tokens)))]
    for command in tokens:
        value = float(next(tokens))
        x, y = points[-1]
        assert command in ("H", "V")
        points.append((value, y) if command == "H" else (x, value))
    assert points[0] == (280, 563)  # Controller boundary.
    assert points[-1] == (770, 625)  # Inverter boundary.
    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        for node in model["nodes"]:
            left, top = node["x"], node["y"]
            right, bottom = left + node["w"], top + node["h"]
            if x1 == x2:
                assert not (left < x1 < right and max(y1, y2) > top and min(y1, y2) < bottom)
            else:
                assert not (top < y1 < bottom and max(x1, x2) > left and min(x1, x2) < right)


@pytest.mark.parametrize("phases", [1, 3])
def test_concept_sheet_wraps_node_copy_and_shows_bidirectional_grid_edges(phases):
    from polder_research.energy import concept_sheet_drawio, topology_mermaid

    scenario = demo_scenario(phases)
    model = concept_model("demo", scenario, "a" * 64)
    svg = ET.fromstring(concept_sheet_svg(model))
    drawio = ET.fromstring(concept_sheet_drawio(model))
    edge_kinds = {edge["id"]: edge["kind"] for edge in model["edges"]}
    for edge_id in ("E-GRID-MTR", "E-MTR-MDB"):
        assert edge_kinds[edge_id] == "power_bidir"
        assert (
            svg.find(f"{{http://www.w3.org/2000/svg}}path[@id='{edge_id}']").get("marker-start")
            == "url(#arrow-start)"
        )
        cell = drawio.find(f".//mxCell[@id='{edge_id}']")
        assert "startArrow=block" in cell.get("style")
    assert 'GRID["Utility grid' in topology_mermaid(scenario)
    assert "<--> METER" in topology_mermaid(scenario)

    svg_ns = "{http://www.w3.org/2000/svg}"
    for node in model["nodes"]:
        left, top, width, height = (node[key] for key in ("x", "y", "w", "h"))
        for suffix in ("LABEL", "DETAIL"):
            block = svg.find(f"{svg_ns}text[@id='{node['id']}-{suffix}']")
            font_size = int(block.get("font-size"))
            lines = block.findall(f"{svg_ns}tspan")
            assert lines
            approximate_width = max(len(line.text or "") * font_size * 0.62 for line in lines)
            assert approximate_width <= width - 24
            last_y = float(block.get("y")) + sum(float(line.get("dy", "0")) for line in lines[1:])
            assert last_y <= top + height - 20

    qet = ET.fromstring(qet_schematic(model, scenario))
    terminal_owners = {}
    for element in qet.findall("./diagram/elements/element"):
        component_id = element.find("./inputs/input[2]").get("text")
        terminal_owners.update(
            {
                terminal.get("id"): component_id
                for terminal in element.findall("./terminals/terminal")
            }
        )
    actual_connections = {
        frozenset((terminal_owners[line.get("terminal1")], terminal_owners[line.get("terminal2")]))
        for line in qet.findall("./diagram/conductors/conductor")
    }
    placed_ids = {
        element.get("text") for element in qet.findall("./diagram/elements/element/inputs/input[2]")
    }
    expected_connections = {
        frozenset((edge["source"], edge["target"]))
        for edge in model["edges"]
        if edge["kind"] in ("power", "power_bidir")
        and edge["source"] in placed_ids
        and edge["target"] in placed_ids
    }
    assert actual_connections == expected_connections


def test_preflight_hand_totals_and_utc_coverage():
    from polder_research.energy import profile_preflight

    text = (
        "timestamp,load_l1_kw,pv_l1_kw,load_l2_kw,pv_l2_kw,load_l3_kw,pv_l3_kw\n"
        "2025-10-26T02:45:00+02:00,4,0,0,8,2,2\n"
        "2025-10-26T02:00:00+01:00,0,4,8,0,2,2\n"
    )
    report = profile_preflight(text, demo_scenario(3))
    assert report["valid"] is True
    assert report["errors"] == []
    assert report["coverage"] == {
        "start_utc": "2025-10-26T00:45:00+00:00",
        "end_exclusive_utc": "2025-10-26T01:15:00+00:00",
        "interval_count": 2,
        "duration_hours": 0.5,
    }
    assert report["channel_energy_kwh"] == {
        "load_l1_kw": 1,
        "pv_l1_kw": 1,
        "load_l2_kw": 2,
        "pv_l2_kw": 2,
        "load_l3_kw": 1,
        "pv_l3_kw": 1,
    }
    assert report["power_unit"] == "kW"
    assert report["source_boundary"]["meter_boundary_verified"] is False


@pytest.mark.parametrize(
    "body",
    [
        "",
        "2025-01-01T00:00:00,1,0\n",
        "2025-01-01T00:00:00Z,nan,0\n",
        "2025-01-01T00:00:00Z,inf,0\n",
        "2025-01-01T00:00:00Z,-1,0\n",
        "2025-01-01T00:00:00Z,1\n",
        "2025-01-01T00:00:00Z,1,0,2\n",
        "2025-01-01T00:00:00Z,1,0\n2025-01-01T00:00:00Z,1,0\n",
        "2025-01-01T00:00:00Z,1,0\n2025-01-01T00:30:00Z,1,0\n",
        "2025-01-01T00:15:00Z,1,0\n2025-01-01T00:00:00Z,1,0\n",
    ],
)
def test_preflight_rejections_match_build_parser(body):
    from polder_research.energy import profile_preflight

    text = "timestamp,load_l1_kw,pv_l1_kw\n" + body
    scenario = demo_scenario(1)
    report = profile_preflight(text, scenario)
    assert report["valid"] is False
    assert report["errors"]
    assert report["coverage"] is None
    assert report["channel_energy_kwh"] is None
    with pytest.raises(ValueError):
        read_profile(text, scenario)


def test_preflight_reports_multiple_row_errors_and_header_mismatch():
    from polder_research.energy import profile_preflight

    report = profile_preflight(
        "timestamp,load_l1_kw,pv_l1_kw\nbad,1,0\n2025-01-01T00:15:00Z,-2,0\n",
        demo_scenario(1),
    )
    assert [error["row"] for error in report["errors"]] == [2, 3]
    assert report["row_count"] == 2
    mismatch = profile_preflight(demo_profile(demo_scenario(1)), demo_scenario(3))
    assert mismatch["errors"][0]["row"] == 1


def test_preflight_cli_deterministic_read_only_and_invalid_exit(tmp_path, capsys):
    project = init_project(tmp_path, "quality", 1)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    args = ["--root", str(tmp_path), "preflight", "quality"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == first
    report = json.loads(first)
    assert report["inputs"]["data_class"] == "synthetic"
    assert (
        report["inputs"]["profile_sha256"]
        == hashlib.sha256((project / "profile.csv").read_bytes()).hexdigest()
    )
    assert before == {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    assert not (project / "runs").exists()
    (project / "profile.csv").write_text("wrong,headers\n1,2\n")
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["valid"] is False
    with pytest.raises(ValueError):
        build_project(tmp_path, "quality")


def test_preflight_unknown_scenario_and_input_symlink(tmp_path, capsys):
    unknown = init_project(tmp_path, "unknown")
    assert main(["--root", str(tmp_path), "preflight", "unknown"]) == 2
    assert "scenario is unknown" in capsys.readouterr().err
    project = init_project(tmp_path, "linked", 1)
    (project / "profile.csv").unlink()
    (project / "profile.csv").symlink_to(unknown / "profile.csv")
    assert main(["--root", str(tmp_path), "preflight", "linked"]) == 2
    assert "symlinks" in capsys.readouterr().err


def test_preflight_unrepresentable_coverage_is_reported():
    from polder_research.energy import profile_preflight

    report = profile_preflight(
        "timestamp,load_l1_kw,pv_l1_kw\n9999-12-31T23:59:00Z,1,0\n",
        demo_scenario(1),
    )
    assert report["valid"] is False
    assert report["errors"]
    assert report["coverage"] is None


@pytest.mark.parametrize(
    "text",
    [
        "0001-01-01T00:00:00+01:00,1,0\n",
        "2025-01-01T00:00:00Z,1e308,0\n2025-01-01T01:00:00Z,1e308,0\n",
    ],
)
def test_preflight_numeric_and_timestamp_overflow(text):
    from polder_research.energy import profile_preflight

    report = profile_preflight(
        "timestamp,load_l1_kw,pv_l1_kw\n" + text,
        replace(demo_scenario(1), interval_minutes=60),
    )
    assert report["valid"] is False
    assert report["errors"]
    assert report["channel_energy_kwh"] is None
    canonical(report)
