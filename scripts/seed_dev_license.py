"""Seed a local development license — fully unlocks every feature for testing.

Usage:
    python scripts/seed_dev_license.py                  # mint a fresh random key
    python scripts/seed_dev_license.py --key BHE-XXXX-XXXX-XXXX-XXXX  # use a specific key

What it does:
  1. Marks the local Setup Wizard as complete (so the app boots straight
     into the dashboard).
  2. Activates every premium + standalone feature flag in
     `backend/native/system_config.json` (story_generator, music_bingo,
     karaoke, sharepoint, bingo_story, karaoke_story).
  3. Stamps the cloud-snapshot fields (`owns_standalone`,
     `owns_music_bingo`, `owns_karaoke`, `cloud_library_active`,
     `cloud_library_expires_at`) and `last_cloud_validated_at = now`
     so the 30-day offline grace passes cleanly without needing
     `api.bighat.live` to be reachable.
  4. Prints the seeded key.

Designed for the preview pod and for the desktop installer's
`backend/native/system_config.json` (drop in place + restart).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "backend" / "native" / "system_config.json"


def _generate_key() -> str:
    sys.path.insert(0, str(ROOT / "backend"))
    from cloud.license_service import generate_key
    return generate_key()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="Use a specific key (else mint a random one)")
    ap.add_argument("--email", default="dev@bighat.local",
                    help="Master admin email to record on the seed")
    ap.add_argument("--config", default=str(CONFIG_PATH),
                    help="Path to system_config.json (default: backend/native/)")
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[seed] config not found at {config_path}", file=sys.stderr)
        return 1

    key = args.key or _generate_key()
    cfg = json.loads(config_path.read_text())
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_iso = (now + timedelta(days=365 * 5)).isoformat()

    cfg["setup_complete"] = True
    cfg["updated_at"] = now_iso
    cfg.setdefault("settings", {})
    cfg["settings"].setdefault("company_name", "BIG Hat Entertainment")

    cfg["license_status"] = {
        "key": key,
        "master_admin_email": args.email,
        "total_seats_allowed": 5,
        "active_seats": cfg.get("license_status", {}).get("active_seats", []),
        "is_active": True,
    }

    cfg["subscription"] = {
        "active": True,
        "tier": "premium",
        "expires_at": expires_iso,
        "last_check": now_iso,
        "last_cloud_validated_at": now_iso,
        # Standalone ownership flags (Phase 10.4)
        "owns_standalone": True,
        "owns_music_bingo": True,
        "owns_karaoke": True,
        "cloud_library_active": True,
        "cloud_library_expires_at": expires_iso,
        # Feature flags
        "sharepoint_enabled": True,
        "story_generator_enabled": True,
        "music_bingo_enabled": True,
        "karaoke_enabled": True,
        "bingo_story_enabled": True,
        "karaoke_story_enabled": True,
        "pending_cloud_activation": False,
    }

    config_path.write_text(json.dumps(cfg, indent=2))

    print("=" * 60)
    print("DEV LICENSE SEEDED")
    print("=" * 60)
    print(f"  Key:          {key}")
    print(f"  Master admin: {args.email}")
    print(f"  Expires:      {expires_iso}")
    print(f"  Config:       {config_path}")
    print()
    print("All features unlocked: standalone, music_bingo, karaoke,")
    print("cloud library, story generator, sharepoint, bingo_story,")
    print("karaoke_story.")
    print()
    print("Now restart the backend: sudo supervisorctl restart backend")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
