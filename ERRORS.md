# Error Log

Append-only. Newest at top. Format:

```
## [YYYY-MM-DD HH:MM] PHASE / FILE — error summary
**What happened:** ...
**Root cause:** ...
**Resolution:** ...
**Verified:** how / by what test / by what observation
```

---

## [2026-05-04 06:17] P0.5 / playwright test harness — CORS preflight blocks credentialed XHR
**What happened:** When running the wizard E2E test from `http://localhost:3000` against backend URL `https://standalone-tools.preview.emergentagent.com`, login form showed "Something went wrong. Please try again." Console log: `Access-Control-Allow-Origin must not be the wildcard '*' when credentials mode is 'include'`.
**Root cause:** Frontend uses `axios` with `withCredentials: true` for cookie-based auth. Backend's CustomCORSMiddleware echoes the Origin header, but the kubernetes ingress + nginx-code-proxy in front of the backend overrides the response with `Access-Control-Allow-Origin: *`. Browsers reject `*` when credentials are included. **NOT a real bug** — only manifests in cross-origin browser test harnesses. Real native standalone runs frontend & backend on same `localhost:8001` origin (Edge `--app=http://localhost:8001/`), no CORS preflight occurs.
**Resolution:** No code change needed. Re-ran the same E2E test from same-origin preview URL `https://standalone-tools.preview.emergentagent.com/` → all calls 200, login + dashboard worked perfectly.
**Verified:** `auto-frontend test` log shows `✓ /api/auth/me: {"status": 200, "body": {"role": "master_admin", ...}}`; dashboard screenshot shows badge "Native • 1/5" + role "Master Admin".

## [2026-05-04 06:14] P0.5 / SetupWizard — success screen flash + auto-redirect
**What happened:** Submit on step 3 succeeded server-side (master admin + license created), but the success screen rendered for one frame then user landed on `/login`. Test selector `text=All Set Up` timed out.
**Root cause:** `handleSubmit` called `setSuccess(data); await refresh();`. `refresh()` updated NativeContext.setupComplete=true. `<NativeGate>` then hit `if (nativeMode && setupComplete && location.pathname === '/setup') return <Navigate to="/login">` and redirected mid-render before success screen could mount.
**Resolution:** Removed `await refresh()` from `handleSubmit`. Moved it into the "Continue to Login" button handler so it runs *while* navigating to a path that doesn't trigger the redirect. Success screen now renders until user clicks the button.
**Verified:** Re-ran E2E flow → Playwright `wait_for_selector('text=All Set Up')` resolved within 1s; user clicks Continue → redirected to /login as expected.

## [2026-05-04 06:02] P0 / backend/native/router.py — EmailStr rejected `.local` TLD
**What happened:** First setup-initialize call with `master@bighat.local` returned 422 with detail `"value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email."`
**Root cause:** `pydantic.EmailStr` (backed by `email-validator`) blocks IANA special-use TLDs (`.local`, `.test`, `.example`, `.invalid`). Native standalone is offline-first and the master admin commonly uses such emails.
**Resolution:** Replaced `EmailStr` with `str + field_validator` using regex `^[^\s@]+@[^\s@]+\.[^\s@]+$`. Lowercase + strip during validation.
**Verified:** `POST /api/native/setup/initialize` with `master@bighat.local` now returns 200; `setup_complete=true` and seat registered.
