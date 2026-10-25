# Caption Observatory — DA3408 Assignment 4

CPU-only BLIP image captioning with Streamlit, Prometheus, node_exporter,
Grafana and Alertmanager. **Read [VERIFICATION.md](VERIFICATION.md) for the actual
execution results and outstanding limitations; implementation is not proof of inference success.**

## Files and architecture

`Streamlit :8501 → local worker :8001 → pretrained BLIP on CPU`

`worker /metrics :8000 + node_exporter :9100 → Prometheus :9090 → Grafana :3000`

`Prometheus alert rules → Alertmanager :9093 → local evaluation receiver`

- `app.py`: single/ZIP UI, status, captions, timing, error table and CSV export.
- `backend.py`, `client.py`, `captioning.py`: bounded HTTP worker, CPU inference,
  safe in-memory archive handling, serialized generation and Prometheus metrics.
- `prometheus.yml`, `monitoring/`: scrapes, alert rules, synthetic rule tests,
  Grafana provisioning and the 20-panel dashboard JSON.
- `scripts/`: startup, sample workload generation, model download, live experiments,
  dashboard query verification, browser screenshots/recording and alert delivery test.
- `tests/`: isolated tests with an explicitly labeled stub model. These validate
  logic and error paths, **not pretrained-model inference**.
- `artifacts/`: measured experiments, test outputs and API export/evidence.

## Run in the prepared Codex environment

```bash
cd /workspace/Assignment-4
source /workspace/assignment4-env/venv/bin/activate
python scripts/generate_workload.py
python scripts/download_model.py
./scripts/start.sh
```

The final command stays in the foreground and starts monitoring, the worker and
Streamlit. Model download is a separate command so an access failure is visible.
Open the local services on your own Ubuntu machine, or use an approved port tunnel.
The onboarding interface does not provide localhost previews.

- Streamlit: port **8501**; worker health: **8001/health**; metrics: **8000/metrics**.
- Prometheus: port **9090**; Grafana: **3000**; Alertmanager: **9093**.
- Grafana's initial local credentials are `admin` / `admin`; change the password
  before making it reachable by other users. The provisioning datasource is
  `Prometheus` (UID `prometheus`). Open the **DA3408** folder and
  **Caption Observatory · CPU Image Captioning** dashboard.
- All listeners bind to loopback. Compose uses Linux host networking. No external
  email or webhook is configured; alerts are verifiable locally in Alertmanager.

In Single mode, upload `samples/generated/flower.jpg`. In Bulk mode, upload
`samples/generated/bulk-10.zip`. Both use the same worker and metrics. The first
inference loads the model. Subsequent calls reuse it. Model-ready stays zero
when loading fails; errors appear in the results table and backend log.

## Reproduce on Ubuntu x86-64

Prerequisites: Python 3.12 with `venv`, Docker Engine and Docker Compose v2,
`curl`, and sufficient disk/RAM for a roughly 1 GB model plus dependencies.
The CPU-only wheels and a maximum of 2 CPU threads by default avoid CUDA.
For optional browser evidence install Chromium and FFmpeg using Ubuntu packages;
`browser_demo.py` uses `/usr/bin/chromium`.

```bash
cd Assignment-4
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu
python -m pip check
python scripts/generate_workload.py
python scripts/download_model.py
PYTHON="$PWD/.venv/bin/python" ./scripts/start.sh
```

The full lock includes development tools. `requirements.txt` lists runtime
direct dependencies; `requirements-dev.txt` adds test and browser tools. Repository
files and provisioning directories must be readable by the container users;
`chmod -R a+rX monitoring; chmod a+r prometheus.yml` fixes permissions when needed.

Required public download hosts include PyPI, PyTorch CPU wheels, GitHub container
registries, `huggingface.co` and the actual Hugging Face artifact CDN. The pinned weights redirected to **`us.aws.cdn.hf.co`**. An initial proxy denial
was resolved after the network draft was updated; the model downloaded and its
SHA256 was verified. Preserve that domain in cloud environment settings. Do not disable TLS
verification, supply a token for a public model, or substitute fake captions.

BLIP revision is pinned to `82a37760796d32b1411fe092ab5d4e227313294b`.
It has `pytorch_model.bin`, not `model.safetensors`; current PyTorch/Transformers
load these weights with their supported safe weights-only path and no remote code.
The download cache is `.cache/huggingface`. For an already-downloaded local copy,
set `CAPTION_MODEL=/absolute/model/path`. To change to another Hub model/revision,
set both `CAPTION_MODEL` and `CAPTION_MODEL_REVISION`; it must remain BLIP-compatible.
`CPU_THREADS` is clamped to 1–4. Generation uses 30 maximum new tokens, one beam,
and deterministic decoding on CPU.

## Execute the validation and experiment

With the stack running, use another terminal:

```bash
source /workspace/assignment4-env/venv/bin/activate  # or source .venv/bin/activate
python -m pytest tests -q
python scripts/experiment.py
python scripts/analyze_experiment.py
python scripts/check_stack.py
python scripts/browser_demo.py --bulk
```

`experiment.py` captures a 30-second idle baseline, submits one real photograph
and a 10-image ZIP via the exact worker used by Streamlit, samples Prometheus every
2 seconds, and observes 15 seconds of recovery. It saves raw `/metrics` before,
after single, and after bulk processing plus timestamps and results in
`artifacts/experiment.json`. It exits nonzero unless all 11 captions succeed.
The 10 ZIP images are brightness variations of a real flower photograph, not
10 distinct scenes. Original attribution is saved in `samples/generated/SOURCE.txt`.
An increase in global host CPU is not guaranteed by a small two-thread workload;
the report must show measured values rather than claim a spike occurred.

`check_stack.py` executes every dashboard expression and exports the actual
provisioned dashboard to `artifacts/grafana-export.json`. Empty series and NaN
are explicitly recorded; latency quantiles need successful inference observations.
These checking scripts use Grafana's initial local login. If you changed it,
set `GRAFANA_USER` and `GRAFANA_PASSWORD` securely in your local process rather
than commit credentials. Do not use unchanged default credentials in production.

```bash
docker exec assignment4-prometheus-1 promtool check config /etc/prometheus/prometheus.yml
docker exec assignment4-alertmanager-1 amtool check-config /etc/alertmanager/alertmanager.yml
docker cp monitoring/alerts.yml assignment4-prometheus-1:/tmp/alerts.yml
docker cp monitoring/alerts.test.yml assignment4-prometheus-1:/tmp/alerts.test.yml
docker exec -w /tmp assignment4-prometheus-1 promtool test rules alerts.test.yml
python scripts/test_alert_delivery.py
```

The final command intentionally stops **only this repository's worker**, waits
for the 30-second downtime rule plus scrape/evaluation/delivery delays, checks the
Alertmanager API, and restarts the worker in a `finally` block. This resets all
process-local counters, so run it **before** the workload experiment. Synthetic
rule tests exercise all five thresholds and are separate from measured results.
External notifications require a user-owned destination and are not configured.

## Dashboard and alert interpretation

The 20 panels cover health and model readiness, attempts/outcomes, mode rates,
mean and P50/P95/P99 latency, active work, batch size, request duration, CPU, host
RAM, process RSS, disk and CPU/memory correlation with bulk activity. It refreshes
every **5 seconds**. See [EVALUATION.md](EVALUATION.md) for manual calculations and
AI prompt attribution. Panel descriptions explain cold starts, counter resets,
rolling windows and measurement scope.

Node exporter sees the cloud machine/container-host namespaces available to it,
not your personal computer. Overlay filesystem statistics are enabled explicitly
because the cloud root filesystem uses overlay. Physical host disk utilization
cannot be inferred from a container's mount namespace. The CPU and RAM percentages
may include other cloud-machine activity; process RSS isolates the worker.

## Record a genuine approximately 60-second demonstration

Once real captions have passed, run:

```bash
python scripts/browser_demo.py --bulk
python scripts/record_dashboard.py
```

The first command verifies real browser uploads. The second records a 65-second
Grafana tour with actual 5-second refreshes, starts another real single+10-image
bulk workload during recording, and exports a genuine **60-second MP4** at
`artifacts/dashboard-demo.mp4`. Full WebM sources remain in `artifacts/video/`;
`artifacts/video-verification.json` records timestamps, trim offset and live
workload captions. System FFmpeg is reused through a local Playwright cache
symlink, so no redundant encoder download is needed.
Do not present a baseline-only recording as proof of successful captions.

For a live workload video, open Grafana with a 5-second refresh, begin recording
with OBS/your screen recorder, show idle CPU/RAM for 10 seconds, upload the single
image in Streamlit, return to Grafana, upload the 10-image ZIP, show active bulk,
throughput/latency and correlation panels, then show active requests returning to
zero. Stop near 60 seconds or keep the workload visible if CPU inference takes
longer. Submit the genuine recording together with JSON export and code.

## Submission

Submit source, requirements, monitoring configuration, dashboard JSON, evaluation
guide, verification report and the genuine MP4. The prepared archive is
`/workspace/Assignment-4-submission.zip`. Model weights, virtualenvs and raw browser
recordings are excluded from the archive; download the pinned model when reproducing.
The sample photograph is CC BY 2.0; see `samples/generated/SOURCE.txt` for attribution
and the record of brightness transformations in `scripts/generate_workload.py`.

## Stop and preserve data

Stop the foreground Streamlit command with Ctrl+C. The launcher cleans up the
worker it started. If the alert test restarted it, stop that worker separately
using its recorded PID only after checking ownership. `docker compose stop` stops
monitoring while preserving volumes. Do not run `down -v` unless deleting all
Prometheus history and Grafana data is intended. The repository includes the application and demonstration evidence; review the
verification report before submitting the assignment.
