# ML Design

## 1. Problem Framing

- **Task:** Binary classification — predict `readmitted_30d ∈ {0, 1}` for each
  inpatient encounter, evaluated at the time of discharge.
- **Unit of analysis:** One row per discharge encounter (`encounter_id`).
- **Prediction window:** 30 days post-discharge.
- **Label source:** Retrospective lookup — did the same `patient_id` have a
  subsequent inpatient admission within 30 days of this encounter's discharge
  date?
- **Consumers:** Care management dashboards and the `/score` API
  (see [api-design.md](api-design.md)); output is a probability + risk tier
  (`low` / `medium` / `high`), not a binary clinical directive.

## 2. Feature Set

| Feature | Type | Source | Notes |
|---|---|---|---|
| `age` | numeric | Patient | |
| `age_band` | categorical | derived | `<18, 18-39, 40-64, 65-79, 80+` |
| `sex` | categorical | Patient | fairness-sensitive |
| `ethnicity` | categorical | Patient | fairness-sensitive, optional at inference |
| `insurance_type` | categorical | Patient | |
| `admission_type` | categorical | Encounter | elective / emergency / urgent |
| `discharge_disposition` | categorical | Encounter | home / SNF / rehab / AMA / expired-excluded |
| `length_of_stay` | numeric | Encounter | days |
| `los_bucket` | categorical | derived | `0-2, 3-5, 6-10, 11+` |
| `comorbidity_count` | numeric | Diagnosis | |
| `charlson_index` | numeric | Diagnosis | |
| `comorbidity_score` | numeric | derived | weighted Charlson-based score |
| `prior_admissions_12mo` | numeric | Utilization | |
| `prior_ed_visits_12mo` | numeric | Utilization | |
| `prior_utilization_rate` | numeric | derived | `(prior_admissions_12mo + prior_ed_visits_12mo) / 12` |
| `num_medications` | numeric | Utilization | |
| `polypharmacy_flag` | boolean | derived | `num_medications >= 5` |
| `bmi` | numeric | Labs/Vitals | |
| `systolic_bp` | numeric | Labs/Vitals | |
| `glucose_level` | numeric | Labs/Vitals | |
| `creatinine` | numeric | Labs/Vitals | renal function proxy |

All feature definitions and derivations live in
[`src/data_pipeline/feature_engineering.py`](../src/data_pipeline/feature_engineering.py)
and canonical dtypes in [`src/common/schemas.py`](../src/common/schemas.py).

## 3. Train/Validation/Test Split

- **Temporal split** to avoid leakage: encounters are sorted by
  `discharge_date`.
  - Train: oldest 70%
  - Validation: next 15% (used for early stopping & hyperparameter selection)
  - Test: most recent 15% (held out, used only for final evaluation & RAI report)
- Patients are not deliberately deduplicated across splits in v1 (documented
  limitation — see §7), but the split logic in `train.py` is structured to
  support a patient-level split if required.

## 4. Modeling Approach

- **Primary algorithm:** LightGBM `LGBMClassifier` (gradient-boosted decision
  trees), with XGBoost (`XGBClassifier`) as a configurable alternative —
  selected via `configs/train_config.yaml: model.algorithm`.
- **Class imbalance:** Readmission is a minority class; handled via
  `scale_pos_weight` / `is_unbalance` and evaluated primarily with PR-AUC
  rather than accuracy.
- **Categorical handling:** Native categorical support (LightGBM) or one-hot
  encoding (XGBoost path), implemented in
  [`src/ml_pipeline/train.py`](../src/ml_pipeline/train.py).

## 5. Hyperparameter Tuning

[`src/ml_pipeline/hyperparameter_tuning.py`](../src/ml_pipeline/hyperparameter_tuning.py)
defines an Azure ML **Sweep job** over:

| Hyperparameter | Search space |
|---|---|
| `num_leaves` | `choice(15, 31, 63, 127)` |
| `learning_rate` | `loguniform(-4, -1)` |
| `n_estimators` | `choice(100, 300, 500)` |
| `min_child_samples` | `choice(10, 20, 50)` |
| `feature_fraction` | `uniform(0.6, 1.0)` |

- **Sampling:** Bayesian sampling (`BanditPolicy` early termination)
- **Primary metric:** validation PR-AUC (maximize)
- **Budget:** configurable `max_total_trials` / `max_concurrent_trials`

## 6. Evaluation

Implemented in [`src/ml_pipeline/evaluate.py`](../src/ml_pipeline/evaluate.py):

- **Discrimination:** ROC-AUC, PR-AUC
- **Operating point metrics:** Precision, Recall, F1, Specificity at
  configurable decision thresholds (default 0.5 and a clinically-tuned
  threshold maximizing recall at precision >= 0.3)
- **Calibration:** Reliability diagram bins + Brier score; a model with poor
  calibration is flagged even if AUC is acceptable, since care teams rely on
  the *probability* to prioritize outreach
- **Output:** `metrics.json` with all the above, persisted alongside the model
  artifact and attached to the registered model as tags/metadata

### Promotion Gate

A trained model is eligible for registration/promotion only if **all** hold on
the held-out test set:

| Metric | Threshold |
|---|---|
| ROC-AUC | >= 0.70 |
| PR-AUC | >= 0.35 |
| Brier score | <= 0.20 |
| Fairness: equalized odds difference (sex, age_band, ethnicity) | <= 0.10 |

These thresholds are encoded in `configs/train_config.yaml` and enforced in
`evaluate.py` / `register_model.py`.

## 7. Responsible AI Methodology

See [responsible-ai-report.md](responsible-ai-report.md) for the full report
template and findings format. Summary of methods used:

- **Explainability (`shap_explainability.py`):** `shap.TreeExplainer` produces
  global feature importance (mean |SHAP|) and per-prediction explanations
  surfaced via the API (`top_factors` field).
- **Fairness (`fairness_metrics.py`):** `fairlearn.metrics.MetricFrame` computes
  selection rate, FPR, FNR, and TPR by group for `sex`, `age_band`,
  `ethnicity`; demographic parity difference and equalized odds difference are
  reported.
- **Error analysis (`error_analysis.py`):** Confusion-matrix breakdown and
  error rates per cohort slice; flags slices with sample size >= 30 and error
  rate significantly above the global rate.

## 8. Known Limitations

- Synthetic data generator approximates realistic distributions but does not
  capture true clinical correlations — retrain on real (de-identified, IRB
  approved) data before production use.
- Train/val/test split is temporal but not strictly patient-disjoint;
  patient-level grouping should be added if patients commonly have multiple
  encounters spanning the split boundary.
- `ethnicity` is treated as optional at inference time to avoid requiring
  collection of sensitive attributes for scoring; it is used only in offline
  fairness audits during training.
