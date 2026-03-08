#!/usr/bin/env python3
"""
StorageRationalizer — Setup Tracker
Run:  python3 tracker.py
Open: http://localhost:5000
Data: saved to tracker_data.db in the same folder
"""

import sqlite3, json, os, glob, re
from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime, timezone

app = Flask(__name__)
DB       = os.path.join(os.path.dirname(__file__), "tracker_data.db")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
DUPES_DB = os.path.join(os.path.dirname(__file__), "..", "manifests", "duplicates.db")
TARGET_GB = 143.0

# ── Database setup ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS fields (
                key   TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                section TEXT PRIMARY KEY,
                content TEXT,
                updated_at TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS checklist (
                item_id TEXT PRIMARY KEY,
                checked INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        db.commit()

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("tracker.html")

@app.route("/api/load")
def load_all():
    """Load all saved data in one shot."""
    with get_db() as db:
        fields   = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM fields")}
        notes    = {r["section"]: r["content"] for r in db.execute("SELECT section, content FROM notes")}
        checks   = {r["item_id"]: bool(r["checked"]) for r in db.execute("SELECT item_id, checked FROM checklist")}
    return jsonify({"fields": fields, "notes": notes, "checks": checks})

@app.route("/api/field", methods=["POST"])
def save_field():
    """Save a single field value."""
    data = request.json
    key, value = data.get("key"), data.get("value", "")
    with get_db() as db:
        db.execute("""
            INSERT INTO fields (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, value))
        db.commit()
    return jsonify({"ok": True})

@app.route("/api/note", methods=["POST"])
def save_note():
    """Save a section note."""
    data = request.json
    section, content = data.get("section"), data.get("content", "")
    with get_db() as db:
        db.execute("""
            INSERT INTO notes (section, content, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(section) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at
        """, (section, content))
        db.commit()
    return jsonify({"ok": True})

@app.route("/api/check", methods=["POST"])
def save_check():
    """Save a checkbox state."""
    data = request.json
    item_id, checked = data.get("item_id"), int(data.get("checked", False))
    with get_db() as db:
        db.execute("""
            INSERT INTO checklist (item_id, checked, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(item_id) DO UPDATE SET checked=excluded.checked, updated_at=excluded.updated_at
        """, (item_id, checked))
        db.commit()
    return jsonify({"ok": True})

@app.route("/api/export")
def export_data():
    """Export all data as JSON backup."""
    with get_db() as db:
        fields = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM fields")}
        notes  = {r["section"]: r["content"] for r in db.execute("SELECT section, content FROM notes")}
        checks = {r["item_id"]: bool(r["checked"]) for r in db.execute("SELECT item_id, checked FROM checklist")}
    export = {"exported_at": datetime.now().isoformat(), "fields": fields, "notes": notes, "checks": checks}
    path = os.path.join(os.path.dirname(__file__), "tracker_backup.json")
    with open(path, "w") as f:
        json.dump(export, f, indent=2)
    return send_file(path, as_attachment=True, download_name=f"StorageRationalizer_backup_{datetime.now().strftime('%Y-%m-%d')}.json")

@app.route("/api/import", methods=["POST"])
def import_data():
    """Import from a JSON backup."""
    data = request.json
    with get_db() as db:
        for k, v in data.get("fields", {}).items():
            db.execute("INSERT INTO fields (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        for s, c in data.get("notes", {}).items():
            db.execute("INSERT INTO notes (section,content) VALUES (?,?) ON CONFLICT(section) DO UPDATE SET content=excluded.content", (s, c))
        for i, c in data.get("checks", {}).items():
            db.execute("INSERT INTO checklist (item_id,checked) VALUES (?,?) ON CONFLICT(item_id) DO UPDATE SET checked=excluded.checked", (i, int(c)))
        db.commit()
    return jsonify({"ok": True})

@app.route("/api/stats")
def stats():
    """Quick stats for header badge."""
    with get_db() as db:
        total   = db.execute("SELECT COUNT(*) FROM checklist").fetchone()[0]
        checked = db.execute("SELECT COUNT(*) FROM checklist WHERE checked=1").fetchone()[0]
    return jsonify({"total": total, "checked": checked})

@app.route("/api/cleanup_status")
def cleanup_status():
    """Parse latest cleanup_*.log and return live stats."""
    log_files = sorted(glob.glob(os.path.join(LOGS_DIR, "cleanup_*.log")))
    if not log_files:
        return jsonify({"error": "No cleanup logs found"})

    latest   = log_files[-1]
    log_name = os.path.basename(latest)

    try:
        with open(latest, "r") as f:
            lines = f.readlines()
    except OSError as e:
        return jsonify({"error": str(e)})

    ts_re = re.compile(r"^\[([^\]]+)\]\s+(.*)")

    total_files  = 0
    deleted      = 0
    not_found    = 0
    errors_403   = 0
    errors_other = 0
    mode         = "unknown"
    start_ts     = None
    end_ts       = None
    is_complete  = False
    source_counts = {}   # source -> {deleted, not_found, errors}

    def ensure_src(src):
        if src not in source_counts:
            source_counts[src] = {"deleted": 0, "not_found": 0, "errors": 0}

    for raw in lines:
        m = ts_re.match(raw.strip())
        if not m:
            continue
        ts_str, msg = m.group(1), m.group(2)

        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            ts = None

        if "=== Phase 3 Cleaner started" in msg:
            start_ts = ts
            mm = re.search(r"mode=(\S+)", msg)
            if mm:
                mode = mm.group(1)
            mm = re.search(r"files=(\d+)", msg)
            if mm:
                total_files = int(mm.group(1))

        elif "=== Complete" in msg:
            end_ts      = ts
            is_complete = True

        elif msg.startswith(("DELETED ", "TRASHED ")):
            parts = msg.split()
            src   = parts[1] if len(parts) > 1 else "unknown"
            ensure_src(src)
            source_counts[src]["deleted"] += 1
            deleted += 1

        elif msg.startswith(("SKIP_NOT_FOUND ", "NOT_FOUND ")):
            parts = msg.split()
            src   = parts[1] if len(parts) > 1 else "unknown"
            ensure_src(src)
            source_counts[src]["not_found"] += 1
            not_found += 1

        elif msg.startswith("ERROR "):
            parts = msg.split()
            src   = parts[1] if len(parts) > 1 else "unknown"
            ensure_src(src)
            if "HTTP 403" in msg:
                source_counts[src]["errors"] += 1
                errors_403 += 1
            else:
                source_counts[src]["errors"] += 1
                errors_other += 1

    processed   = deleted + not_found + errors_403 + errors_other
    progress_pct = round((processed / total_files * 100) if total_files > 0 else 0, 1)

    # ETA / duration
    eta_seconds  = None
    elapsed_sec  = None
    if start_ts:
        now = datetime.now(start_ts.tzinfo or timezone.utc)
        if end_ts:
            elapsed_sec = (end_ts - start_ts).total_seconds()
        elif not is_complete and processed > 0:
            elapsed_sec = (now - start_ts).total_seconds()
            rate = processed / elapsed_sec if elapsed_sec > 0 else 0
            if rate > 0:
                eta_seconds = (total_files - processed) / rate

    # Space recovered from duplicates.db
    space_recovered_gb = 0.0
    try:
        if os.path.exists(DUPES_DB):
            conn = sqlite3.connect(DUPES_DB)
            row  = conn.execute(
                "SELECT SUM(file_size) FROM duplicate_members WHERE action='deleted'"
            ).fetchone()
            conn.close()
            if row and row[0]:
                space_recovered_gb = round(row[0] / (1024 ** 3), 2)
    except Exception:
        pass

    last_lines = [l.rstrip() for l in lines if l.strip()][-20:]

    return jsonify({
        "log_file":          log_name,
        "mode":              mode,
        "total_files":       total_files,
        "deleted":           deleted,
        "not_found":         not_found,
        "errors_403":        errors_403,
        "errors_other":      errors_other,
        "processed":         processed,
        "progress_pct":      progress_pct,
        "is_complete":       is_complete,
        "start_time":        start_ts.isoformat() if start_ts else None,
        "end_time":          end_ts.isoformat()   if end_ts   else None,
        "elapsed_sec":       elapsed_sec,
        "eta_seconds":       eta_seconds,
        "space_recovered_gb": space_recovered_gb,
        "target_gb":         TARGET_GB,
        "source_breakdown":  source_counts,
        "last_lines":        last_lines,
    })

if __name__ == "__main__":
    init_db()
    print("\n" + "="*55)
    print("  StorageRationalizer — Setup Tracker")
    print("  Open in browser: http://localhost:5000")
    print("  Data saved to:   tracker_data.db")
    print("  Stop server:     Ctrl+C")
    print("="*55 + "\n")
    app.run(debug=False, port=5000, host="127.0.0.1")
