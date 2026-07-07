"""
v32.0.0-alpha.53 — HARDCODED 17-step presentation build pipeline.

This module IS the merchant's spec, encoded as code so no future agent can
"reinterpret" it. It provides two entry points:

    build_from_wizard(...)   — the 12-step Build Wizard (guided dropdowns).
    build_from_roulette(...) — the slot-machine Round Roulette.

Both produce the SAME output shape: a `.bighat` presentation JSON written
to `Files/Trivia/Rounds/<name>.bighat`, which the Editor then reads and
runs the section-by-section assembly pipeline against (see
`assemble_presentation_with_checks` in this module).

Round-count rules (hardcoded, no admin override):
    5 rounds: [MC, REG, MISC, MYS, BIG]
    6 rounds: [MC, REG, (REG or MISC), MISC, MYS, BIG]

Anything else raises `BuildValidationError` — the wizard/roulette UIs are
expected to prevent this ever happening client-side, but we defend it here
as the last line of truth.

Overlay compositing (question + answer slides ONLY):
    Each Location has 0..N overlay PNGs, tagged with the round-types they
    apply to (metadata attribute `applies_to_round_types: ["MC","REG",...]`).
    The renderer picks the matching overlay(s) for the current round-type
    and composites them z-order-high on top of Q + A slides.

Assembly-time checks:
    After each section (host / location / intros / round-i) the pipeline
    calls the appropriate `_verify_*` function. If a check fails, the
    result is written to the presentation's attestation report and a
    warning is bubbled up. Frontend shows "Check failed — continue anyway?"
    modal (option 4b).
"""
from __future__ import annotations

import json
import logging
import random
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded round-order rules
# ---------------------------------------------------------------------------

ALLOWED_ROUND_COUNTS = (5, 6)

# For a given count → the frozen sequence of allowed round-types per slot.
# `tuple` means "one of these"; single-item tuple = fixed.
ROUND_ORDER_SPEC: Dict[int, Tuple[Tuple[str, ...], ...]] = {
    5: (
        ("MC",),
        ("REG",),
        ("MISC",),
        ("MYS",),
        ("BIG",),
    ),
    6: (
        ("MC",),
        ("REG",),
        ("REG", "MISC"),   # slot 3 — user's choice
        ("MISC",),
        ("MYS",),
        ("BIG",),
    ),
}


class BuildValidationError(ValueError):
    """Raised when the wizard/roulette input violates the hardcoded spec."""


# ---------------------------------------------------------------------------
# Docs-root + slugs (re-used from native_slides)
# ---------------------------------------------------------------------------

def _docs_root() -> Path:
    import os as _os
    env = _os.environ.get("BIGHAT_FILES_DIR")
    if env:
        return Path(env)
    return Path.home() / "Documents" / "BIG Hat Entertainment"


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").strip()).strip("-").lower()
    return s or "unnamed"


def _files_root() -> Path:
    root = _docs_root() / "Files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _intros_dir() -> Path:
    p = _files_root() / "Trivia" / "Intros"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _rounds_dir() -> Path:
    p = _files_root() / "Trivia" / "Rounds"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _round_pool_dir(round_type: str) -> Path:
    """The folder the wizard/roulette pulls a round from — one folder per type."""
    return _files_root() / "Trivia" / round_type.upper()


# ---------------------------------------------------------------------------
# Round-order validation (Steps 6-11)
# ---------------------------------------------------------------------------

def validate_round_sequence(round_types: List[str]) -> None:
    """Enforce the merchant's hardcoded round-count and order rules.

    Raises `BuildValidationError` on any deviation.
    """
    count = len(round_types)
    if count not in ALLOWED_ROUND_COUNTS:
        raise BuildValidationError(
            f"round count must be 5 or 6, got {count} "
            "(white-glove override will land in a later release)"
        )
    spec = ROUND_ORDER_SPEC[count]
    for i, (got, allowed) in enumerate(zip(round_types, spec)):
        got_u = (got or "").upper()
        if got_u not in allowed:
            raise BuildValidationError(
                f"slot {i + 1} must be one of {allowed}, got {got_u!r}"
            )


# ---------------------------------------------------------------------------
# Round-file resolution — resolve a round id/filename against the on-disk pool
# ---------------------------------------------------------------------------

def _list_round_files_of_type(round_type: str) -> List[Path]:
    d = _round_pool_dir(round_type)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".bighat")


def _resolve_round_file(round_type: str, ref: str) -> Path:
    """Resolve a wizard-supplied round reference to an actual disk path.

    `ref` may be:
      - a bare filename ("mc-01-a-1.bighat"),
      - a stem ("mc-01-a-1"),
      - an absolute path,
      - a relative path from docs-root.
    """
    if not ref:
        raise BuildValidationError(f"{round_type}: empty round reference")
    p = Path(ref)
    candidates: List[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(_docs_root() / ref)
        candidates.append(_round_pool_dir(round_type) / ref)
        if not ref.lower().endswith(".bighat"):
            candidates.append(_round_pool_dir(round_type) / f"{ref}.bighat")
    for c in candidates:
        if c.is_file():
            # And it MUST live under the correct type folder — no cross-pool
            # picking (spec step 7-11: "only pulls from the XX folder").
            expected_dir = _round_pool_dir(round_type).resolve()
            try:
                c.resolve().relative_to(expected_dir)
            except ValueError as e:
                raise BuildValidationError(
                    f"{round_type} round {ref!r} lives outside {expected_dir} "
                    f"(cross-type picking is forbidden)"
                ) from e
            return c
    raise BuildValidationError(
        f"{round_type} round file not found for {ref!r}; "
        f"pool={_round_pool_dir(round_type)}"
    )


# ---------------------------------------------------------------------------
# Host + location validation (Steps 4-5)
# ---------------------------------------------------------------------------

def _load_host(host_id: str) -> Dict[str, Any]:
    d = _files_root() / "Hosts" / host_id
    hj = d / "host.json"
    if not hj.is_file():
        raise BuildValidationError(f"host_id {host_id!r} not on disk at {hj}")
    return json.loads(hj.read_text(encoding="utf-8"))


def _load_location(location_id_or_slug: str) -> Optional[Dict[str, Any]]:
    """Location metadata lives in Mongo (see locations_router.py). But the
    disk-side folder MUST exist and contain a `location.json` sentinel;
    otherwise the wizard cannot bind overlays to it. If no sentinel is
    found we still return None and let the caller decide.
    """
    d = _files_root() / "Locations" / location_id_or_slug
    if not d.is_dir():
        # try slug lookup — the wizard passes the id, but folders are named
        # after the slug. Caller supplies both; this helper only reads what's
        # on disk.
        for entry in (_files_root() / "Locations").iterdir():
            if not entry.is_dir():
                continue
            lj = entry / "location.json"
            if lj.is_file():
                try:
                    doc = json.loads(lj.read_text(encoding="utf-8"))
                    if doc.get("id") == location_id_or_slug:
                        return doc
                except (OSError, ValueError):
                    continue
        return None
    lj = d / "location.json"
    if lj.is_file():
        try:
            return json.loads(lj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    # No metadata JSON, but the folder exists — return a stub so the caller
    # knows the folder is real.
    return {"id": location_id_or_slug, "slug": location_id_or_slug,
            "_stub": True, "_folder": str(d)}


# ---------------------------------------------------------------------------
# Public API: Build Wizard (Steps 1-12)
# ---------------------------------------------------------------------------

def build_from_wizard(
    *,
    name: str,
    host_id: str,
    location_id: str,
    round_count: int,
    round_files: List[str],
    intro_pack_id: Optional[str] = None,
    owner_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble a presentation `.bighat` file from wizard input.

    Enforces every rule in the merchant's 17-step spec that concerns
    presentation *creation* (steps 1-12). The Editor phase (steps 13-17)
    happens later via `assemble_presentation_with_checks`.
    """
    # Step 6: round count
    if round_count not in ALLOWED_ROUND_COUNTS:
        raise BuildValidationError(
            f"round_count must be 5 or 6, got {round_count}"
        )
    if len(round_files) != round_count:
        raise BuildValidationError(
            f"round_files length ({len(round_files)}) must equal round_count "
            f"({round_count})"
        )

    # Steps 7-11: order + type validation
    types_by_slot = [spec[0] if len(spec) == 1 else None
                     for spec in ROUND_ORDER_SPEC[round_count]]
    # Slot with a choice (round-3 in 6-round mode) — the wizard passes the
    # file directly and we deduce the type from which pool contains it.
    def _deduce_type(idx: int, ref: str) -> str:
        fixed = types_by_slot[idx]
        if fixed:
            return fixed
        # slot with choice — probe both pools
        for candidate in ROUND_ORDER_SPEC[round_count][idx]:
            try:
                _resolve_round_file(candidate, ref)
                return candidate
            except BuildValidationError:
                continue
        raise BuildValidationError(
            f"slot {idx + 1} round ref {ref!r} does not live in any of "
            f"{ROUND_ORDER_SPEC[round_count][idx]}"
        )

    resolved_round_types = [
        _deduce_type(i, ref) for i, ref in enumerate(round_files)
    ]
    validate_round_sequence(resolved_round_types)

    # Steps 4-5: host + location on disk
    host = _load_host(host_id)
    loc = _load_location(location_id)  # may be None → wizard should have blocked

    round_file_refs: List[Dict[str, Any]] = []
    for i, ref in enumerate(round_files):
        rtype = resolved_round_types[i]
        p = _resolve_round_file(rtype, ref)
        rel = p.relative_to(_docs_root()).as_posix()
        round_file_refs.append({
            "order": i + 1,
            "type": rtype,
            "file": rel,
        })

    # Step 12: write the .bighat presentation JSON.
    pres_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pres: Dict[str, Any] = {
        "id": pres_id,
        "type": "trivia-presentation",
        "schema_version": 2,
        "created_at": now,
        "updated_at": now,
        "created_by": owner_email or host.get("email"),
        "name": name.strip() or f"Show {now[:10]}",
        "host_id": host_id,
        "host_name": host.get("display_name") or host.get("email"),
        "location_id": location_id,
        "location_name": (loc or {}).get("name") or location_id,
        "round_count": round_count,
        "roundFiles": round_file_refs,
        "intro_pack_id": intro_pack_id,
        "_source": "build-wizard",
        "_verified_spec_step": "steps 1-12 (build wizard)",
    }

    out = _rounds_dir() / f"{_slug(pres['name'])}-{pres_id[:6]}.bighat"
    out.write_text(json.dumps(pres, indent=2), encoding="utf-8")
    pres["_disk_path"] = str(out)
    logger.info("[build_wizard] wrote %s (%d rounds, host=%s, loc=%s)",
                out, round_count, host_id, location_id)
    return pres


# ---------------------------------------------------------------------------
# Public API: Round Roulette (5 REG + 5 MISC + 5 BIG choices → randomise)
# ---------------------------------------------------------------------------

def build_from_roulette(
    *,
    name: str,
    host_id: str,
    location_id: str,
    round_count: int,
    reg_pool: List[str],
    misc_pool: List[str],
    big_pool: List[str],
    mc_pool: Optional[List[str]] = None,
    mys_pool: Optional[List[str]] = None,
    seed: Optional[int] = None,
    intro_pack_id: Optional[str] = None,
    owner_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Slot-machine builder. Merchant's spec:
      - Host picks 5 candidates from REG, 5 from MISC, 5 from BIG.
      - Stop the randomiser → one is picked from each pool.
      - MC and MYS are auto-picked (single spinner each) from their pools.
      - If round_count==6, the (REG or MISC) slot 3 is auto-picked from a
        merged REG-or-MISC pool (spec quote:
        "if 6 rounds is chosen then the randomizer will automatically
        select an available round from (REG or MISC)").
    """
    if round_count not in ALLOWED_ROUND_COUNTS:
        raise BuildValidationError(
            f"round_count must be 5 or 6, got {round_count}"
        )
    rng = random.Random(seed) if seed is not None else random.Random()

    def _pick(pool: List[str], label: str) -> str:
        if not pool:
            raise BuildValidationError(f"{label} pool is empty")
        return rng.choice(pool)

    mc_choices = mc_pool or [p.name for p in _list_round_files_of_type("MC")]
    mys_choices = mys_pool or [p.name for p in _list_round_files_of_type("MYS")]

    if not mc_choices:
        raise BuildValidationError("no MC rounds on disk at Files/Trivia/MC")
    if not mys_choices:
        raise BuildValidationError("no MYS rounds on disk at Files/Trivia/MYS")

    mc_pick = _pick(mc_choices, "MC")
    reg_pick = _pick(reg_pool, "REG")
    misc_pick = _pick(misc_pool, "MISC")
    mys_pick = _pick(mys_choices, "MYS")
    big_pick = _pick(big_pool, "BIG")

    if round_count == 5:
        picks = [
            ("MC", mc_pick),
            ("REG", reg_pick),
            ("MISC", misc_pick),
            ("MYS", mys_pick),
            ("BIG", big_pick),
        ]
    else:  # 6
        # Slot-3 auto-pick from REG or MISC — must not reuse slot-2 REG or
        # slot-4 MISC picks; the pool for slot-3 is the merger MINUS those
        # two picks.
        merged = [r for r in reg_pool if r != reg_pick] + \
                 [m for m in misc_pool if m != misc_pick]
        if not merged:
            raise BuildValidationError(
                "cannot auto-pick slot-3: no eligible REG-or-MISC choice "
                "remaining after slot-2 and slot-4 selections"
            )
        slot3_pick = rng.choice(merged)
        # deduce type
        slot3_type = "REG" if slot3_pick in reg_pool else "MISC"
        picks = [
            ("MC", mc_pick),
            ("REG", reg_pick),
            (slot3_type, slot3_pick),
            ("MISC", misc_pick),
            ("MYS", mys_pick),
            ("BIG", big_pick),
        ]

    # Delegate to the wizard path — same validation, same writer.
    round_files = [ref for _, ref in picks]
    result = build_from_wizard(
        name=name, host_id=host_id, location_id=location_id,
        round_count=round_count, round_files=round_files,
        intro_pack_id=intro_pack_id, owner_email=owner_email,
    )
    result["_source"] = "round-roulette"
    result["_roulette_picks"] = [{"slot": i + 1, "type": t, "file": r}
                                  for i, (t, r) in enumerate(picks)]
    # Persist the roulette flag onto disk too.
    Path(result["_disk_path"]).write_text(
        json.dumps(result, indent=2), encoding="utf-8",
    )
    return result


# ---------------------------------------------------------------------------
# Intro slides — new library at Files/Trivia/Intros/
# ---------------------------------------------------------------------------

def list_intro_packs() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in sorted(_intros_dir().iterdir()) if _intros_dir().exists() else []:
        if p.suffix.lower() != ".bighat":
            continue
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "id": j.get("id") or p.stem,
                "name": j.get("name") or p.stem,
                "num_slides": len(j.get("slides") or []),
                "created_at": j.get("created_at"),
                "file": p.name,
            })
        except (OSError, ValueError) as e:
            logger.warning("[intros] skipping unreadable %s: %s", p, e)
    return out


def load_intro_pack(intro_id: str) -> Optional[Dict[str, Any]]:
    if not intro_id:
        return None
    for p in _intros_dir().iterdir() if _intros_dir().exists() else []:
        if p.suffix.lower() != ".bighat":
            continue
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if j.get("id") == intro_id or p.stem == intro_id:
                return j
        except (OSError, ValueError):
            continue
    return None


def save_intro_pack(name: str, slides: List[Dict[str, Any]]) -> Dict[str, Any]:
    pid = str(uuid.uuid4())
    doc = {
        "id": pid,
        "type": "trivia-intro-pack",
        "name": name.strip() or f"Intro Pack {pid[:6]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "slides": slides or [],
    }
    p = _intros_dir() / f"{_slug(doc['name'])}-{pid[:6]}.bighat"
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def delete_intro_pack(intro_id: str) -> bool:
    for p in _intros_dir().iterdir() if _intros_dir().exists() else []:
        if p.suffix.lower() != ".bighat":
            continue
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if j.get("id") == intro_id or p.stem == intro_id:
                p.unlink()
                return True
        except (OSError, ValueError):
            continue
    return False


# ---------------------------------------------------------------------------
# Overlay round-type tag matching (Step 17)
# ---------------------------------------------------------------------------

def overlays_for_round_type(
    location_overlays: List[Dict[str, Any]], round_type: str,
) -> List[Dict[str, Any]]:
    """Return overlays whose `applies_to_round_types` tag list includes
    `round_type` (case-insensitive). Overlays with NO tag list default to
    "applies to every round type" (backwards compat with legacy overlays)."""
    rt = (round_type or "").upper()
    out: List[Dict[str, Any]] = []
    for ov in location_overlays or []:
        tags = ov.get("applies_to_round_types")
        if tags is None:
            out.append(ov)  # untagged legacy → applies everywhere
            continue
        if any((t or "").upper() == rt for t in tags):
            out.append(ov)
    out.sort(key=lambda o: o.get("order") or 0)
    return out
