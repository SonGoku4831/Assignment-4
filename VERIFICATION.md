# Actual verification report — DA3408 Assignment 4

Validated on 25 October 2026 in this Codex cloud Linux environment. All results
below are from execution. No captions, monitoring values, screenshots or video
frames were fabricated. The first model request failed while the artifact CDN
was denied; network access was subsequently resolved and the complete real-model
workflow passed. The final model SHA256 matches the pinned upstream metadata.

## Measured experiment

- CPU pretrained BLIP revision: `82a37760796d32b1411fe092ab5d4e227313294b`.
- Model weights: 989,820,849 bytes; verified SHA256
  `d6638651a5526cc2ede56f2b5104d6851b0755816d220e5e046870430180c767`.
- Single photograph caption: **“two orange flowers”**.
- Single request including initial download/load: **92.745 s**;
  actual mean generation: **1.126 s**.
- ZIP: **10/10 successful captions**, **0 unexpected failures**, sequential CPU
  processing, **15.056 s** wall time and
  **1.503 s/image** mean model generation.
- Raw counters: +1 single success and +10 bulk successes. Histogram and summary
  inference counts both increased by 11. Active uploads, active inference and bulk
  activity were all zero in the recovery snapshot. Last batch size was 10.
- Sampled host CPU: idle mean **4.224%**, bulk mean **12.537%**, bulk peak **20.664%**
  using the 30-second rate window. Other machine activity and monitoring can
  contribute; these measurements do not isolate causal CPU usage by the worker.
- Sampled worker RSS: idle about **23.3 MB**, bulk peak **1,612,353,536 bytes**
  (about **1.50 GiB**). Weights remain loaded after recovery. Host RAM bulk mean
  was **4.929%**; it need not rise in direct proportion to worker RSS.
- Prometheus samples can lag the phase boundary by one 5-second scrape. The
  rolling CPU average remained elevated during recovery even though active-work
  gauges returned to zero; the report does not claim instantaneous CPU recovery.

Primary experiment data is in `artifacts/experiment.json`, raw metric snapshots in
`artifacts/metrics-before.txt`, `metrics-after-single.txt`, `metrics-after-bulk.txt`,
and asserted calculations in `artifacts/experiment-summary.json`.

## Requirement verification table

| Requirement | Status | Execution evidence | Files produced |
|---|---|---|---|
| Streamlit launches | PASS | Health response `ok`; real Chromium session rendered UI | `app.py`, `artifacts/streamlit-idle.png`, `artifacts/final-health.json` |
| Pretrained CPU-only inference | PASS | Pinned BLIP generated nonempty real captions; torch CPU wheel and explicit CPU tensors | `captioning.py`, `scripts/download_model.py`, `artifacts/model-integrity.json` |
| Single image workflow | PASS | Worker and browser generated captions; browser success `True` | `backend.py`, `client.py`, `artifacts/streamlit-single.png` |
| Bulk ZIP workflow | PASS | 10 sequential CPU captions; browser success `True` | `artifacts/experiment.json`, `artifacts/streamlit-bulk.png` |
| Invalid/corrupt files and ZIPs | PASS | 4 real-worker failure-path checks, including a mixed batch that continues after corruption | `scripts/test_live_inputs.py`, `artifacts/live-input-tests.json` |
| Memory/size/path safeguards | PASS | Unit tests cover memory exceptions, decompression-bomb dimensions, byte caps, traversal and 101-image rejection | `captioning.py`, `tests/test_captioning.py` |
| Four Prometheus metric types | PASS | Raw exposition has counters, gauges, histogram buckets and summary sum/count; deltas asserted on real inference | `artifacts/metrics-*.txt`, `scripts/analyze_experiment.py` |
| Bounded custom metadata labels | PASS | Mode, operation, outcome and three safe client categories; arbitrary client rejected | `captioning.py`, `tests/test_captioning.py` |
| Separate `/metrics` endpoint | PASS | Worker exposes HTTP port 8000 before any browser opens | `backend.py`, `prometheus.yml` |
| Prometheus integration | PASS | App, node, Prometheus and Alertmanager targets all `up=1`; promtool config valid | `artifacts/final-health.json`, `artifacts/prometheus-validation.txt` |
| Node CPU/RAM/disk | PASS | Real samples queried; overlay filesystem explicitly enabled for cloud namespace | `compose.yml`, `artifacts/stack-verification.json` |
| Grafana datasource | PASS | Health API: Successfully queried the Prometheus API | `monitoring/grafana/provisioning/datasources/prometheus.yml` |
| Dashboard coverage and refresh | PASS | 20 rendered panels, health/workload/latency/hardware/correlation; 5-second refresh | `monitoring/grafana/dashboards/caption-observatory.json`, `artifacts/grafana-dashboard.png` |
| Dashboard query data | PASS | **26/26 queries return finite data**, including P50/P95/P99 after real inference | `artifacts/stack-verification.json` |
| Dashboard JSON import/export | PASS | File provisioned successfully and actual Grafana dashboard exported via API | `artifacts/grafana-export.json` |
| Seven plotting commandments | PASS (implemented/inspected) | Accessible colors, line patterns/points, short axis names, linear scales/units, legends, titles and explanatory descriptions; final grading is assessor-owned | `scripts/build_dashboard.py`, `EVALUATION.md`, dashboard screenshots |
| Alert configurations and evaluation | PASS | All five rules pass promtool synthetic tests; Alertmanager configuration validates | `monitoring/alerts.yml`, `monitoring/alerts.test.yml`, `artifacts/alert-tests.txt` |
| Live alert pipeline | PASS | Worker stopped; real downtime alert received by Alertmanager; worker restarted and all targets recovered | `scripts/test_alert_delivery.py`, `artifacts/alert-delivery.json` |
| Recovery | PASS | Upload, inference and bulk gauges zero; model remains loaded; final monitoring healthy | `artifacts/experiment.json`, `artifacts/final-health.json` |
| Automated tests | PASS | **19 passed**, no failures or skipped tests; stubs explicitly restricted to unit tests | `tests/`, `artifacts/unit-tests.txt` |
| Browser execution | PASS | Single and bulk passed; **0 JavaScript page errors** | `scripts/browser_demo.py`, `artifacts/browser-verification.json` |
| Genuine demonstration video | PASS | **59.96 s**, H.264, 1600×1000; real Grafana 5s refresh and an additional 11-image live CPU workload with zero failures | `scripts/record_dashboard.py`, `artifacts/dashboard-demo.mp4`, `artifacts/video-verification.json` |
| Repeatable setup | PASS on current instance | Exact install helper rerun successfully; cached model checksum verified; dependencies remained satisfied | `scripts/install.sh`, `artifacts/install-repeatability.txt` |
| README, sample workload, evaluation guide | PASS | Exact commands, real CC BY photograph + 10-image ZIP generator, worked PromQL examples and AI attribution | `README.md`, `scripts/generate_workload.py`, `samples/generated/SOURCE.txt`, `EVALUATION.md` |
| External email/webhook notification | UNVERIFIED / not configured | Local Alertmanager pipeline is verified; no user-owned notification destination was supplied | `monitoring/alertmanager.yml` |
| Independent Ubuntu/fresh-task restoration | UNVERIFIED | Reproduction commands supplied and tested here; no second machine or published new task was available | `README.md`, saved environment draft |
| GitHub publication | See repository history | This report records validation before publication; subsequent publication is recorded in Git history | repository `main` branch |

## Additional evidence and interpretation

The browser test made actual file uploads through Streamlit. The video also ran
another real single-plus-ten-image workload while Grafana was recording; its full
captions and timestamps are in `artifacts/video-verification.json`. The original
WebM recording is retained locally under `artifacts/video/`; the MP4 is a simple
60-second trim/transcode, without synthetic charts, inserted frames or fake data.

Later tests intentionally submitted corrupt images and archives, producing
expected error counts in the dashboard. These are separate from the primary
11-success/0-error experiment. Totals therefore exceed 11. The live downtime test
also intentionally caused a short availability gap before the main experiment.
These events are real, documented diagnostic activity, not unexplained failures.

The dataset is one real CC BY flower photograph plus 10 brightness variants,
not ten distinct source scenes. Attribution and transformation code are included.
Resource metrics describe the cloud namespace available to node_exporter, not a
physical personal workstation. Two CPU threads and serialized generation bound
work; unit-tested memory exceptions are not proof of successful operation under
an actual operating-system OOM kill.

## Reproduce or continue

Use `README.md` for startup and reproduction. Services were left running at the
end of validation. No external service was messaged during validation. GitHub publication after
validation is recorded in repository history.
Review the saved environment installation/startup/network configuration and publish
through environment settings if you want to retain the prepared cloud snapshot.
Publication and a new-task restoration are not claimed as completed.
