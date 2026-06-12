# SRE Runbook — Operations

## 1. System Summary

| Item | Value |
|---|---|
| Service | AI-Powered Personalized Healthcare Assistant |
| Owner team | ML Platform / Clinical AI |
| Primary resources | `mlw-hcai-{env}` (AML Workspace), `func-hcai-{env}` (Function App), `appi-hcai-{env}` (App Insights) |
| On-call rotation | PagerDuty schedule `hcai-mlops` |
| Severity matrix | See §6 |

## 2. Architecture Quick Reference

See [architecture.md](architecture.md) for the full diagram. Critical path for
a scoring request:

```
Client -> Azure Function (func-hcai-{env}) -> AML Managed Online Endpoint -> score.py -> Model
```

## 3. Routine Operations

### 3.1 Deploying a new model version

1. CI pipeline `cd-ml.yml` runs the AML training pipeline
   ([`pipeline_definition.yml`](../src/ml_pipeline/pipeline_definition.yml)).
2. `evaluate.py` and `responsible_ai/*` run automatically; if the promotion
   gate (see [ml-design.md §6](ml-design.md#6-evaluation)) fails, the run is
   marked failed and **no model is registered**.
3. `register_model.py` registers the model with tags `git_sha`,
   `training_run_id`, `data_version`.
4. A new deployment is created under the existing endpoint
   (`src/deployment/aml_endpoint/deployment.yml`) with **0% traffic**.
5. Run smoke tests (`tests/integration/`) against the new deployment's
   direct endpoint URL.
6. Shift traffic gradually: 10% → 50% → 100% over the course of ~1 hour,
   monitoring App Insights dashboards between steps.
7. Once at 100%, scale down and remove the previous deployment after a
   24-hour bake period.

### 3.2 Rolling back a deployment

```bash
# List deployments under the endpoint
az ml online-deployment list --endpoint-name ep-hcai-readmission-prod -g rg-hcai-prod -w mlw-hcai-prod

# Shift 100% traffic back to the previous (known-good) deployment
az ml online-endpoint update \
  --name ep-hcai-readmission-prod \
  -g rg-hcai-prod -w mlw-hcai-prod \
  --traffic "blue=100 green=0"
```

Rollback should be completed within **15 minutes** of detecting a regression
(see §6 severity SEV-2).

### 3.3 Rotating secrets

All secrets are stored in `kv-hcai-{env}`. To rotate:

```bash
az keyvault secret set --vault-name kv-hcai-prod --name aml-endpoint-key --value <new-key>
```

The Function App reads secrets via managed identity at runtime — **no
redeploy required**, but restart the Function App to clear any cached token:

```bash
az functionapp restart -g rg-hcai-prod -n func-hcai-prod
```

## 4. Monitoring & Alerts

| Alert | Source | Threshold | Defined in |
|---|---|---|---|
| `HighScoringLatencyP95` | App Insights | p95 > 1000ms over 5 min | [`alert_rules.json`](../src/monitoring/alert_rules.json) |
| `HighErrorRate` | App Insights | 5xx rate > 5% over 5 min | [`alert_rules.json`](../src/monitoring/alert_rules.json) |
| `EndpointAvailabilityDrop` | AML Endpoint metrics | availability < 99% over 15 min | [`alert_rules.json`](../src/monitoring/alert_rules.json) |
| `DataDriftDetected` | `data_drift_detection.py` (scheduled job) | PSI > 0.2 on any monitored feature | [`alert_rules.json`](../src/monitoring/alert_rules.json) |
| `ModelDriftDetected` | `model_drift_detection.py` (scheduled job) | prediction distribution KS p-value < 0.01 | [`alert_rules.json`](../src/monitoring/alert_rules.json) |

KQL queries for investigating alerts are in
[`app_insights_queries.kql`](../src/monitoring/app_insights_queries.kql).

## 5. Common Incidents & Response

### 5.1 `HighErrorRate` (5xx from Function API)

1. Query recent failures:
   ```kql
   requests
   | where timestamp > ago(30m) and success == false
   | summarize count() by resultCode, bin(timestamp, 5m)
   ```
2. Check whether failures originate from the Function App (auth/validation
   bugs) or the AML endpoint (model/runtime errors) using the
   `dependencies` table filtered to the endpoint URL.
3. If the AML endpoint is unhealthy: check deployment instance health
   (`az ml online-deployment get-logs ...`) and consider rollback (§3.2).
4. If the Function App is unhealthy: check recent deployments (`cd-ml.yml`,
   `cd-infra.yml`) for config drift; verify Key Vault access (managed
   identity permissions).

### 5.2 `HighScoringLatencyP95`

1. Check AML deployment instance count / CPU utilization — may need to scale
   out (`deployment.yml: instance_count`).
2. Check for cold-start effects after a recent deployment (new instances take
   time to warm).
3. Check downstream Key Vault / token-acquisition latency in the Function App
   dependency traces.

### 5.3 `DataDriftDetected`

1. Review the drift report produced by `data_drift_detection.py` (stored in
   `outputs/monitoring/drift_report_<date>.json`).
2. Identify which features drifted (PSI > 0.2) and cross-reference with
   upstream source system changes (e.g., new EHR fields, coding changes).
3. If drift is due to a genuine population shift (not a data bug), schedule a
   retraining run via `cd-ml.yml` (manual dispatch).
4. If drift is due to an upstream data quality issue, fix at the
   `data_pipeline/validate.py` / Great Expectations layer and re-run
   ingestion.

### 5.4 `ModelDriftDetected`

1. Review `model_drift_detection.py` output for prediction-distribution shift
   and (if available) rolling AUC against newly-labeled outcomes.
2. If rolling AUC has degraded below the promotion-gate threshold
   (ROC-AUC < 0.70), trigger an emergency retraining run and consider
   rolling back to a previous model version (§3.2) in the interim.

## 6. Severity Matrix

| Severity | Definition | Response time | Example |
|---|---|---|---|
| SEV-1 | Endpoint fully down / API unavailable | 15 min | All `/score` requests return 5xx |
| SEV-2 | Significant degradation (latency, error rate, model drift) | 1 hour | p95 latency > 2s, ModelDriftDetected |
| SEV-3 | Minor issue, no user impact | 1 business day | Single alert flake, non-blocking warning |

## 7. Useful Commands

```bash
# Tail Function App logs
az webapp log tail -g rg-hcai-{env} -n func-hcai-{env}

# Get AML online deployment logs
az ml online-deployment get-logs \
  --name blue --endpoint-name ep-hcai-readmission-{env} \
  -g rg-hcai-{env} -w mlw-hcai-{env} --lines 200

# Check current traffic split
az ml online-endpoint show \
  --name ep-hcai-readmission-{env} -g rg-hcai-{env} -w mlw-hcai-{env} \
  --query traffic

# Run drift detection manually
python -m src.monitoring.data_drift_detection --env prod
```

## 8. Escalation

1. On-call ML Platform engineer (PagerDuty `hcai-mlops`)
2. Clinical AI Governance Committee (responsible AI / fairness regressions —
   see [responsible-ai-report.md](responsible-ai-report.md))
3. Azure subscription owner (resource/quota issues)
