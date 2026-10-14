# Design notes

## Why reusable workflows (and not composite actions)

Composite actions are steps; reusable workflows are **jobs**, with their own
`permissions`, `environment`, runners and concurrency. That matters here:

- `reusable-container` needs `id-token: write` and `packages: write`, but the caller's CI job
  should not have them. Permissions are declared per job, so they cannot leak to unrelated steps.
- Sigstore keyless certificates record the workflow that requested the token. For a reusable
  workflow that is the reusable file itself (`job_workflow_ref`), so the cluster can trust
  *this pipeline* rather than *any job in the org*.

## Why scan before push

The usual order is build → push → scan. If the scan then fails, a vulnerable image already sits
in the registry with a tag someone can deploy. Here the scan runs on a local single-arch build;
only if it passes is the multi-arch image built (from cache) and pushed. Combined with
signature verification in the cluster, an image that never passed the gate cannot run.

Trade-off: the arm64 variant is not scanned separately. Both variants come from the same
Dockerfile and base image tag, and OS package versions match across arches in Debian; the
scheduled rescan (roadmap) covers drift.

## Why digests in Git

`values-<env>.yaml` holds `image.digest`. Argo CD diffs show the exact artifact; rollback is
`git revert`; a re-pushed tag cannot change what runs. Kyverno additionally runs with
`mutateDigest: true`, so even a tag-only reference gets pinned at admission.

## Why a GitHub App instead of a PAT

A PAT belongs to a person, usually has broad scopes and lives until someone remembers to
rotate it. The App token is minted per run, expires in an hour and is limited to two
permissions on one repository. The App private key is the single secret in this design;
it can be rotated without touching any workflow.

## Promotion flow per environment

```
environment: dev     subject repo:gastonhp1/secure-cicd-golden-path:environment:dev
  └─ Azure identity id-platform-dev-github-ci  → AcrPush on acr…dev only
environment: prod    subject …:environment:prod   (required reviewers, tags v* only)
  └─ Azure identity id-platform-prod-github-ci → AcrPush on acr…prod only
```

A compromised dev job cannot push to prod: the token subject does not match prod's
federated credential, so Entra ID refuses the exchange.
