#!/usr/bin/env bash
# Standalone alternative to the Terraform in azure-aks-gitops-platform:
# creates a user-assigned managed identity that GitHub Actions can assume via OIDC
# (no client secret), trusted only for one GitHub environment, with AcrPush on one ACR.
#
# Usage:
#   scripts/setup-azure-oidc.sh <resource-group> <acr-name> <github-environment>
# Example:
#   scripts/setup-azure-oidc.sh rg-platform-dev acrplatformdevghp01 dev
set -euo pipefail

RG="${1:?resource group}"
ACR_NAME="${2:?acr name}"
GH_ENV="${3:?github environment (dev|prod)}"
REPO="${GITHUB_REPO:-gastonhp1/secure-cicd-golden-path}"
IDENTITY="id-github-ci-${GH_ENV}"

command -v az >/dev/null || { echo "az CLI is required" >&2; exit 1; }

echo ">> identity $IDENTITY in $RG"
az identity create -g "$RG" -n "$IDENTITY" -o none
CLIENT_ID=$(az identity show -g "$RG" -n "$IDENTITY" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -g "$RG" -n "$IDENTITY" --query principalId -o tsv)

echo ">> federated credential for repo:$REPO:environment:$GH_ENV"
az identity federated-credential create \
  -g "$RG" --identity-name "$IDENTITY" \
  -n "github-${GH_ENV}" \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${REPO}:environment:${GH_ENV}" \
  --audiences api://AzureADTokenExchange \
  -o none

ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
echo ">> AcrPush on $ACR_NAME"
# New principals can take a few seconds to replicate in Entra ID.
for i in 1 2 3 4 5; do
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
    --role AcrPush --scope "$ACR_ID" -o none && break
  echo "   waiting for identity replication ($i)..."; sleep 10
done

cat <<EOF

Done. In GitHub → Settings → Environments → ${GH_ENV} → Variables:

  AZURE_CLIENT_ID       = ${CLIENT_ID}
  AZURE_TENANT_ID       = $(az account show --query tenantId -o tsv)
  AZURE_SUBSCRIPTION_ID = $(az account show --query id -o tsv)
  ACR_LOGIN_SERVER      = $(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
EOF
