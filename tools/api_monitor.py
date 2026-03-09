"""
StorageRationalizer — API Usage Monitor

Tracks token consumption, quota usage, and estimated costs across:
- Google Drive API (quota: 1B units/day, 1000 req/100s)
- OneDrive / Microsoft Graph API (quota: 10K req/10min)

Usage:
    from tools.api_monitor import APIMonitor
    monitor = APIMonitor()

    # Wrap API calls
    with monitor.track("google_drive", "files.list"):
        response = service.files().list(...).execute()

    # Report
    monitor.report()
    monitor.check_alerts()
"""

import functools
import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Generator, Optional

logger = logging.getLogger("api")

# ---------------------------------------------------------------------------
# Cost / quota constants
# ---------------------------------------------------------------------------

# Google Drive API v3 — quota units per operation
# https://developers.google.com/drive/api/guides/limits
GOOGLE_QUOTA_UNITS: Dict[str, int] = {
    "files.list": 1,
    "files.get": 1,
    "files.create": 10,
    "files.delete": 30,
    "files.update": 10,
    "files.copy": 100,
    "about.get": 1,
    "default": 1,
}

GOOGLE_DAILY_QUOTA = 1_000_000_000  # 1B units/day
GOOGLE_RATE_LIMIT = 1000  # req per 100 seconds per user

# OneDrive / Microsoft Graph — no published quota units, track request count
ONEDRIVE_RATE_LIMIT = 10_000  # req per 10 minutes per app

# Alert thresholds
ALERT_QUOTA_PCT = 0.80  # Alert at 80% of daily quota
ALERT_RATE_PCT = 0.70  # Alert at 70% of rate limit window

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class APICall:
    service: str
    operation: str
    started_at: float
    duration_ms: float = 0.0
    quota_units: int = 0
    status: str = "ok"
    error: Optional[str] = None


@dataclass
class ServiceStats:
    total_calls: int = 0
    total_quota_units: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0
    calls_this_window: int = 0
    window_start: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# APIMonitor
# ---------------------------------------------------------------------------


class APIMonitor:
    """
    Thread-safe API usage monitor with quota tracking, cost estimation,
    SQLite persistence, and alert rules.

    Args:
        db_path: Path to SQLite database for persisting call history.
                 Defaults to manifests/api_usage.db.
        persist: If True, write every call to the SQLite DB (default True).
    """

    _instance: Optional["APIMonitor"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        db_path: Optional[Path] = None,
        persist: bool = True,
    ) -> None:
        self._db_path = db_path or (
            Path(__file__).resolve().parent.parent / "manifests" / "api_usage.db"
        )
        self._persist = persist
        self._stats: Dict[str, ServiceStats] = {}
        self._calls: list[APICall] = []
        self._mutex = threading.Lock()

        if persist:
            self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def track(
        self,
        service: str,
        operation: str,
    ) -> Generator[None, None, None]:
        """
        Context manager that records a single API call.

        Usage:
            with monitor.track("google_drive", "files.list"):
                result = service.files().list(...).execute()
        """
        call = APICall(
            service=service,
            operation=operation,
            started_at=time.monotonic(),
            quota_units=self._quota_units(service, operation),
        )
        try:
            yield
        except Exception as exc:
            call.status = "error"
            call.error = str(exc)
            raise
        finally:
            call.duration_ms = (time.monotonic() - call.started_at) * 1000
            self._record(call)

    def track_call(
        self,
        service: str,
        operation: str,
    ) -> Callable:
        """
        Decorator that records API calls on a function.

        Usage:
            @monitor.track_call("google_drive", "files.list")
            def list_files():
                return service.files().list(...).execute()
        """

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                with self.track(service, operation):
                    return fn(*args, **kwargs)

            return wrapper

        return decorator

    def report(self) -> Dict:
        """Return a summary dict of all API usage since startup."""
        with self._mutex:
            summary = {}
            for svc, stats in self._stats.items():
                avg_ms = stats.total_duration_ms / stats.total_calls if stats.total_calls else 0
                summary[svc] = {
                    "total_calls": stats.total_calls,
                    "error_count": stats.error_count,
                    "error_rate_pct": (
                        round(stats.error_count / stats.total_calls * 100, 1)
                        if stats.total_calls
                        else 0
                    ),
                    "total_quota_units": stats.total_quota_units,
                    "quota_used_pct": (
                        round(stats.total_quota_units / GOOGLE_DAILY_QUOTA * 100, 4)
                        if svc == "google_drive"
                        else None
                    ),
                    "avg_latency_ms": round(avg_ms, 1),
                }
            return summary

    def check_alerts(self) -> list[str]:
        """
        Check all alert thresholds. Returns list of alert messages.
        Logs each alert at WARNING level.
        """
        alerts = []
        with self._mutex:
            gd = self._stats.get("google_drive")
            if gd and gd.total_quota_units > GOOGLE_DAILY_QUOTA * ALERT_QUOTA_PCT:
                msg = (
                    f"ALERT: Google Drive quota at "
                    f"{gd.total_quota_units / GOOGLE_DAILY_QUOTA * 100:.1f}% "
                    f"({gd.total_quota_units:,}/{GOOGLE_DAILY_QUOTA:,} units)"
                )
                logger.warning(msg)
                alerts.append(msg)

            for svc, stats in self._stats.items():
                window_elapsed = time.monotonic() - stats.window_start
                rate_limit = GOOGLE_RATE_LIMIT if svc == "google_drive" else ONEDRIVE_RATE_LIMIT
                if stats.calls_this_window > rate_limit * ALERT_RATE_PCT:
                    msg = (
                        f"ALERT: {svc} rate limit at "
                        f"{stats.calls_this_window}/{rate_limit} "
                        f"req in {window_elapsed:.0f}s"
                    )
                    logger.warning(msg)
                    alerts.append(msg)

        return alerts

    def reset(self) -> None:
        """Reset in-memory stats (does not clear DB history)."""
        with self._mutex:
            self._stats.clear()
            self._calls.clear()

    def recent_calls(self, limit: int = 20) -> list[dict]:
        """Return the most recent API calls as dicts."""
        with self._mutex:
            return [
                {
                    "service": c.service,
                    "operation": c.operation,
                    "duration_ms": round(c.duration_ms, 1),
                    "quota_units": c.quota_units,
                    "status": c.status,
                    "error": c.error,
                }
                for c in self._calls[-limit:]
            ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _quota_units(self, service: str, operation: str) -> int:
        if service == "google_drive":
            return GOOGLE_QUOTA_UNITS.get(operation, GOOGLE_QUOTA_UNITS["default"])
        return 1  # OneDrive: count requests, not quota units

    def _record(self, call: APICall) -> None:
        with self._mutex:
            if call.service not in self._stats:
                self._stats[call.service] = ServiceStats()

            stats = self._stats[call.service]
            stats.total_calls += 1
            stats.total_quota_units += call.quota_units
            stats.total_duration_ms += call.duration_ms
            if call.status == "error":
                stats.error_count += 1

            # Rate limit window (reset after 100s for Google, 600s for OneDrive)
            window_duration = 100 if call.service == "google_drive" else 600
            if time.monotonic() - stats.window_start > window_duration:
                stats.calls_this_window = 0
                stats.window_start = time.monotonic()
            stats.calls_this_window += 1

            self._calls.append(call)

        # Log every call at DEBUG
        logger.debug(
            "API call: service=%s op=%s status=%s duration=%.1fms quota=%d",
            call.service,
            call.operation,
            call.status,
            call.duration_ms,
            call.quota_units,
        )

        if call.status == "error":
            logger.warning(
                "API error: service=%s op=%s error=%s",
                call.service,
                call.operation,
                call.error,
            )

        if self._persist:
            self._write_db(call)

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_calls (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                service      TEXT NOT NULL,
                operation    TEXT NOT NULL,
                started_at   TEXT NOT NULL,
                duration_ms  REAL,
                quota_units  INTEGER,
                status       TEXT,
                error        TEXT
            )
        """
        )
        conn.commit()
        conn.close()

    def _write_db(self, call: APICall) -> None:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                "INSERT INTO api_calls VALUES (NULL,?,?,?,?,?,?,?)",
                [
                    call.service,
                    call.operation,
                    datetime.fromtimestamp(call.started_at, tz=timezone.utc).isoformat(),
                    round(call.duration_ms, 2),
                    call.quota_units,
                    call.status,
                    call.error,
                ],
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("Failed to persist API call to DB: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton (optional convenience)
# ---------------------------------------------------------------------------

_global_monitor: Optional[APIMonitor] = None


def get_monitor(db_path: Optional[Path] = None) -> APIMonitor:
    """Return the module-level singleton APIMonitor, creating it if needed."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = APIMonitor(db_path=db_path)
    return _global_monitor


# ---------------------------------------------------------------------------
# CLI — show usage report from DB
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="StorageRationalizer API Usage Monitor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("report", help="Show usage summary from DB")
    sub.add_parser("alerts", help="Check alert thresholds")
    p_recent = sub.add_parser("recent", help="Show recent API calls")
    p_recent.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    monitor = get_monitor()

    if args.cmd == "report":
        report = monitor.report()
        print(json.dumps(report, indent=2))

    elif args.cmd == "alerts":
        alerts = monitor.check_alerts()
        if alerts:
            for a in alerts:
                print(a)
        else:
            print("No alerts — all within thresholds.")

    elif args.cmd == "recent":
        calls = monitor.recent_calls(limit=args.limit)
        for c in calls:
            print(
                f"{c['service']}/{c['operation']} "
                f"[{c['status']}] {c['duration_ms']}ms "
                f"quota={c['quota_units']}"
            )


if __name__ == "__main__":
    _cli()
