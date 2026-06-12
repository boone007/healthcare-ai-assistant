# Makefile for the AI-Powered Personalized Healthcare Assistant
#
# Convenience targets that wrap the commands documented in README.md
# (sections 4.4-4.7) and the CI/CD workflows under ci-cd/. Azure resource
# names follow the "hcai" naming convention defined in
# infra/terraform/envs/$(ENV)/main.tf and src/deployment/aml_endpoint/.
#
# Override defaults on the command line, e.g.:
#   make ENV=prod tf-plan
#   make aml-pipeline-submit ENV=prod

ENV ?= dev
PYTHON ?= python3

RESOURCE_GROUP ?= rg-hcai-$(ENV)
WORKSPACE ?= mlw-hcai-$(ENV)
ENDPOINT_NAME ?= ep-hcai-readmission-$(ENV)
FUNCTION_APP ?= func-hcai-$(ENV)

DATA_DIR ?= data
OUTPUT_DIR ?= outputs

.PHONY: help install lint format type-check \
	test test-integration test-performance test-all \
	ingest validate transform data train evaluate \
	shap fairness error-analysis responsible-ai register \
	tf-init tf-plan tf-apply tf-destroy \
	aml-pipeline-submit aml-endpoint-create aml-deployment-create aml-endpoint-invoke \
	monitoring-data-drift monitoring-model-drift \
	func-deploy clean

help:
	@echo "Healthcare AI Assistant - common developer tasks (ENV=$(ENV))"
	@echo ""
	@echo "  install               Install Python dependencies"
	@echo "  lint                  Run ruff and black --check"
	@echo "  format                Run ruff --fix and black"
	@echo "  type-check            Run mypy on src/"
	@echo "  test                  Run unit tests"
	@echo "  test-integration      Run integration tests"
	@echo "  test-performance      Run performance (scoring latency) tests"
	@echo "  test-all              Run the full test suite"
	@echo ""
	@echo "  data                  Run ingest -> validate -> transform locally"
	@echo "  train                 Train the model (depends on data)"
	@echo "  evaluate              Evaluate the trained model"
	@echo "  responsible-ai        Run SHAP, fairness, and error-analysis"
	@echo "  register              Register the model (promotion gate enforced)"
	@echo ""
	@echo "  tf-plan               Terraform init + plan for envs/$(ENV)"
	@echo "  tf-apply              Terraform apply the saved plan for envs/$(ENV)"
	@echo "  tf-destroy            Terraform destroy envs/$(ENV) (use with care)"
	@echo ""
	@echo "  aml-pipeline-submit   Submit the AML training pipeline ($(WORKSPACE))"
	@echo "  aml-endpoint-create   Create the managed online endpoint ($(ENDPOINT_NAME))"
	@echo "  aml-deployment-create Create/update the 'blue' deployment (--all-traffic)"
	@echo "  aml-endpoint-invoke   Smoke test the endpoint with sample_request.json"
	@echo ""
	@echo "  monitoring-data-drift Run PSI-based data drift detection"
	@echo "  monitoring-model-drift Run prediction/AUC drift detection"
	@echo ""
	@echo "  func-deploy           Publish the Azure Function API ($(FUNCTION_APP))"
	@echo "  clean                 Remove caches, coverage, and local outputs"

# --------------------------------------------------------------------------
# Local dev / CI
# --------------------------------------------------------------------------

install:
	pip install -r requirements.txt

lint:
	ruff check src tests
	black --check src tests

format:
	ruff check --fix src tests
	black src tests

type-check:
	mypy src

test:
	pytest tests/unit

test-integration:
	pytest tests/integration

test-performance:
	pytest tests/performance -m performance

test-all:
	pytest tests

# --------------------------------------------------------------------------
# Data pipeline (src/data_pipeline)
# --------------------------------------------------------------------------

ingest:
	$(PYTHON) -m src.data_pipeline.ingest --output $(DATA_DIR)/raw/encounters.csv

validate:
	$(PYTHON) -m src.data_pipeline.validate --input $(DATA_DIR)/raw/encounters.csv

transform:
	$(PYTHON) -m src.data_pipeline.transform \
		--input $(DATA_DIR)/raw/encounters.csv \
		--output $(DATA_DIR)/processed/features.parquet

data: ingest validate transform

# --------------------------------------------------------------------------
# ML pipeline (src/ml_pipeline) - local runs
# --------------------------------------------------------------------------

train:
	$(PYTHON) -m src.ml_pipeline.train \
		--data $(DATA_DIR)/processed/features.parquet \
		--config configs/train_config.yaml \
		--output-dir $(OUTPUT_DIR)

evaluate:
	$(PYTHON) -m src.ml_pipeline.evaluate \
		--model-path $(OUTPUT_DIR)/model.pkl \
		--data $(OUTPUT_DIR)/test.parquet \
		--config configs/train_config.yaml \
		--output $(OUTPUT_DIR)/metrics.json

shap:
	$(PYTHON) -m src.ml_pipeline.responsible_ai.shap_explainability \
		--model-path $(OUTPUT_DIR)/model.pkl \
		--data $(OUTPUT_DIR)/test.parquet \
		--output $(OUTPUT_DIR)/responsible_ai/shap_report.json

fairness:
	$(PYTHON) -m src.ml_pipeline.responsible_ai.fairness_metrics \
		--model-path $(OUTPUT_DIR)/model.pkl \
		--data $(OUTPUT_DIR)/test.parquet \
		--output $(OUTPUT_DIR)/responsible_ai/fairness_report.json

error-analysis:
	$(PYTHON) -m src.ml_pipeline.responsible_ai.error_analysis \
		--model-path $(OUTPUT_DIR)/model.pkl \
		--data $(OUTPUT_DIR)/test.parquet \
		--output $(OUTPUT_DIR)/responsible_ai/error_analysis.json

responsible-ai: shap fairness error-analysis

register:
	$(PYTHON) -m src.ml_pipeline.register_model \
		--model-path $(OUTPUT_DIR)/model.pkl \
		--metrics $(OUTPUT_DIR)/metrics.json \
		--fairness-report $(OUTPUT_DIR)/responsible_ai/fairness_report.json \
		--model-name readmission-risk-model \
		--subscription-id $(SUBSCRIPTION_ID) \
		--resource-group $(RESOURCE_GROUP) \
		--workspace-name $(WORKSPACE)

# --------------------------------------------------------------------------
# Infrastructure (infra/terraform/envs/$(ENV))
# --------------------------------------------------------------------------

tf-init:
	cd infra/terraform/envs/$(ENV) && terraform init

tf-plan: tf-init
	cd infra/terraform/envs/$(ENV) && terraform plan -out=tfplan

tf-apply:
	cd infra/terraform/envs/$(ENV) && terraform apply tfplan

tf-destroy:
	cd infra/terraform/envs/$(ENV) && terraform destroy

# --------------------------------------------------------------------------
# Azure ML pipeline + managed online endpoint
# --------------------------------------------------------------------------

aml-pipeline-submit:
	az ml job create \
		--file src/ml_pipeline/pipeline_definition.yml \
		--resource-group $(RESOURCE_GROUP) \
		--workspace-name $(WORKSPACE)

aml-endpoint-create:
	az ml online-endpoint create \
		-f src/deployment/aml_endpoint/endpoint.yml \
		--resource-group $(RESOURCE_GROUP) \
		--workspace-name $(WORKSPACE)

aml-deployment-create:
	az ml online-deployment create \
		-f src/deployment/aml_endpoint/deployment.yml \
		--resource-group $(RESOURCE_GROUP) \
		--workspace-name $(WORKSPACE) \
		--all-traffic

aml-endpoint-invoke:
	az ml online-endpoint invoke \
		--name $(ENDPOINT_NAME) \
		--resource-group $(RESOURCE_GROUP) \
		--workspace-name $(WORKSPACE) \
		--request-file src/deployment/aml_endpoint/sample_request.json

# --------------------------------------------------------------------------
# Monitoring (src/monitoring)
# --------------------------------------------------------------------------

monitoring-data-drift:
	$(PYTHON) -m src.monitoring.data_drift_detection \
		--baseline $(OUTPUT_DIR)/train.parquet \
		--current $(DATA_DIR)/monitoring/recent_scoring_inputs.parquet \
		--output $(OUTPUT_DIR)/monitoring/drift_report.json

monitoring-model-drift:
	$(PYTHON) -m src.monitoring.model_drift_detection \
		--baseline-predictions $(OUTPUT_DIR)/monitoring/baseline_predictions.parquet \
		--current-predictions $(DATA_DIR)/monitoring/recent_predictions.parquet \
		--output $(OUTPUT_DIR)/monitoring/model_drift_report.json

# --------------------------------------------------------------------------
# Azure Function API (src/deployment/api/function_app)
# --------------------------------------------------------------------------

func-deploy:
	cd src/deployment/api/function_app && func azure functionapp publish $(FUNCTION_APP) --python

# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
