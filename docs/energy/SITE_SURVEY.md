# Customer/site survey and evidence pack

Status: reusable blank template. This is data collection, not permission to energise.

Project ID: ____  Site ID: ____  Survey date: ____  Surveyor: ____
Property owner/contact reference (private workspace only): ____
Intended use: residential / business / mixed / marine interface / other: ____

For each answer record: **value + unit + evidence reference + date + status**.
Statuses: observed / customer-reported / source-reported / inferred / assumed /
verified / unknown. Leave unknown values blank; never substitute zero.

## 1. Requirements - customer interview

- [ ] What problem are we solving, and what is the order of priorities?
- [ ] Is the objective savings, self-consumption, export reduction, peak reduction,
      a smaller connection, selected backup, whole-site backup or off-grid operation?
- [ ] Which loads must continue, at what simultaneous power and for how long?
- [ ] What interruption is acceptable? Is PV charging during an outage required?
- [ ] What can be delayed or shed? What must never be automatically disconnected?
- [ ] What changes are planned: EV, heat pump, heating, machinery, extra PV?
- [ ] What is the total budget, maintenance expectation and acceptable uncertainty?
- [ ] Who owns, operates, insures and reviews the system?

## 2. Site and electricity boundaries

- [ ] Identify every supply separately and map buildings, floors and sub-boards to it.
- [ ] Confirm which meter serves this work; do not use a telecom-box label as proof.
- [ ] Obtain verified phase count and utility main-fuse/connection information.
- [ ] Record meter model, available data interface and phase aggregation behaviour.
- [ ] Record main switch, busbar and distribution-board ratings and existing diagrams.
- [ ] Map all sources: PV inverters, generators, batteries, UPS and shore supplies.
- [ ] Trace upstairs/cabin feeders to their protective devices and all downstream loads.
- [ ] Obtain inspection history and known defects; record access/isolation constraints.

**Important:** a downstream C32/B16 breaker does not establish the utility fuse
rating. Two PV stickers do not, by themselves, prove two independent inverters.
An X1 family marking does not identify its exact model, rating or battery capability.

## 3. Photographs - without exposing live parts

- [ ] Overall room, access routes, meter and closed distribution-board fronts.
- [ ] Readable device/model labels; full PV inverter typeplates and visible connections.
- [ ] Upstairs board/feed identification and cabin feeder markings where accessible.
- [ ] Cabin inside/outside, floor, roof, walls, openings and surrounding structures.
- [ ] Complete proposed cable route, entries, crossings and mounting locations.

Keep originals in the private workspace with dates and hashes. Do not unplug PV
connectors, remove utility seals or open energised enclosures to get a photograph.
Measurements inside electrical equipment require an appropriate safe-work procedure.

## 4. Electrical verification - competent tester/designer

- [ ] Earthing system, bonding, protective conductor continuity and neutral arrangement.
- [ ] RCD/RCBO exact type, rated residual current, location and coordination.
- [ ] Earth/loop impedance, prospective fault current and relevant existing test results.
- [ ] Cable conductor material, cross-section, length, installation method and grouping.
- [ ] Breaker/fuse characteristics, ratings and interrupting capability.
- [ ] Combined source contributions to distribution equipment and circuit conductors.
- [ ] Reverse-power suitability and protection in each proposed operating mode.
- [ ] Main fuse, feeder and equipment constraints per phase, not just summed kW.

A visible `I-delta-n 0.3 A` marking means 300 mA, not 30 mA; it does not by itself
establish the correct protection for a new battery circuit or prove the existing
installation is non-compliant. Have the complete arrangement checked.

## 5. Measurements and appliances

Obtain at least a matching-period annual bill plus the finest available import,
export and PV time series. Aim for a full year for seasonal modelling. Use a separate
faster per-phase logging plan for demand and transient investigation.

| Load ID | Description/model | Phase(s) | Rated kW/kVA/A | Measured duty | Startup demand | Backup? | Controllable? |
|---|---|---|---|---|---|---|---|
| ____ | ____ | ____ | ____ | ____ | ____ | ____ | ____ |

Include cooking, water/space heating, heat pumps, EV chargers, pumps, compressors,
workshop equipment and any genuinely three-phase loads. Do not deliberately overload
circuits to measure their limits.

| Channel | Sensor/location | Unit | Interval and timestamp meaning | Timezone | Missing/reset periods | Evidence ID |
|---|---|---|---|---|---|---|
| ____ | ____ | ____ | ____ | ____ | ____ | ____ |

Record voltage, current and power factor where required for current/power-quality
analysis. Interval-average active power is not a measurement of RMS current or inrush.

## 6. Solar installation

For each inverter: exact model/firmware, maximum AC output, phase assignment,
array size, panel models, orientation, tilt, shading, strings/MPPT arrangement,
existing limits, monitoring access, production history and manufacturer documentation.

Confirm whether the proposal retains existing PV on the grid side or requires a
separately engineered island-capable arrangement. A normal grid-tied PV inverter
should not be assumed to continue operating during an outage.

## 7. Placement and cable route

- [ ] Cabin dimensions, usable clearances, door opening and service access.
- [ ] Construction materials and structural/floor loading; support and anchoring.
- [ ] Measured cable-route length, not straight-line map distance.
- [ ] Routing method, conduit/trench feasibility, neighbouring services and entries.
- [ ] Ambient extremes, direct sun, humidity, condensation, water/flood exposure.
- [ ] Combustible storage, nearby windows/doors/intakes and occupied spaces/escape routes.
- [ ] Battery temperature management and inverter ventilation as separate needs.
- [ ] Detection/alarm path, safe external access and incident/isolation information.
- [ ] An upstairs option additionally needs structural, escape-route and fire review;
      an available socket is not a siting assessment.

## 8. Candidate equipment - only after the survey

Record exact cell/module, BMS and inverter specifications: temperature-dependent
limits, voltage/current ranges, independent shutdown, communication and failure
behaviour, warranties, certifications and supported combinations. For parallel
modules, evaluate operation with one module disconnected. Nominal kWh is not power.

## 9. Commercial and administrative inputs

- [ ] Import/export contract, effective dates, fees/bands, taxes and VAT treatment.
- [ ] Current/alternative network charges and one-time connection modification costs.
- [ ] All-in material, shipping, installation, test, inspection and maintenance costs.
- [ ] Site-use classification, permissions, insurer response and grid registration path.
- [ ] Applicable standards/requirements confirmed by the responsible reviewer.
- [ ] Scope-specific approvals and design/commissioning responsibilities in writing.

## 10. Survey handover

Deliver a site sketch, evidence index, phase map, load list, measurement-quality
report, requirements and blockers. Separate real customer facts from assumptions
used in early concepts. Do not order a final pack/inverter or select protective
ratings while the relevant site facts remain unresolved.
