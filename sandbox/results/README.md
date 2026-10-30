# Sandbox run examples (2026-10-29)

Captured from the project machine. Times are UTC. These are examples of live
open-data checks, not unit tests.

| File | Command | What it shows |
|---|---|---|
| [2026-10-29-run-all-cme-timeout.txt](2026-10-29-run-all-cme-timeout.txt) | `uv run python sandbox/run_all.py` | SWPC and bonus feeds pass. DONKI CME times out (10/11). Summary marks DONKI FAIL. |
| [2026-10-29-nasa-donki-11of11.txt](2026-10-29-nasa-donki-11of11.txt) | `uv run python sandbox/nasa_donki.py` | A second pass reaches all 11 CCMC DONKI endpoints, including CME (27 events). |
| [2026-10-29-run-all-pass.txt](2026-10-29-run-all-pass.txt) | `uv run python sandbox/run_all.py` | The same suite a few minutes later. All five checks pass, including DONKI 11/11. |
| [2026-10-29-modal-fetch-once-us.txt](2026-10-29-modal-fetch-once-us.txt) | `modal run sandbox/us_fetch_modal.py::fetch_once` | One cloud run from Virginia, US. DONKI, the monthly OMNI file, and CDAWeb all return 200. The cron is not left running. |

The CME timeout on the first local run is the same GSFC behavior seen from
Ontario: the host sometimes does not answer before the client timeout. A retry
from the same machine can succeed. The Modal run does not depend on that path.
