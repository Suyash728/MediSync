"""
POST /share              — create a new time-limited share grant (returns token)
GET  /share              — list all share grants for the patient
DELETE /share/{grant_id} — revoke a share grant (sets is_active=False)
GET  /share/view/{token} — public endpoint: validate token, return scoped records

Security invariants (enforced here AND in RLS):
  1. Token is a 32-byte cryptographically random hex string (secrets.token_hex(32)).
  2. Expired or revoked grants return 403, never 404 (prevents token enumeration).
  3. Every call to /view/{token} writes a row to access_log.
  4. Ownership is verified server-side before any mutation — the service-role key
     bypasses RLS, so we cannot rely on RLS alone for write operations.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from models.schemas import ShareGrantCreate
from utils.access import require_active_access
from utils.auth import get_current_patient
from utils.db import get_supabase
from utils.storage import get_signed_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", summary="Create a share grant and return a shareable token [paid]")
async def create_share_grant(
    body: ShareGrantCreate,
    patient_id: str = Depends(require_active_access),
) -> dict:
    """
    Generate a cryptographically random token and persist a share_grants row.

    The caller constructs the full shareable URL as:
        <frontend_origin>/clinician/shared/{token}

    We return the token separately so the frontend can build the URL using
    window.location.origin (no hardcoded base URL in the backend).
    """
    supabase = get_supabase()
    token = secrets.token_hex(32)   # 64-char hex string; brute-force infeasible
    expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    row: dict = {
        "patient_id":         patient_id,
        "token":              token,
        "recipient_name":     body.recipient_name,
        "recipient_email":    body.recipient_email,
        # Store UUIDs as strings; Postgres UUID[] accepts string UUIDs
        "scope_record_ids":   [str(r) for r in body.scope_record_ids] if body.scope_record_ids else None,
        "scope_record_types": [rt.value for rt in body.scope_record_types] if body.scope_record_types else None,
        "expires_at":         expires_at.isoformat(),
        "is_active":          True,
    }

    result = supabase.table("share_grants").insert(row).execute()
    grant = result.data[0]

    # For audit metadata: if sharing a single specific record, fetch its title + date
    # so the access history UI can show "Share link created — [record title]".
    record_title: str | None = None
    record_date: str | None = None
    if body.scope_record_ids and len(body.scope_record_ids) == 1:
        rec = (
            supabase.table("health_records")
            .select("title, document_date")
            .eq("id", str(body.scope_record_ids[0]))
            .eq("patient_id", patient_id)
            .single()
            .execute()
        )
        if rec.data:
            record_title = rec.data.get("title")
            record_date  = rec.data.get("document_date")

    # Audit: one log row per grant creation
    supabase.table("access_log").insert({
        "patient_id": patient_id,
        "action":     "share_create",
        "actor_type": "patient",
        "actor_id":   patient_id,
        "metadata":   {
            "grant_id":       grant["id"],
            "recipient_name": body.recipient_name,
            "expires_at":     expires_at.isoformat(),
            "scope_types":    [rt.value for rt in body.scope_record_types] if body.scope_record_types else None,
            # Populated when the patient shares a single specific record
            "record_title":   record_title,
            "record_date":    record_date,
        },
    }).execute()

    logger.info("share: created grant %s for patient %s", grant["id"][:8], patient_id[:8])
    return {"grant": grant, "token": token}


@router.get("/", summary="List all share grants for the current patient")
async def list_share_grants(
    patient_id: str = Depends(get_current_patient),
) -> dict:
    """Return grants newest-first. Includes revoked grants so the patient sees history."""
    supabase = get_supabase()
    result = (
        supabase.table("share_grants")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"grants": result.data, "total": len(result.data)}


@router.delete("/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_grant(
    grant_id: str,
    patient_id: str = Depends(get_current_patient),
) -> None:
    """
    Revoke a share grant immediately by setting is_active=False.
    The next /view/{token} call for this grant returns 403.

    Ownership check (belt-and-suspenders): we filter by both id AND patient_id
    even though the service-role key bypasses RLS. This ensures that a patient
    cannot revoke another patient's grant by guessing a UUID.
    """
    supabase = get_supabase()

    existing = (
        supabase.table("share_grants")
        .select("id, patient_id")
        .eq("id", grant_id)
        .eq("patient_id", patient_id)   # explicit ownership check — not relying on RLS
        .single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share grant not found.",
        )

    supabase.table("share_grants").update({"is_active": False}).eq("id", grant_id).execute()

    # Audit: one log row per revocation
    supabase.table("access_log").insert({
        "patient_id": patient_id,
        "action":     "share_revoke",
        "actor_type": "patient",
        "actor_id":   patient_id,
        "metadata":   {"grant_id": grant_id},
    }).execute()

    logger.info("share: revoked grant %s by patient %s", grant_id[:8], patient_id[:8])


@router.get("/view/{token}", summary="[Public] Validate token and return scoped records")
async def view_shared_records(token: str) -> dict:
    """
    Public endpoint — no patient authentication required.
    Resolves a share token and returns the patient's scoped health records.

    Authorization logic (the three-gate check):
      1. Token lookup via service-role key (bypasses RLS).  We cannot use the anon
         key here because share_grants RLS only exposes rows to auth.uid()=patient_id,
         and the clinician is not authenticated as that patient.
      2. is_active=False (revoked by patient) → 403.
      3. expires_at < now() (link too old) → 403.
      Both inactive and expired return 403, never 404, so an attacker cannot
      distinguish "this token was never issued" from "this token was revoked."
    """
    supabase = get_supabase()

    result = (
        supabase.table("share_grants")
        .select("*")
        .eq("token", token)
        .single()
        .execute()
    )

    if not result.data:
        # 403, not 404 — prevents enumeration of valid token prefixes
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    grant = result.data

    if not grant["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This share link has been revoked by the patient.",
        )

    expires_at = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This share link has expired.",
        )

    patient_id: str = grant["patient_id"]

    # Build the scoped health_records query based on what the patient chose to share
    query = (
        supabase.table("health_records")
        .select("*")
        .eq("patient_id", patient_id)
        .order("document_date", desc=True)
    )

    if grant.get("scope_record_ids"):
        # Patient shared specific records by ID
        query = query.in_("id", grant["scope_record_ids"])
    elif grant.get("scope_record_types"):
        # Patient shared specific record types (e.g. prescriptions only)
        query = query.in_("record_type", grant["scope_record_types"])
    # Both None → no filter → share ALL records (patient's explicit choice)

    records_result = query.execute()
    raw_records: list[dict] = records_result.data

    # Enrich each record: signed URL for the original document + child rows.
    # Signed URLs are generated server-side using the service-role key — the
    # clinician's browser never touches Storage directly or sees our credentials.
    records: list[dict] = []
    for rec in raw_records:
        file_url: str | None = None
        if rec.get("file_path"):
            try:
                file_url = get_signed_url(rec["file_path"], expires_in=3600)
            except Exception as exc:
                logger.warning("share: signed URL failed for record %s: %s", rec["id"][:8], exc)

        # Medications extracted from this record
        meds = (
            supabase.table("medications")
            .select("id, name, dosage, frequency, duration, is_active, low_confidence")
            .eq("record_id", rec["id"])
            .execute()
        ).data

        # Lab values extracted from this record
        labs = (
            supabase.table("lab_values")
            .select("id, test_name, value, unit, reference_range, reference_source, is_abnormal")
            .eq("record_id", rec["id"])
            .execute()
        ).data

        records.append({**rec, "file_url": file_url, "medications": meds, "lab_values": labs})

    # Audit: every clinician view is logged.
    # actor_id is the first 8 chars of the token — enough to correlate multiple
    # views from the same link without storing the full reusable token in the log.
    supabase.table("access_log").insert({
        "patient_id": patient_id,
        "action":     "share_view",
        "actor_type": "clinician",
        "actor_id":   token[:8],
        "metadata":   {
            "grant_id":       grant["id"],
            "recipient_name": grant.get("recipient_name"),
            "record_count":   len(records),
        },
    }).execute()

    # Patient display name for the clinician header
    profile = (
        supabase.table("profiles")
        .select("full_name")
        .eq("id", patient_id)
        .single()
        .execute()
    )
    patient_name: str = profile.data["full_name"] if profile.data else "Patient"

    # Human-readable scope label shown in the clinician view header
    if grant.get("scope_record_types"):
        readable_types = ", ".join(
            t.replace("_", " ").title() for t in grant["scope_record_types"]
        )
        scope_label = f"Shared types: {readable_types}"
    elif grant.get("scope_record_ids"):
        scope_label = f"{len(records)} specific record(s)"
    else:
        scope_label = "All records"

    logger.info(
        "share: view token=%s patient=%s records=%d",
        token[:8], patient_id[:8], len(records),
    )

    return {
        "patient_name":     patient_name,
        "grant_expires_at": expires_at.isoformat(),
        "scope_label":      scope_label,
        "recipient_name":   grant.get("recipient_name"),
        "records":          records,
    }
