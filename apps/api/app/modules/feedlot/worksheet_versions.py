"""Version history of the worksheet: every imported workbook is kept, and any version can be restored.

What a "version" covers: the WEIGHTS (and entry weights) the worksheet put on animals that exist. Restoring a version
re-aligns those to that workbook (the same rules as an import; see worksheet_align). It does not delete animals,
batches, sales or Finance postings: the Finance ledger is append-only and needs its own reversing entries, so that
is a separate, deliberate step and is not done here.

Every real change is recorded as a new version (source 'restore' / 'unpost' included) so history only grows and a
restore can itself be undone by restoring the version before it.
"""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.feedlot import worksheet_reconcile
from app.modules.feedlot.models import WorksheetVersion
from app.modules.feedlot.worksheet_parse import parse_workbook

_LOCK_NAMESPACE = 7302
UNPOST_CONFIRM = "UNPOST"


def new_report(dry_run: bool) -> dict:
    return {"dry_run": dry_run, "ok": True, "created": Counter(), "updated": Counter(), "unchanged": Counter(),
            "warnings": [], "errors": []}


def finish_report(report: dict) -> dict:
    for k in ("created", "updated", "unchanged"):
        report[k] = dict(report[k])
    return report


def summarise(report: dict) -> dict:
    u, c = report.get("updated", {}), report.get("created", {})
    return {
        "created": dict(c), "updated": dict(u), "warnings": len(report.get("warnings", [])),
        "weights": {"appended": c.get("weight_records", 0), "voided": u.get("weights_voided", 0),
                    "restored": u.get("weights_restored", 0), "entry_weights": u.get("entry_weights", 0)},
        "conflicts": len(report.get("conflicts", [])) + len(report.get("weight_conflicts", [])),
        "ambiguous_dates": len(report.get("ambiguous_dates", [])), "moved": len(report.get("moved", [])),
    }


async def record_version(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None, content: bytes | None, *,
                         source: str, filename: str | None, cycle_id: uuid.UUID | None, note: str | None = None,
                         restored_from: uuid.UUID | None = None) -> tuple[WorksheetVersion, bool]:
    """Store a workbook as the next version. -> (version, is_new). Importing a file identical to the latest version
    does not create another one. Does not commit (it is part of the caller's transaction)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:ns, :k)"), {"ns": _LOCK_NAMESPACE, "k": org_id.int % 2147483647})
    digest = hashlib.sha256(content).hexdigest() if content else None
    last = (await db.execute(select(WorksheetVersion).where(WorksheetVersion.organization_id == org_id)
                             .order_by(WorksheetVersion.version_no.desc()).limit(1))).scalar_one_or_none()
    if last is not None and digest and source in ("upload", "sync") and last.sha256 == digest:
        return last, False
    v = WorksheetVersion(organization_id=org_id, production_cycle_id=cycle_id,
                         version_no=(last.version_no if last else 0) + 1, source=source, filename=filename, sha256=digest,
                         size_bytes=len(content or b""), content=content, note=note, restored_from_version_id=restored_from,
                         created_by=user_id)
    db.add(v)
    await db.flush()
    return v, True


def _out(v: WorksheetVersion, numbers: dict[uuid.UUID, int], latest_no: int) -> dict:
    return {"id": str(v.id), "version_no": v.version_no, "source": v.source, "filename": v.filename, "sha256": v.sha256,
            "size_bytes": v.size_bytes, "has_file": v.size_bytes > 0, "note": v.note, "summary": v.summary,
            "production_cycle_id": str(v.production_cycle_id) if v.production_cycle_id else None,
            "restored_from_version_no": numbers.get(v.restored_from_version_id) if v.restored_from_version_id else None,
            "created_by": str(v.created_by) if v.created_by else None, "created_at": v.created_at.isoformat(),
            "is_latest": v.version_no == latest_no}


async def list_versions(db: AsyncSession, org_id: uuid.UUID, limit: int = 100) -> list[dict]:
    rows = list((await db.execute(select(WorksheetVersion).where(WorksheetVersion.organization_id == org_id)
                                  .order_by(WorksheetVersion.version_no.desc()).limit(limit))).scalars())
    numbers = {v.id: v.version_no for v in rows}
    latest = rows[0].version_no if rows else 0
    return [_out(v, numbers, latest) for v in rows]


async def _get(db: AsyncSession, org_id: uuid.UUID, version_id: uuid.UUID) -> WorksheetVersion:
    v = (await db.execute(select(WorksheetVersion).where(WorksheetVersion.id == version_id,
                                                         WorksheetVersion.organization_id == org_id))).scalar_one_or_none()
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worksheet version not found")
    return v


async def get_file(db: AsyncSession, org_id: uuid.UUID, version_id: uuid.UUID) -> tuple[WorksheetVersion, bytes]:
    v = await _get(db, org_id, version_id)
    if not v.content:
        raise HTTPException(status.HTTP_409_CONFLICT, "This entry has no workbook file (it records an unpost, not an import)")
    return v, bytes(v.content)


async def restore_version(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, version_id: uuid.UUID, *,
                          dry_run: bool = True) -> dict:
    """Re-align the weights on existing animals with an earlier workbook. dry_run previews and saves nothing."""
    v, content = await get_file(db, org_id, version_id)
    if v.production_cycle_id:
        from app.modules.cycles.deps import ensure_writable
        await ensure_writable(db, org_id, v.production_cycle_id)          # a closed cycle is not changed
    try:
        pw = parse_workbook(content)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    report = new_report(dry_run)
    report["warnings"].extend(pw.warnings)
    ver = None
    try:
        if not dry_run:
            ver, _ = await record_version(db, org_id, user_id, content, source="restore", filename=v.filename,
                                          cycle_id=v.production_cycle_id, note=f"Restored version {v.version_no}",
                                          restored_from=v.id)
            report["version"] = {"id": str(ver.id), "version_no": ver.version_no}
        await worksheet_reconcile.realign_from_workbook(db, org_id, user_id, pw, cycle_id=v.production_cycle_id,
                                                        version_id=ver.id if ver else None, report=report)
        if ver is not None:
            ver.summary = summarise(report)
        await (db.rollback() if dry_run else db.commit())
    except Exception:
        await db.rollback()
        raise
    report["restored_version_no"] = v.version_no
    return finish_report(report)


async def unpost_weights(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, cycle_id: uuid.UUID | None,
                         dry_run: bool = True, confirm: str | None = None) -> dict:
    """Set aside EVERY weight the worksheet imported (in one cycle, or the whole organisation when cycle_id is None).
    The farm's own entries are untouched. Reversible: restore any earlier version to bring the weights back."""
    if not dry_run and confirm != UNPOST_CONFIRM:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Type {UNPOST_CONFIRM} to confirm removing every imported weight")
    if cycle_id:
        from app.modules.cycles.deps import ensure_writable
        await ensure_writable(db, org_id, cycle_id)
    report = new_report(dry_run)
    ver = None
    try:
        if not dry_run:
            ver, _ = await record_version(db, org_id, user_id, None, source="unpost", filename=None, cycle_id=cycle_id,
                                          note="Unposted every imported weight" + (" in this cycle" if cycle_id else ""))
            report["version"] = {"id": str(ver.id), "version_no": ver.version_no}
        await worksheet_reconcile.realign_from_workbook(db, org_id, user_id, None, cycle_id=cycle_id,
                                                        version_id=ver.id if ver else None, report=report, empty=True)
        if ver is not None:
            ver.summary = summarise(report)
        await (db.rollback() if dry_run else db.commit())
    except Exception:
        await db.rollback()
        raise
    return finish_report(report)
