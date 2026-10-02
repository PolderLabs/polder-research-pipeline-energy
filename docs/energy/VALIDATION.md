# Validation record

Date: 2026-10-02. Scope: the new energy concept module and its tests.

## Executed locally

- Python 3.13.5, pytest 9.0.2.
- `PYTHONPATH=src pytest -q tests/test_energy.py`: **52 tests passed**.
- Single-phase and balanced three-phase synthetic demos initialised and built.
- Generated SVG opened as a rendered image and inspected for legibility.
- Repeated build produces the same run directory; modified outputs are rejected.

The repository targets Python 3.14+. The focused local check does not replace the
repository's target-version CI or a full regression run. Ruff is not available in
the local authoring environment. Full CI, formatter checks and regeneration of the
existing implementation-status block must be completed before merging. Check the
pull request's actual check results rather than interpreting this note as CI approval.

## What the tests establish

Hand-calculated examples, loss accounting, SOC and power constraints, phase-summed
versus physical phase power, auxiliary consumption, initial/final stored energy,
invalid numeric inputs, timestamps and DST offsets, missing/duplicate CSV data,
JSON duplicate keys, path traversal/symlinks, determinism and run tampering are tested.
Seeded synthetic sequences exercise energy conservation across both phase counts.

## What they do not establish

No independent engineering validation, equipment certification, protection study,
RMS-current calculation, field measurement agreement, tariff accuracy or safe
islanding claim has been established. The project does not approve an installation.
Generated diagrams are functional concepts, not construction drawings. A test suite
can show that a documented model behaves consistently without proving that model
represents a particular customer's installation.
