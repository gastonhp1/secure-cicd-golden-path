SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

APP        ?= demo-api
APP_DIR    := apps/$(APP)
IMAGE      ?= $(APP):local
VENV       := .venv
PY         := $(VENV)/bin

##@ App (local)
.PHONY: venv test lint run image scan
venv: ## Create a virtualenv with the app and dev tools
	python3 -m venv $(VENV)
	$(PY)/pip install -q -e '$(APP_DIR)[dev]'

test: ## Run the test suite with coverage
	cd $(APP_DIR) && ../../$(PY)/pytest

lint: ## ruff + mypy
	cd $(APP_DIR) && ../../$(PY)/ruff check . && ../../$(PY)/ruff format --check . && ../../$(PY)/mypy

run: ## Run the app with reload on http://localhost:8080
	cd $(APP_DIR) && ../../$(PY)/uvicorn demo_api.main:app --reload --port 8080

image: ## Build the container image locally
	docker build -t $(IMAGE) --build-arg APP_VERSION=local --build-arg GIT_SHA=$$(git rev-parse --short HEAD) $(APP_DIR)

scan: image ## Same blocking gate CI uses
	trivy image --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 $(IMAGE)

##@ Supply chain
.PHONY: verify
verify: ## Verify a published image: make verify REF=ghcr.io/gastonhp1/demo-api@sha256:...
	@test -n "$(REF)" || { echo "set REF=<image@digest>"; exit 1; }
	cosign verify $(REF) \
	  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
	  --certificate-identity-regexp '^https://github.com/gastonhp1/secure-cicd-golden-path/.github/workflows/reusable-container.yml@refs/(heads/main|tags/v.*)$$' \
	  | jq '.[0].optional | {Issuer, Subject, githubWorkflowRef: .githubWorkflowRef}'
	cosign verify-attestation $(REF) --type spdxjson \
	  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
	  --certificate-identity-regexp '^https://github.com/gastonhp1/secure-cicd-golden-path/' >/dev/null && echo "SBOM attestation: OK"
	gh attestation verify oci://$(REF) --owner gastonhp1 && echo "SLSA provenance: OK"

##@ Pipeline
.PHONY: lint-workflows
lint-workflows: ## actionlint + zizmor on .github/workflows
	actionlint
	zizmor --min-severity medium .github/workflows

.PHONY: help
help:
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
