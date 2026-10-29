# Decisions, assumptions, trade-offs

## Problem as I understood it
Model pumps, tanks, valves, sensors and flows; inject leaks, blockages, pump degradation and sensor faults; detect abnormal operation and simulate operating changes; keep traceability and measurable outputs. I framed the central operational question as: **when an alarm fires, is it a process fault or an instrument fault?** Tripping a process on a bad sensor is costly, and missing a real leak is worse.

## Assumptions
- Synthetic data only; fixed seed 20261022; 5-minute sampling over about 3.9 days (1,112 steps x 90 sensors, cut to exactly 100,000 rows).
- Steady-state affinity-law pump model: `Q = Qnom*speed*eff*valve*(1-block)`; `P = P0*(speed*eff)^2*(1-0.25*(Q/Qnom)^2)`. A leak removes flow before the tank inlet and lowers pressure by half the leaked fraction.
- Customer demand tracks the commanded flow; tank outflow uses a proportional controller so levels stay bounded.
- Mass-balance tolerance is 6% of nominal flow.
- Operating modes follow a fixed daily schedule (high demand 06-10 and 18-22, low demand 23-05).

## Key decisions and why
- **One physics module for everything.** The generator, the classifier's expected values and the what-if simulator share `physics.py`, so a simulated leak looks the way generated leaks look. No drift between "data" and "model".
- **Ground truth in separate tables** (`gt_events`, `gt_edge_cases`). It is used only as training/evaluation labels, never as a feature. Sensor faults corrupt only the measurement, so a healthy process is mislabelled by naive rules, which is what the classifier must resolve.
- **Alarms are derived, not random.** Threshold rules run on the measured telemetry and file everything as PROCESS (a rule engine cannot tell the difference). This creates the "sensor fault labelled as process fault" edge case honestly.
- **Residual features, not raw values.** Flow out vs flow in, pressure vs the pump curve at the current mode, level trend, and signal variance (stuck sensors have near-zero variance, spikes have large variance).
- **RandomForest** over deep learning: small tabular data, fast, robust, and each call is explainable via feature z-scores shown in the UI.
- **Rule-engine baseline** so the AI's value is measured, not assumed.
- **Claude copilot with a fallback.** The model explains incidents; a built-in playbook answers if there is no key or the call fails, so the app always works.
- **Raw SQL, no ORM.** Small schema, easy to read in a walkthrough. Foreign keys, ENUMs, unit comments, a bridge table (`pump_valve`) with effective dates, and append-only mode/alarm history.
- **Pipes use polymorphic node ids** (tank, valve or pump), so they cannot carry a real foreign key. The generator validates them, and the missing-node pipes are deliberate, labelled edge cases.

## How I tested / know it works
- `validation_summary.json`: primary-key uniqueness, 14 foreign-key checks (0 orphans), enums, date ordering (alarm cleared >= raised), every asset in a connected line, edge-case counts match injection, and flow-conservation violations all fall inside labelled scenarios (0 unlabelled).
- Reproducibility: generate twice with the same seed; `repro.py` compares checksums of every CSV and the SQL seed.
- Held-out classification metrics and confusion matrix (README).
- Manual end-to-end run of the full stack (MySQL, API, UI); What-if scenarios for leak, blockage and degradation behave as expected.

## Trade-offs and limitations
- **Evaluation is optimistic.** Stratified random split of windows; adjacent windows share events. Next step: hold out whole pumps or the last 30% of time, and report that number.
- Synthetic data means the classifier has learned the generator. Real data would add missing tags, clock drift, unlabelled faults and calibration history.
- Steady-state physics; no transients.
- No auth, no automated tests, dev server only, model retrains on each API start (no persisted model, no drift monitoring).
- Facilities form several hydraulic zones rather than one connected graph because pumps are the only inter-tank links.

## What I would do next
1. Pump-level and time-level hold-out evaluation.
2. pytest tests for physics, API contracts and the validation checks; Docker Compose for one-command setup.
3. Persist the trained model; add confidence thresholds and an "operator should not trust this" state for unseen operating modes.
4. Let the copilot call tools (query telemetry, run the simulator) instead of explaining one incident at a time.
5. Validate on a real or public historian dataset.