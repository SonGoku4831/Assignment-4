# Manual evaluation and metric calculations

## Definitions and safe labels

`caption_images_total{mode,outcome,client}` counts one attempt for each image.
`mode` is `single|bulk`; `outcome` is `success|error`; client is
`interactive|demonstration|test`. Arbitrary session IDs and raw IPs create unbounded
cardinality and privacy concerns, so the application uses these safe client
categories. `caption_errors_total{mode,operation,client}` distinguishes validation,
decode, model loading and inference. A rejected ZIP increases request/validation
errors, not per-image attempts, because no images were processed.

Gauges include active uploads, active model generation, active bulk, last batch
size, model readiness and worker RSS. Histograms expose latency buckets, sum and
count; Python summaries expose `_sum` and `_count`, not client-computed quantiles.
Counters have `_total`. Histograms and summaries do not have `_total` in place of
`_count`. Model generation timing excludes decode and cold model loading;
per-image processing and whole-request timing include that work.

## Worked examples (illustrative, not measured run results)

| Panel | Calculation | Manual example |
|---|---|---|
| Application health | `up{job="caption-app"}` | 1 means last scrape succeeded; it does not prove weights loaded |
| Images attempted | `sum(caption_images_total)` | 1 single + 10 bulk = 11 attempted |
| Success/failure | `sum by (outcome) (caption_images_total)` | 10 valid + 1 corrupt image = 10 successes and 1 failure |
| Rate by mode | `sum by (mode) (rate(caption_images_total[1m]))` | Counter delta 12 over 60 s ≈ 0.2 images/s; Prometheus extrapolates boundaries |
| Mean inference | sum rate of summary `_sum` / sum rate of `_count` | Total 22 inference seconds / 11 observations = 2 seconds/image |
| Active generation | `caption_active_inferences` | 1 during serialized model generation, then 0 |
| Batch size | `caption_last_batch_size` | ZIP with 10 supported filenames → 10, including a corrupt candidate |
| CPU % | `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))` | Average idle 0.75 CPU seconds/s → 25% CPU |
| RAM % | `100 * (1 - MemAvailable/MemTotal)` | Available 24 GiB of 32 GiB → 25% used |
| Process RSS | `caption_process_memory_bytes` | 1,073,741,824 bytes = 1 GiB, distinct from whole-host RAM |
| Disk % | `100 * (1 - avail/size)` | 30 GiB available / 40 GiB size → 25% used, including reserved-block effects |

`clamp_min(denominator, 0.000001)` makes a mean display zero when no events occurred
rather than divide by zero. It does not create inference observations. Quantiles
must remain absent/NaN when there have been no successful/attempted generations.

For P50/P95/P99 use:

```promql
histogram_quantile(0.95,
  sum by (le) (rate(caption_inference_seconds_bucket[5m])))
```

Example bucket rates represent 100 observations: cumulative count at 2 s is 80,
at 4 s is 98, at +Inf is 100. The P95 estimate interpolates inside the (2,4]
bucket: `2 + (95-80)/(98-80) * (4-2) = 3.667 s`. This is an estimate, not the exact
95th raw observation. P50 and P99 use probabilities 0.50 and 0.99 respectively.
Never average precomputed quantiles across modes. Aggregate buckets preserving
`le`, then calculate the quantile. The query combines modes; mode-specific means
remain separate. A summary's `_sum/_count` is a mean and is not a P95.

Counters reset on worker restart; `rate` and `increase` account for resets. In the
measured experiment, compare raw before/after counters within one worker lifetime.
A real stop/start alert test is therefore performed first, not midway through the
success experiment. Prometheus scrapes every 5 seconds, so a sub-5-second activity
gauge can be missed even if counters change. Use a sufficiently long bulk workload.

## Alerts

- Down: `up == 0` continuously for 30 s, with extra scrape/evaluation/delivery time.
- High inference: rolling 2-minute mean > 10 s for 1 minute.
- Image errors: >20% failed in 5 minutes, at least 5 attempts, sustained 30 s.
- CPU >85% over 2 minutes sustained for 2 minutes.
- RAM >85% sustained for 2 minutes.

These are demonstration thresholds, not universal production limits. Prometheus
holds pending/firing state and sends firing alerts to Alertmanager. Alertmanager
groups and retains them; its local receiver has no external destination. Synthetic
rule tests are explicitly distinct from a live downtime alert and from real CPU
or latency stress. Absence of an external email is not evidence of email delivery.

## Seven plotting commandments

1. Blue/orange/teal accents avoid red-green-only semantics; text UP/DOWN, legends,
   line patterns and point markers add redundant identity.
2. Lines and markers remain interpretable in browser, print and captured video.
3. Axis labels state the measure; dual-axis correlation panels label both axes.
4. All time-series axes use linear scales; units are seconds, bytes, percent,
   operations/second or counts as appropriate.
5. Multi-series panels show legends with last and maximum values.
6. The dashboard and each panel have descriptive titles; panel descriptions serve
   as subtitles/context and are available through Grafana's panel information.
7. Each description explains the plot's meaning, measurement scope and caveats.

## AI attribution

Prompt used for generated dashboard PromQL and the filesystem exclusion regex:
“Build a professional DA3408 dashboard using caption_* metrics and node_exporter;
include health, mode throughput, errors, mean and histogram quantiles, bulk size,
CPU/RAM/disk and bulk correlation. Explain every query, use bounded labels,
accessible colors, explicit units, linear axes, and 5s refresh. Include overlay
filesystems for a container-based cloud machine while excluding pseudo filesystems.”

Prompt used for alert expressions:
“Write DA3408 alerts matching caption_* metrics for application down, high mean
inference latency, error ratio, CPU and RAM; guard low-volume error ratios and
document units and thresholds.”

These prompts also appear in generated configuration/source comments. Dashboard
JSON panel descriptions link to this evaluation guide through the repository;
JSON does not support comments. The student must independently explain and verify
the calculations at evaluation, as required by the assignment.
