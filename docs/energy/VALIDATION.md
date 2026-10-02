# Validation record

Date: 2026-10-02. Scope: the new energy concept module and its tests.

## Executed checks

- Local Python 3.13.5 / pytest 9.0.2: **52 focused tests passed**.
- Single-phase and balanced three-phase synthetic demos initialised and built.
- Generated SVG rendered and inspected for legibility.
- Repeated build produces the same run directory; modified outputs are rejected.
- GitHub Actions Python 3.14.7 / pytest 9.1.1: the same **52 focused tests passed**,
  and both installed-console synthetic demo/build sequences completed successfully.
- The initial full repository CI passed its pytest, wheel-installation smoke,
  Python 3.13 syntax, vault audit, schema/derived-state and secret-scan jobs.
- Repository Ruff 0.16.9 formatting and safe lint fixes were applied to the new
  module/tests, then the focused tests, lint and format checks passed again.
- The existing implementation-status generator collected **337 tests** and
  regenerated the tracked status block (27 schemas, Python 3.14).

Initial CI evidence: [repository run](https://github.com/PolderLabs/polder-research-pipeline-energy/actions/runs/37020449399)
and [energy run](https://github.com/PolderLabs/polder-research-pipeline-energy/actions/runs/37020449908).
The initial runs correctly failed on formatting/lint and generated-status drift;
these were not suppressed. The branch maintenance run
[37020755745](https://github.com/PolderLabs/polder-research-pipeline-energy/actions/runs/37020755745)
applied the formatter and regenerated status. The temporary write-enabled
maintenance workflow was removed afterwards. The permanent energy workflow has
read-only permissions and checks without modifying tracked sources.

For the current revision's complete CI status, use the checks attached to
[pull request 1](https://github.com/PolderLabs/polder-research-pipeline-energy/pull/1).
A past successful job or this document is not approval of a later revision.

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
