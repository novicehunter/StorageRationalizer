#!/usr/bin/env python3
"""
StorageRationalizer — Setup Tracker
Run:  python3 tracker.py
Open: http://localhost:5000
Data: saved to tracker_data.db in the same folder
"""

import sqlite3, json, os
from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime

app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), "tracker_data.db")

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

if __name__ == "__main__":
    init_db()
    print("\n" + "="*55)
    print("  StorageRationalizer — Setup Tracker")
    print("  Open in browser: http://localhost:5000")
    print("  Data saved to:   tracker_data.db")
    print("  Stop server:     Ctrl+C")
    print("="*55 + "\n")
    app.run(debug=False, port=5000, host="127.0.0.1")
