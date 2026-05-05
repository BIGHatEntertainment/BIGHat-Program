"""BIG Hat Standalone — Cloud Licensing Service (Phase 10.0)

This package implements the cloud-side license authority that backs the
$24.99 one-time desktop purchase and the $5/month Cloud Library subscription.

All code here runs ONLY when `BIGHAT_CLOUD_MODE=1`. It is deliberately
excluded from the desktop `launcher.py` bundle via `BIGHAT_NATIVE_MODE=1`
so that shipped installers cannot accidentally expose licensing endpoints.

Module map:
  * `config`           — env-var surface + licensing constants
  * `license_models`   — Pydantic request/response & stored-record models
  * `license_store`    — MongoDB CRUD for `license_keys` / webhook events
  * `license_service`  — business logic: mint / activate / validate / revoke
  * `email_service`    — Resend wrapper, graceful no-op when key missing
  * `squarespace_webhook` — webhook signature + order dispatch
  * `license_router`   — public FastAPI routes (`/api/license/*`)
  * `admin_router`     — admin FastAPI routes (`/api/license/admin/*`)
"""
