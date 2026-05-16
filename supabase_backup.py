import os
import json
import time
import threading
import requests
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

MAX_RETRIES = 5
RETRY_DELAYS = [2, 4, 8, 16, 32]

AUTO_BACKUP_INTERVAL_SECONDS = 300
AUTO_RESTORE_INTERVAL_SECONDS = 900

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def is_configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def _request_with_retry(method, url, **kwargs):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
    raise last_exc

def save_backup(data_dir, default_data, label="Manual"):
    if not is_configured():
        raise RuntimeError("Supabase is not configured (missing SUPABASE_URL or SUPABASE_SERVICE_KEY)")
    snapshot = {}
    for fname in default_data.keys():
        fpath = os.path.join(data_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                snapshot[fname] = json.load(f)
        except Exception:
            snapshot[fname] = default_data.get(fname, {})
    payload = {
        "label": label,
        "data": snapshot,
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    resp = _request_with_retry(
        "POST",
        f"{SUPABASE_URL}/rest/v1/backups",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    result = resp.json()
    return result[0] if isinstance(result, list) else result

def list_backups(limit=30):
    if not is_configured():
        return []
    resp = _request_with_retry(
        "GET",
        f"{SUPABASE_URL}/rest/v1/backups",
        headers=_headers(),
        params={
            "select": "id,label,created_at",
            "order": "created_at.desc",
            "limit": limit,
        },
        timeout=10,
    )
    return resp.json()

def restore_backup(backup_id, data_dir):
    if not is_configured():
        raise RuntimeError("Supabase is not configured")
    resp = _request_with_retry(
        "GET",
        f"{SUPABASE_URL}/rest/v1/backups",
        headers={**_headers(), "Prefer": ""},
        params={
            "select": "id,label,data,created_at",
            "id": f"eq.{backup_id}",
            "limit": 1,
        },
        timeout=15,
    )
    results = resp.json()
    if not results:
        raise ValueError("Backup not found")
    row = results[0]
    snapshot = row["data"]
    os.makedirs(data_dir, exist_ok=True)
    for fname, content in snapshot.items():
        fpath = os.path.join(data_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
    return row

def restore_latest_backup(data_dir):
    if not is_configured():
        return None
    try:
        resp = _request_with_retry(
            "GET",
            f"{SUPABASE_URL}/rest/v1/backups",
            headers={**_headers(), "Prefer": ""},
            params={
                "select": "id,label,data,created_at",
                "order": "created_at.desc",
                "limit": 1,
            },
            timeout=15,
        )
        results = resp.json()
        if not results:
            return None
        row = results[0]
        snapshot = row["data"]
        os.makedirs(data_dir, exist_ok=True)
        for fname, content in snapshot.items():
            fpath = os.path.join(data_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        return row
    except Exception as e:
        print(f"[supabase_backup] restore_latest_backup failed: {e}")
        return None

def delete_backup(backup_id):
    if not is_configured():
        raise RuntimeError("Supabase is not configured")
    _request_with_retry(
        "DELETE",
        f"{SUPABASE_URL}/rest/v1/backups",
        headers=_headers(),
        params={"id": f"eq.{backup_id}"},
        timeout=10,
    )
    return True

_auto_backup_timer = None
_auto_restore_timer = None

def _run_auto_backup(data_dir, default_data):
    global _auto_backup_timer
    try:
        save_backup(data_dir, default_data, label="Auto")
        print(f"[supabase_backup] Auto backup saved at {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}")
    except Exception as e:
        print(f"[supabase_backup] Auto backup failed: {e}")
    finally:
        _auto_backup_timer = threading.Timer(
            AUTO_BACKUP_INTERVAL_SECONDS,
            _run_auto_backup,
            args=(data_dir, default_data),
        )
        _auto_backup_timer.daemon = True
        _auto_backup_timer.start()

def _run_auto_restore(data_dir):
    global _auto_restore_timer
    try:
        row = restore_latest_backup(data_dir)
        if row:
            print(f"[supabase_backup] Auto restore from backup {row.get('id', '')[:8]} ({row.get('created_at')})")
    except Exception as e:
        print(f"[supabase_backup] Auto restore failed: {e}")
    finally:
        _auto_restore_timer = threading.Timer(
            AUTO_RESTORE_INTERVAL_SECONDS,
            _run_auto_restore,
            args=(data_dir,),
        )
        _auto_restore_timer.daemon = True
        _auto_restore_timer.start()

def start_auto_backup(data_dir, default_data, delay_seconds=30):
    global _auto_backup_timer
    if not is_configured():
        print("[supabase_backup] Auto backup disabled — Supabase not configured.")
        return
    _auto_backup_timer = threading.Timer(
        delay_seconds,
        _run_auto_backup,
        args=(data_dir, default_data),
    )
    _auto_backup_timer.daemon = True
    _auto_backup_timer.start()
    print(f"[supabase_backup] Auto backup enabled — first run in {delay_seconds}s, then every {AUTO_BACKUP_INTERVAL_SECONDS}s.")

def start_auto_restore(data_dir, delay_seconds=60):
    global _auto_restore_timer
    if not is_configured():
        print("[supabase_backup] Auto restore disabled — Supabase not configured.")
        return
    _auto_restore_timer = threading.Timer(
        delay_seconds,
        _run_auto_restore,
        args=(data_dir,),
    )
    _auto_restore_timer.daemon = True
    _auto_restore_timer.start()
    print(f"[supabase_backup] Auto restore enabled — first run in {delay_seconds}s, then every {AUTO_RESTORE_INTERVAL_SECONDS}s.")

def startup_restore(data_dir):
    if not is_configured():
        return
    try:
        print("[supabase_backup] Deploy detected — restoring latest backup from Supabase...")
        row = restore_latest_backup(data_dir)
        if row:
            print(f"[supabase_backup] Startup restore complete from {row.get('created_at')}")
        else:
            print("[supabase_backup] No backup found in Supabase — starting fresh.")
    except Exception as e:
        print(f"[supabase_backup] Startup restore error: {e}")
