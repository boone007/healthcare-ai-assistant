# Architecture Overview

## 1. Purpose

This document describes the end-to-end architecture of the AI-Powered
Personalized Healthcare Assistant: a system that ingests patient encounter
data, validates and transforms it into features, trains and evaluates a
30-day hospital readmission risk model, audits the model for responsible AI
concerns, registers and deploys the model behind a secured API, and
continuously monitors it in production.

## 2. Logical Architecture

```mermaid
flowchart TB
    subgraph Sources
        A1[(EHR System)]
        A2[(Claims System)]
    end

    subgraph DataPlatform["Data Platform (Azure)"]
        ADF[Azure Data Factory\nPipelines]
        RAW[(ADLS Gen2\nraw/)]
        GE[Great Expectations\nValidation Suite]
        TRANSFORM[Feature Engineering\n(src/data_pipeline)]
        CURATED[(ADLS Gen2\ncurated/ - Feature Store)]
    end

    subgraph MLPlatform["Azure ML Workspace"]
        PIPE[AML Pipeline\n(pipeline_definition.yml)]
        TRAIN[train.py\nLightGBM/XGBoost]
        SWEEP[Hyperparameter\nSweep Job]
        EVAL[evaluate.py]
        RAI[responsible_ai/*\nSHAP, Fairness, Errors]
        MR[(Model Registry)]
    end

    subgraph Serving
        EP[Managed Online\nEndpoint]
        SCORE[score.py]
        FUNC[Azure Function\nHTTP API + AAD]
    end

    subgraph Ops["Cross-Cutting"]
        KV[(Key Vault)]
        AI[(Application Insights)]
        MON[Drift Detection\nJobs]
        ALERTS[Azure Monitor\nAlert Rules]
    end

    A1 --> ADF
    A2 --> ADF
    ADF --> RAW --> GE --> TRANSFORM --> CURATED --> PIPE
    PIPE --> TRAIN --> SWEEP --> EVAL --> RAI --> MR
    MR --> EP --> SCORE
    EP --> FUNC
    FUNC -->|secrets| KV
    PIPE -->|secrets| KV
    FUNC --> AI
    EP --> AI
    CURATED --> MON
    EP --> MON
    MON --> AI --> ALERTS
```

## 3. Component Inventory

| Layer | Component | Implementation |
|---|---|---|
| Ingestion | Simulated/ADF ingestion | [`src/data_pipeline/ingest.py`](../src/data_pipeline/ingest.py) |
| Validation | Great Expectations suite | [`src/data_pipeline/validate.py`](../src/data_pipeline/validate.py), [`src/data_pipeline/great_expectations/`](../src/data_pipeline/great_expectations) |
| Feature Engineering | Pandas-based transforms | [`src/data_pipeline/transform.py`](../src/data_pipeline/transform.py), [`src/data_pipeline/feature_engineering.py`](../src/data_pipeline/feature_engineering.py) |
| Feature Store | ADLS-backed feature interface | [`src/data_pipeline/feature_store.py`](../src/data_pipeline/feature_store.py) |
| Training | LightGBM/XGBoost training | [`src/ml_pipeline/train.py`](../src/ml_pipeline/train.py) |
| Hyperparameter Tuning | AML Sweep job | [`src/ml_pipeline/hyperparameter_tuning.py`](../src/ml_pipeline/hyperparameter_tuning.py) |
| Evaluation | AUC, PR, calibration | [`src/ml_pipeline/evaluate.py`](../src/ml_pipeline/evaluate.py) |
| Responsible AI | SHAP, fairness, error analysis | [`src/ml_pipeline/responsible_ai/`](../src/ml_pipeline/responsible_ai) |
| Registration | AML Model Registry | [`src/ml_pipeline/register_model.py`](../src/ml_pipeline/register_model.py) |
| Deployment | Managed Online Endpoint | [`src/deployment/aml_endpoint/`](../src/deployment/aml_endpoint) |
| Scoring | Inference script | [`src/deployment/scoring/score.py`](../src/deployment/scoring/score.py) |
| API | Azure Function w/ AAD | [`src/deployment/api/function_app/`](../src/deployment/api/function_app) |
| Monitoring | Drift detection, alerts | [`src/monitoring/`](../src/monitoring) |
| Infra | Terraform modules + envs | [`infra/terraform/`](../infra/terraform) |
| CI/CD | GitHub Actions | [`ci-cd/`](../ci-cd) |

## 4. Azure Resource Map

```mermaid
flowchart LR
    subgraph RG["rg-hcai-{env}"]
        VNET[vnet-hcai-{env}]
        ST[sthcai{env}001\nADLS Gen2]
        KV[kv-hcai-{env}]
        AI[appi-hcai-{env}]
        AML[mlw-hcai-{env}\nAML Workspace]
        CC[cpu-cluster-{env}\nCompute Cluster]
        EP[Managed Online Endpoint]
        FN[func-hcai-{env}]
    end
    VNET --- AML
    VNET --- ST
    AML --- CC
    AML --- EP
    AML --> KV
    AML --> AI
    AML --> ST
    FN --> AML
    FN --> KV
    FN --> AI
```

Resource naming follows the convention `<resource-prefix>-hcai-<env>` (or
storage-account-safe variants), defined centrally in
[`infra/terraform/envs/*/variables.tf`](../infra/terraform/envs).

## 5. Environments

| Environment | Purpose | Compute SKU | Endpoint traffic |
|---|---|---|---|
| `dev` | Development & experimentation | `Standard_DS3_v2`, 0-2 nodes | Manual testing only |
| `prod` | Production inference | `Standard_DS4_v2`, 1-4 nodes | 100% to latest approved deployment |

## 6. Security & Compliance Notes

- All secrets (storage keys, AAD client secrets, AML keys) are stored in
  **Azure Key Vault** and referenced via managed identity — never hard-coded.
- The Azure Function API requires **Azure AD (Entra ID)** token authentication
  (see [api-design.md](api-design.md)).
- Storage accounts use private endpoints / VNet service endpoints in `prod`
  (see [`infra/terraform/modules/networking`](../infra/terraform/modules/networking)).
- All PHI-like fields in example data are **synthetic placeholders** — no real
  patient data is used or required to run this repository.
