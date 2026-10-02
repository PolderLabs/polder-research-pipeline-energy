# Primary-source research register

Checked: 2026-10-02. This is a seed register, not a completed applicability review.
The entries below identify which documentation was inspected and what it supports.
A release must capture the exact relevant revision/section and, where permitted,
a local copy with a hash. Do not copy licensed standards into this public repository.

| ID | Primary source | Supported use and limits |
|---|---|---|
| S1 | [Victron ESS: multiphase regulation](https://www.victronenergy.com/media/pg/Energy_Storage_System/en/multiphase-regulation---further-information.html) | Reviewed web chapter. Distinguishes phase-summed regulation, balanced output and individual-phase regulation. Not proof of this site's configuration or billing-meter behaviour. |
| S2 | [Victron ESS design and installation](https://www.victronenergy.com/media/pg/Energy_Storage_System/en/installation.html) | Topology/installation research entry point. Full exact-equipment and operating-mode review still required. |
| S3 | [Victron battery compatibility](https://www.victronenergy.com/live/battery_compatibility%3Astart) | Reviewed web guidance: DIY BMS support limitations and independent physical battery disconnection. A compatible protocol is not whole-pack certification. |
| S4 | [NIPV battery research collection](https://nipv.nl/onderzoek/batterijen/) | Reviewed publication index. Obtain and review the actual small-scale EOS/fire-safety and, when relevant, marine documents. No universal cabin dimensions or fire distances extracted here. |
| S5 | [IPLO: PGS 37-1/37-2 and regulatory changes](https://iplo.nl/thema/externe-veiligheid/publicatiereeks-gevaarlijke-stoffen-pgs/pgs-37-1-37-2/) | Reviewed explanation of guidelines and developing regulatory position. Do not treat a capacity threshold or a guideline as an automatic permission/exemption. Verify site applicability with the responsible authority. |
| S6 | [NEN low-voltage installations](https://www.nen.nl/en/elektrotechniek/installatievoorschriften/nen-1010-laagspanningsinstallaties) | Reviewed publisher overview, including reference to NEN 1010-8:2026. Full applicable standards and licensed calculation tables not reviewed or reproduced. |
| S7 | [QElectroTech official project](https://github.com/qelectrotech/qelectrotech-source-mirror) and [panel-layout documentation](https://download.qelectrotech.org/qet/manuals/html/users/drawing/lop.html) | Reviewed purpose: electrical drawings and linked panel layouts. Project explicitly does not provide a simulation/calculation engine. Adapter remains planned. |
| S8 | [JRC PVGIS hourly radiation](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-tools/hourly-radiation_en) and [API documentation](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en) | Reviewed modelled hourly resource/output capabilities. Pin dataset/API, input units, azimuth convention and time semantics. These are estimates, not site measurements. |
| S9 | [JRC PVGIS 6 information](https://photovoltaic-geographic-information-system.ec.europa.eu/en/about-pvgis-6) | Reviewed page describes a beta interface. Do not silently change an adapter's API/dataset version when a newer endpoint appears. |

## Per-source intake fields

Source ID; exact title/publisher; canonical URL; edition/revision/firmware; publication
and retrieval dates; section/page; licence; content hash; applicability; extracted
claim; reviewer; conflicts; affected component/method IDs; refresh trigger.

The research pipeline's existing source/segment/claim/gap records should be reused
for this lifecycle. The first energy CLI only stores pointers to such evidence;
it does not yet resolve, verify or refresh those pointers.

## Research questions to close before the first installation design

Exact grid and meter boundary; manufacturer-specific inverter/BMS compatibility;
PV behaviour during grid loss; feeder and switchboard source contributions;
normal/island protection behaviour; cabin environmental and incident requirements;
insurer acceptance of a self-built pack; owner/operator responsibilities; current
registration and site-specific permissions; the actual supplier tariff and fees.

No product approval, cell recommendation, RCD choice, conductor size or insurance
coverage is established by this register.
