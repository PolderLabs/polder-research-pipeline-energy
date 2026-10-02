# Polder Energy Engineering Workbench

**Research -> site survey -> reproducible calculations -> concept drawings ->
reviewed engineering -> commissioning.**

An energy-focused extension of Polder Research Pipeline for PolderLabs customer
projects. It keeps the original local research/evidence foundation and adds a
small, runnable AC-storage concept workbench. It is an alpha engineering tool,
not an automatic installer, certification system or live energy controller.

Start with the [master plan](docs/energy/ENERGY_WORKBENCH_PLAN.md),
[site survey](docs/energy/SITE_SURVEY.md),
[calculation contract](docs/energy/CALCULATION_CONTRACT.md),
[topology/drawing guide](docs/energy/TOPOLOGIES_AND_DRAWINGS.md),
[source register](docs/energy/RESEARCH_SOURCES.md) and
[implementation roadmap](docs/energy/ROADMAP.md).

## Run a concept now

Use Python 3.14+ for this repository. Clone **this energy fork**, not the generic
upstream installer (which has not yet been specialised for the energy workflow):

```sh
git clone https://github.com/PolderLabs/polder-research-pipeline-energy.git
cd polder-research-pipeline-energy
python -m venv .venv
# Activate .venv using your operating system's normal activation command.
python -m pip install -e .

polder-energy demo demo-single --phases 1
polder-energy build demo-single
polder-energy demo demo-three --phases 3
polder-energy build demo-three
```

The commands print the local project/output directories under
`.research/energy/projects/`. Open `report.md`, `topology.svg` or the
`concept-sheet.svg` preview in the generated run directory. Edit the customer-facing
concept in `concept-sheet.drawio` with draw.io Desktop, or the functional-block
electrical schematic in `electrical-schematic.qet` with QElectroTech. These are
offline-friendly native files; drawings are concept-only and edits are not synced
back into calculations. `results.json`, `topology.mmd` and `manifest.json` contain
the same scenario's results and provenance hashes.

For an agent-assisted drawing request, see
[`docs/energy/AGENT_DRAWING_WORKFLOW.md`](docs/energy/AGENT_DRAWING_WORKFLOW.md)
for the brief fields, immutable-run workflow and validation limits.

Without installing a console entry point, the equivalent source command is:

```sh
PYTHONPATH=src python -m polder_research.energy --help
```

Demos are invented data, not a customer design or a battery recommendation.
For a real intake:

```sh
polder-energy init customer-a
```

This deliberately leaves `scenario` null. Complete the survey and explicit model
inputs before building. The replay accepts a documented per-phase load/PV CSV,
not arbitrary P1 data or annual bills. See the calculation contract. To compare
one-phase storage on a three-phase supply, use `grid_phases: 3`,
`topology: "single_phase"` and a verified/modelled `battery_phase` explicitly.

## Implemented versus planned

| Implemented now | Still requires development/review |
|---|---|
| Local case initialisation and synthetic demos | Canonical site/evidence schema and dashboard integration |
| SOC/power/efficiency-aware self-consumption replay | Raw meter/PV adapters and full data-quality workflow |
| Physical per-phase active-power reporting | RMS-current, protection, cable and fault calculations |
| Hashed JSON/Markdown/Mermaid/SVG concept bundle | Reviewed CAD/SLD, cable schedule and final BOM |
| Strict input/failure tests | Tariff optimisation, independently validated forecasts and payback |
| Unconditional `concept_only` status | Authorised review, construction release and as-built lifecycle |

The current three-phase replay is **balanced**. Net-zero power across phases does
not mean every phase has zero current. No output certifies a grid-connection
reduction, safe backup, suitable cable/fuse or compliant installation.

## Existing research foundation

The original research application remains available:

```sh
polder-research serve
```

It supports local evidence/knowledge workflows; the new energy CLI is not yet a
page in that dashboard. The dashboard is local and unauthenticated: do not expose
it as a customer portal. Laya and remote classification remain optional upstream
capabilities, not requirements for energy calculations.

See the [knowledge-base dashboard](knowledge-base/index.md),
[research methods](knowledge-base/00-home/research-methods.md),
[evidence model](knowledge-base/00-home/evidence-model.md),
[AGENTS.md](AGENTS.md) and [energy agent contract](agents/energy-engineering-agent.md).

## Customer privacy and safety

This repository is public. Commit code, templates and synthetic fixtures only.
Customer photos, bills, telemetry, addresses, meter IDs and contracts stay in
private local workspaces. `.research/` is already gitignored, but that is not
access control, encryption or a backup system. Unrelated customers should have
separate workspace roots and controlled access. No customer material is sent to
cloud services by the energy CLI.

Every energy report/drawing is labelled **CONCEPT ONLY - NOT FOR INSTALLATION**.
A complete installation requires source-backed design, appropriate competent
review, site-specific permissions/requirements and measured commissioning.
See [SECURITY.md](SECURITY.md) and the master plan.

## Development

```sh
python -m pip install -r requirements-ci.txt
python -m pip install -e .
ruff check .
ruff format --check .
PYTHONPATH=src pytest -q
python scripts/emit_implementation_status.py
```

Run the focused new tests with `PYTHONPATH=src pytest -q tests/test_energy.py`.
See [validation notes](docs/energy/VALIDATION.md) for the checks actually performed
on this change and the limits of those checks. Existing research features and
licensing are preserved; see [CONTRIBUTING.md](CONTRIBUTING.md) and [LICENSE](LICENSE).
