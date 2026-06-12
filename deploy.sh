#!/usr/bin/env bash
#
# deploy.sh - manual end-to-end deploy helper for the Healthcare AI Assistant.
#
# Mirrors the steps automated by ci-cd/cd-infra.yml and ci-cd/cd-ml.yml for
# ad-hoc local runs: provision infrastructure, submit the AML training
# pipeline, roll out the managed online endpoint, and (optionally) publish
# the Azure Function API. Azure resource names follow the "hcai" convention
# defined in infra/terraform/envs/$ENV/main.tf and src/deployment/aml_endpoint/.
#
# Usage:
#   ./deploy.sh [-e dev|prod] [--with-infra] [--with-function-app] [--skip-pipeline]
#
# Examples:
#   ./deploy.sh                                 # dev: submit pipeline + roll out endpoint
#   ./deploy.sh -e dev --with-infra             # dev: terraform apply, then pipeline + endpoint
#   ./deploy.sh -e prod --with-function-app     # prod: pipeline + endpoint + function app
#
# Requires: az CLI (logged in via `az login`), the `ml` az extension,
# terraform (if --with-infra), and the Azure Functions Core Tools `func`
# (if --with-function-app).

set -euo pipefail

ENV="dev"
WITH_INFRA=false
WITH_FUNCTION_APP=false
SKIP_PIPELINE=false

usage() {
  grep '^#' "$0" | sed -e 's/^#//' -e 's/^ //'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)
      ENV="$2"
      shift 2
      ;;
    --with-infra)
      WITH_INFRA=true
      shift
      ;;
    --with-function-app)
      WITH_FUNCTION_APP=true
      shift
      ;;
    --skip-pipeline)
      SKIP_PIPELINE=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
  esac
done

if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "ENV must be 'dev' or 'prod' (got: $ENV)" >&2
  exit 1
fi

RESOURCE_GROUP="rg-hcai-${ENV}"
WORKSPACE="mlw-hcai-${ENV}"
ENDPOINT_NAME="ep-hcai-readmission-${ENV}"
FUNCTION_APP="func-hcai-${ENV}"

log() {
  printf '[deploy] %s\n' "$1"
}

confirm() {
  local prompt="$1"
  read -r -p "$prompt [y/N] " reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Aborted." >&2; exit 1 ;;
  esac
}

log "Target environment: ${ENV} (resource group: ${RESOURCE_GROUP}, workspace: ${WORKSPACE})"

if [[ "$ENV" == "prod" ]]; then
  confirm "This will deploy to PRODUCTION (${RESOURCE_GROUP}/${WORKSPACE}). Continue?"
fi

if ! az account show > /dev/null 2>&1; then
  echo "Not logged in to Azure CLI. Run 'az login' first." >&2
  exit 1
fi

az extension add -n ml -y > /dev/null 2>&1 || true

# --------------------------------------------------------------------------
# 1. Infrastructure (optional)
# --------------------------------------------------------------------------
if [[ "$WITH_INFRA" == true ]]; then
  log "Applying Terraform configuration for envs/${ENV}..."
  pushd "infra/terraform/envs/${ENV}" > /dev/null
  terraform init -input=false
  terraform plan -input=false -out=tfplan
  terraform apply -input=false tfplan
  popd > /dev/null
else
  log "Skipping infrastructure (pass --with-infra to run terraform apply)."
fi

# --------------------------------------------------------------------------
# 2. AML training pipeline (validate -> transform -> train -> evaluate ->
#    responsible AI -> register, gated by the promotion gate)
# --------------------------------------------------------------------------
if [[ "$SKIP_PIPELINE" == true ]]; then
  log "Skipping AML pipeline submission (--skip-pipeline)."
else
  log "Submitting AML training pipeline (src/ml_pipeline/pipeline_definition.yml)..."
  JOB_NAME=$(az ml job create \
    --file src/ml_pipeline/pipeline_definition.yml \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$WORKSPACE" \
    --query name -o tsv)
  log "Submitted pipeline job: ${JOB_NAME}"

  log "Streaming pipeline job logs..."
  az ml job stream \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$WORKSPACE"

  STATUS=$(az ml job show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$WORKSPACE" \
    --query status -o tsv)
  log "Pipeline job status: ${STATUS}"

  if [[ "$STATUS" != "Completed" ]]; then
    echo "Pipeline job did not complete successfully (status=${STATUS})." >&2
    echo "If the failure occurred in the register_model step, this likely" >&2
    echo "means the responsible AI promotion gate rejected the candidate" >&2
    echo "model. See docs/responsible-ai-report.md and the job's" >&2
    echo "register_model logs for details." >&2
    exit 1
  fi
fi

# --------------------------------------------------------------------------
# 3. Managed online endpoint rollout
# --------------------------------------------------------------------------
log "Ensuring managed online endpoint exists (${ENDPOINT_NAME})..."
az ml online-endpoint create \
  --file src/deployment/aml_endpoint/endpoint.yml \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE" \
  || log "Endpoint already exists, continuing."

log "Deploying latest registered model to the 'blue' deployment (--all-traffic)..."
az ml online-deployment create \
  --file src/deployment/aml_endpoint/deployment.yml \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE" \
  --all-traffic

log "Smoke testing the endpoint with sample_request.json..."
az ml online-endpoint invoke \
  --name "$ENDPOINT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE" \
  --request-file src/deployment/aml_endpoint/sample_request.json

# --------------------------------------------------------------------------
# 4. Azure Function API (optional)
# --------------------------------------------------------------------------
if [[ "$WITH_FUNCTION_APP" == true ]]; then
  log "Publishing Azure Function API (${FUNCTION_APP})..."
  pushd src/deployment/api/function_app > /dev/null
  func azure functionapp publish "$FUNCTION_APP" --python
  popd > /dev/null
else
  log "Skipping Azure Function API publish (pass --with-function-app to publish)."
fi

log "Deploy complete for environment: ${ENV}"
