<<<<<<< HEAD
# PumpSense: is the plant failing, or is the sensor lying?

Synthetic pump / tank / valve network with a fault classifier, a what-if simulator and an incident copilot.
When an alarm fires, PumpSense tells an operator whether the **process** is faulty (leak, blockage, pump degradation) or the **instrument** is (stuck, drifting or spiking sensor).

**Stack:** React 18 + Vite + Recharts, Flask, MySQL 8, scikit-learn (RandomForest).

## What is in the repo
| Path | Purpose |
|---|---|
| `backend/physics.py` | Shared pump curve, leak, blockage, degradation and tank mass-balance model (used by generator, classifier features and simulator) |
| `backend/generate.py` | Seeded synthetic data generator (seed 20261022), validation, CSV + SQL export |
| `backend/schema.sql`, `backend/load_mysql.py` | MySQL schema (13 tables) and loader |
| `backend/ml.py` | Window features from physics residuals + RandomForest classifier |
| `backend/app.py` | Flask API |
| `backend/repro.py` | Regenerates the data twice and compares checksums |
| `frontend/` | React UI (6 screens) |
| `AI_USAGE.md`, `DECISIONS.md` | AI disclosure with prompt history; assumptions, trade-offs, limits |

## Prerequisites
Python 3.10+ (tested on 3.12), Node 18+, MySQL 8 running locally. No paid services are required.

## Run it (Windows PowerShell)
```powershell
# 1. Generate data (about 1 minute). Writes backend/data/
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generate.py

# 2. Load MySQL (drops and recreates database "pumpsense")
$env:DB_USER="root"
$env:DB_PASSWORD="<your mysql password>"
python load_mysql.py

# 3. Start the API (trains the classifier from MySQL on start, 10-30 s). Leave running.
python app.py

# 4. New terminal: start the UI
cd frontend
npm install
npm run dev          # open http://localhost:5173
```
macOS / Linux: same steps, but activate with `source venv/bin/activate` and set variables with `export DB_USER=root DB_PASSWORD=...`.

Optional Claude copilot: set `$env:ANTHROPIC_API_KEY="..."` before `python app.py`. Without it the Incidents screen uses a built-in playbook (labelled as such in the UI). Optional: `DB_HOST` (default 127.0.0.1), `DB_NAME` (default pumpsense), `CLAUDE_MODEL`.

Starter scale (same generator, smaller): `python generate.py --fac 1 --pumps 4 --tanks 8 --valves 8 --points 5000`

## How to verify it works
1. `python generate.py` prints row counts: 3 facilities, 20 pumps, 30 tanks, 60 valves, 90 sensors, **100000** telemetry rows.
2. `backend/data/validation_summary.json`: all primary keys unique, every foreign-key orphan count is 0, edge cases present exactly as injected (2 pipes to missing nodes, 3 level readings over 100%, 2 simulations without config, sensor-fault alarms filed as process alarms).
3. `python repro.py` (from `backend/`): every file reports OK, i.e. the same seed gives identical output twice.
4. UI **Overview**: classifier vs rule-engine comparison and a confusion matrix.
5. UI **What-if**: pick any pump, set Leak fraction 0.3, Run. Expect a positive residual, the "flow imbalance" flag lit, and the classifier reading Leak. Blockage 0.4 reads Blockage; efficiency 0.7 reads Pump degradation. Each run is stored as `SIM-2026-######` in `simulation_run`.
6. UI **Incidents**: click a row to see the residual evidence and the copilot's suggestion.
7. UI **Alarm audit**: alarms the rule engine filed as process faults that the classifier reads as sensor faults.

## Results (seed 20261022, held-out windows)
| | Classifier | Threshold rule engine |
|---|---|---|
| Faults caught | 97.5% | 77.0% |
| Correct cause (process vs sensor) | 97.5% | 64.6% |
| False alarms on healthy windows | 0.3% | 0.1% |

**Read these with care:** the split is a random split of one-hour windows, and neighbouring windows are correlated, so the classifier numbers are optimistic. See `DECISIONS.md`.

## Known limitations
- All data is synthetic; the classifier learns this generator's physics. It demonstrates the pipeline, not real-plant accuracy.
- Optimistic evaluation (above). A hold-out by pump or by time is the next step.
- Steady-state physics only; no transients such as water hammer.
- Pumps are the only links between tanks, so each facility is several hydraulic zones, not one connected graph. Validation checks zones and orphan assets instead.
- Development server only, no authentication, no automated test suite. Verification is the validation summary, the reproducibility check and the manual steps above.

## Data provenance
Fully synthetic. No external data, no licences, no personal information. Credentials are read from environment variables only.
=======
