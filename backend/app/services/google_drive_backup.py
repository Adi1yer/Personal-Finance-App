"""Create / list / prune / restore Google Drive ledger backups."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db.profile_db import _clear_profile_engine_cache
from app.db.registry import profile_ledger_path
from app.services.encryption import decrypt_value, encrypt_value
from app.services.google_drive_oauth import fetch_email, refresh_access_token
from app.services.profile_settings import get_setting, set_setting

FOLDER_NAME = "Personal Finance Backups"
KEEP_COUNT = 5
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"


class GoogleDriveError(Exception):
    pass


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def connection_status(db: Session) -> dict[str, Any]:
    email = get_setting(db, "google_drive_email")
    token = get_setting(db, "google_drive_refresh_token_enc")
    return {
        "configured": True,  # filled by API from env
        "connected": bool(token and email),
        "email": email,
        "folder_id": get_setting(db, "google_drive_folder_id"),
        "last_backup_at": get_setting(db, "google_drive_last_backup_at"),
    }


def save_tokens(db: Session, token_payload: dict[str, Any]) -> dict[str, Any]:
    refresh = token_payload.get("refresh_token")
    access = token_payload.get("access_token")
    if not access:
        raise GoogleDriveError("No access token from Google")
    if refresh:
        set_setting(db, "google_drive_refresh_token_enc", encrypt_value(str(refresh)))
    elif not get_setting(db, "google_drive_refresh_token_enc"):
        raise GoogleDriveError(
            "Google did not return a refresh token. Disconnect in Google Account "
            "permissions and connect again with consent."
        )
    email = fetch_email(str(access)) or ""
    set_setting(db, "google_drive_email", email)
    folder_id = ensure_backup_folder(db, access_token=str(access))
    return {"email": email, "folder_id": folder_id}


def disconnect(db: Session) -> None:
    for key in (
        "google_drive_refresh_token_enc",
        "google_drive_email",
        "google_drive_folder_id",
        "google_drive_last_backup_at",
    ):
        set_setting(db, key, None)


def _access_token(db: Session) -> str:
    enc = get_setting(db, "google_drive_refresh_token_enc")
    if not enc:
        raise GoogleDriveError("Google Drive is not connected")
    try:
        refresh = decrypt_value(str(enc))
    except Exception as e:
        raise GoogleDriveError(f"Could not decrypt Drive token: {e}") from e
    try:
        data = refresh_access_token(refresh)
    except ValueError as e:
        detail = str(e)
        # Google Testing apps / revoked consent often return invalid_grant.
        if "invalid_grant" in detail or "expired or revoked" in detail.lower():
            disconnect(db)
            raise GoogleDriveError(
                "Google Drive access expired or was revoked. "
                "Click Connect Google Drive again to re-authorize."
            ) from e
        raise GoogleDriveError(detail) from e
    access = data.get("access_token")
    if not access:
        raise GoogleDriveError("Failed to refresh Google access token")
    # Google may rotate refresh tokens
    new_refresh = data.get("refresh_token")
    if new_refresh:
        set_setting(db, "google_drive_refresh_token_enc", encrypt_value(str(new_refresh)))
    return str(access)


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def ensure_backup_folder(db: Session, *, access_token: str | None = None) -> str:
    existing = get_setting(db, "google_drive_folder_id")
    token = access_token or _access_token(db)
    if existing:
        # Verify it still exists
        with httpx.Client(timeout=30.0) as client:
            res = client.get(
                f"{DRIVE_API}/files/{existing}",
                headers=_headers(token),
                params={"fields": "id,trashed"},
            )
            if res.status_code == 200 and not res.json().get("trashed"):
                return str(existing)

    with httpx.Client(timeout=30.0) as client:
        # Prefer a folder we already created (drive.file scope).
        q = (
            f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        res = client.get(
            f"{DRIVE_API}/files",
            headers=_headers(token),
            params={"q": q, "spaces": "drive", "fields": "files(id,name)"},
        )
        if res.status_code >= 400:
            raise GoogleDriveError(f"Drive list failed: {res.text}")
        files = res.json().get("files") or []
        if files:
            folder_id = files[0]["id"]
        else:
            create = client.post(
                f"{DRIVE_API}/files",
                headers={**_headers(token), "Content-Type": "application/json"},
                json={
                    "name": FOLDER_NAME,
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
            if create.status_code >= 400:
                raise GoogleDriveError(f"Drive folder create failed: {create.text}")
            folder_id = create.json()["id"]
    set_setting(db, "google_drive_folder_id", folder_id)
    return str(folder_id)


def _build_zip(profile_id: str) -> tuple[bytes, str]:
    ledger = profile_ledger_path(profile_id)
    if not ledger.is_file():
        raise GoogleDriveError("Ledger database not found")
    stamp = _utc_stamp()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(ledger, arcname="ledger.db")
        meta = {
            "profile_id": profile_id,
            "created_at": stamp,
            "kind": "personal-finance-ledger-backup",
            "version": 1,
        }
        zf.writestr("meta.json", json.dumps(meta, indent=2))
    name = f"ledger-{stamp}.zip"
    return buf.getvalue(), name


def list_backups(db: Session) -> list[dict[str, Any]]:
    token = _access_token(db)
    folder_id = ensure_backup_folder(db, access_token=token)
    q = f"'{folder_id}' in parents and trashed = false and name contains 'ledger-'"
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"{DRIVE_API}/files",
            headers=_headers(token),
            params={
                "q": q,
                "orderBy": "createdTime desc",
                "pageSize": 50,
                "fields": "files(id,name,createdTime,size)",
            },
        )
        if res.status_code >= 400:
            raise GoogleDriveError(f"Drive list backups failed: {res.text}")
        files = res.json().get("files") or []
    return [
        {
            "id": f["id"],
            "name": f.get("name"),
            "created_at": f.get("createdTime"),
            "size": f.get("size"),
        }
        for f in files
    ]


def create_backup(db: Session, profile_id: str) -> dict[str, Any]:
    token = _access_token(db)
    folder_id = ensure_backup_folder(db, access_token=token)
    payload, filename = _build_zip(profile_id)
    metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    boundary = "=======personal_finance_backup======="
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: application/zip\r\n\r\n"
    ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")

    with httpx.Client(timeout=120.0) as client:
        res = client.post(
            f"{DRIVE_UPLOAD}/files?uploadType=multipart&fields=id,name,createdTime,size",
            headers={
                **_headers(token),
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )
        if res.status_code >= 400:
            raise GoogleDriveError(f"Drive upload failed: {res.text}")
        uploaded = res.json()

    deleted = 0
    # Re-list and prune oldest beyond KEEP_COUNT
    backups = list_backups(db)
    if len(backups) > KEEP_COUNT:
        token = _access_token(db)
        with httpx.Client(timeout=60.0) as client:
            for item in backups[KEEP_COUNT:]:
                r = client.delete(
                    f"{DRIVE_API}/files/{item['id']}",
                    headers=_headers(token),
                )
                if r.status_code in (200, 204):
                    deleted += 1

    stamp = datetime.now(timezone.utc).isoformat()
    set_setting(db, "google_drive_last_backup_at", stamp)
    return {
        "file_id": uploaded.get("id"),
        "name": uploaded.get("name") or filename,
        "created_at": uploaded.get("createdTime") or stamp,
        "pruned": deleted,
        "kept": KEEP_COUNT,
    }


def restore_backup(db: Session, profile_id: str, file_id: str) -> dict[str, Any]:
    token = _access_token(db)
    with httpx.Client(timeout=120.0) as client:
        meta = client.get(
            f"{DRIVE_API}/files/{file_id}",
            headers=_headers(token),
            params={"fields": "id,name"},
        )
        if meta.status_code >= 400:
            raise GoogleDriveError(f"Backup not found: {meta.text}")
        name = meta.json().get("name") or file_id
        dl = client.get(
            f"{DRIVE_API}/files/{file_id}",
            headers=_headers(token),
            params={"alt": "media"},
        )
        if dl.status_code >= 400:
            raise GoogleDriveError(f"Download failed: {dl.text}")
        content = dl.content

    ledger_path = profile_ledger_path(profile_id)
    backup_local = ledger_path.with_suffix(".db.pre-restore")
    _clear_profile_engine_cache(profile_id)

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        if "ledger.db" not in zf.namelist():
            raise GoogleDriveError("Zip is missing ledger.db")
        extracted = zf.read("ledger.db")

    if ledger_path.is_file():
        shutil.copy2(ledger_path, backup_local)
    ledger_path.write_bytes(extracted)
    _clear_profile_engine_cache(profile_id)
    return {
        "restored_from": name,
        "file_id": file_id,
        "local_safety_copy": str(backup_local) if backup_local.is_file() else None,
        "message": "Ledger restored. Reload the app to pick up the restored data.",
    }


def backup_all_connected_profiles() -> list[dict[str, Any]]:
    """Best-effort Drive backup for every profile with a stored refresh token (quit hook)."""
    from app.db.profile_db import get_profile_session_factory
    from app.db.registry import get_registry_session_factory, init_registry_database
    from app.models.profile import Profile

    init_registry_database()
    registry = get_registry_session_factory()()
    results: list[dict[str, Any]] = []
    try:
        profiles = registry.query(Profile).order_by(Profile.email).all()
        for profile in profiles:
            db = get_profile_session_factory(profile.id)()
            try:
                if not get_setting(db, "google_drive_refresh_token_enc"):
                    continue
                out = create_backup(db, profile.id)
                results.append({"profile_id": profile.id, "email": profile.email, **out})
            except Exception as exc:  # noqa: BLE001 — quit must never hang on one profile
                results.append(
                    {
                        "profile_id": profile.id,
                        "email": profile.email,
                        "error": str(exc),
                    }
                )
            finally:
                db.close()
    finally:
        registry.close()
    return results
