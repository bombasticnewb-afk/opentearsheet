---
name: New connector / filing parser
about: Propose a new data source or SEC form for OpenTearsheet
title: "[connector] "
labels: connector, enhancement
---

**Form or data source**
e.g. Schedule 13D/13G, Form 144, N-PORT, XBRL company facts

**Free public endpoint(s)**
Link the SEC (or other free, keyless) endpoint and its documentation.

**Facts it would add to the memo**
List 3–6 concrete, citable facts, e.g. "Activist stake filed: 7.2% by X on DATE".

**Entity type**
`company` (ticker/CIK) or `firm` (13F CIK / IAPD CRD)?

**Gotchas you know about**
Units, amendments, schema versions, rate limits...

- [ ] I'd like to build this myself
- [ ] I can provide a sample filing for a synthetic test fixture
