# Agent-assisted concept drawings

This guide lets an agent help scope, generate and iterate on functional energy
concept drawings without treating them as installation designs. Read it together
with [the drawing contract](TOPOLOGIES_AND_DRAWINGS.md), [the site survey](SITE_SURVEY.md)
and the agent contract at `agents/energy-engineering-agent.md`.

## Quick start

For an existing, complete project, build its revision-linked artifact bundle:

```sh
polder-energy build <project-id>
```

The command prints the run directory under
`.research/energy/projects/<project-id>/runs/<run-id>/`. The agent should return
that local path and identify the relevant outputs:

- `concept-sheet.drawio` — editable customer-facing concept;
- `concept-sheet.svg` — preview;
- `electrical-schematic.qet` — editable functional-block schematic;
- `topology.svg` / `topology.mmd` — topology view/source;
- `report.md` / `manifest.json` — assumptions, scope and content hashes.

If the project is a new intake, use `polder-energy init <project-id>` and complete
the survey and explicit scenario/profile inputs first. Never fill unknowns with
demo values. `polder-energy demo <id> --phases 1` or `--phases 3` is only for
clearly labelled synthetic walkthroughs.

## Brief the agent

The user can request a drawing in ordinary language. Before making a site-specific
concept, the agent must identify or confirm:

```text
Audience: customer / installer discussion / internal review
Purpose: energy-flow concept / functional electrical blocks / other concept view
Project ID or explicitly synthetic scenario:
Known equipment and verified facts (with evidence references):
Unknowns to keep visible:
Requested changes to an existing drawing:
Output: native file only / preview / both
```

Do not request personally identifying data in chat or copy it to this public repo.
If critical scope inputs are unavailable, return the existing generic concept with
unknowns shown, or ask one focused clarification; never imply a complete design.

## Iterate safely

1. Use the project's validated scenario and existing generator as the source of
   truth. Do not hand-edit an immutable run artifact: the manifest covers every
   generated file, and the builder intentionally refuses modified runs.
2. For a reusable change, update the shared concept model/renderers in
   `src/polder_research/energy.py`, preserve stable component IDs and source run
   references, add XML/relationship assertions in `tests/test_energy.py`, then
   rebuild into a new run revision.
3. For a one-off visual iteration, make a clearly named working copy under
   `.research/energy/projects/<project-id>/drawings/`, outside the immutable
   `runs/<run-id>/` directory (for example `<run-id>-concept-sheet.drawio`). Record
   the parent run ID in the filename or accompanying note. Mark hand-edited
   derivatives as drafts; their original manifest hash no longer authenticates
   the edited file.
4. Keep `.drawio` XML well-formed and editable. Keep QET element/terminal IDs,
   conductor references and embedded symbols consistent. If draw.io Desktop or
   QElectroTech is available, open the output there before claiming editor-level
   validation. Without the application, report that limitation and run XML and
   relationship checks instead.
5. State the delivered file paths, what changed, which facts remain unknown and
   what validation was performed. Do not claim code compliance or installation
   readiness.

## Non-negotiable scope

These artifacts are functional concepts: not to scale, not an approved single-line
diagram, not wiring instructions, and not protection/cable/terminal/PE/N/backup
designs. Never invent site equipment or dimensions. Do not add cloud-editor embeds
or upload customer files. Any path from concept drawing to installation pack needs
qualified, site-specific engineering review and a separate approval workflow.
