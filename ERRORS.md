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

## [2026-05-04 06:02] P0 / backend/native/router.py — EmailStr rejected `.local` TLD
**What happened:** First setup-initialize call with `master@bighat.local` returned 422 with detail `"value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email."`
**Root cause:** `pydantic.EmailStr` (backed by `email-validator`) blocks IANA special-use TLDs (`.local`, `.test`, `.example`, `.invalid`). Native standalone is offline-first and the master admin commonly uses such emails.
**Resolution:** Replaced `EmailStr` with `str + field_validator` using regex `^[^\s@]+@[^\s@]+\.[^\s@]+$`. Lowercase + strip during validation.
**Verified:** `POST /api/native/setup/initialize` with `master@bighat.local` now returns 200; `setup_complete=true` and seat registered.
