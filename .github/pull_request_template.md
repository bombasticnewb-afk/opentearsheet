## What does this change?

## Checklist
- [ ] `pytest -q` passes locally (tests never touch the network)
- [ ] New parsing logic has a test with a **synthetic** fixture in `tests/fixtures/`
- [ ] Every new memo fact carries at least one `Source` linking to the public document
- [ ] No new required dependency in the core library (`src/opentearsheet`), no API keys, no telemetry
- [ ] Docs updated (README / CONTRIBUTING) if behaviour or config changed
