# StorageRationalizer Monitoring & Alerting Setup

**Purpose:** Detect security incidents, performance issues, and operational anomalies in real-time.

**Effective Date:** March 9, 2026
**Update Frequency:** Monthly
**Owner:** Operations + Security Team

---

## 1. Monitoring Architecture

```
Application Logs
    ↓
Log Aggregation (local + cloud)
    ↓
Alert Rules (thresholds + patterns)
    ↓
Notification Channels (Slack, email, PagerDuty)
    ↓
Incident Response (manual or automated)
```

---

## 2. Local Logging Setup

### A. Application Logging Configuration

**File:** `config/logging_config.py` (create if doesn't exist)

```python
import logging
import logging.handlers
from pathlib import Path

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()  # Also print to console
    ]
)

# Security-specific logger
security_logger = logging.getLogger("security")
security_handler = logging.FileHandler("logs/security.log")
security_handler.setLevel(logging.WARNING)
security_logger.addHandler(security_handler)

# API logger
api_logger = logging.getLogger("api")
api_handler = logging.FileHandler("logs/api.log")
api_logger.addHandler(api_handler)

# File operations logger
file_logger = logging.getLogger("file_ops")
file_handler = logging.FileHandler("logs/file_operations.log")
file_logger.addHandler(file_handler)
```

### B. Log Files & Rotation

```bash
# Create logs directory
mkdir -p logs

# Set up log rotation (prevents disk full)
# Add to crontab (crontab -e):
0 0 * * * cd ~/Desktop/StorageRationalizer && find logs -name "*.log" -mtime +30 -delete

# Or use Python's RotatingFileHandler:
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler(
    "logs/app.log",
    maxBytes=10485760,  # 10 MB
    backupCount=5       # Keep 5 old files
)
```

---

## 3. Security Events to Monitor

### Critical Events (P1 - Immediate Alert)

| Event | Log Location | Alert Threshold | Action |
|-------|--------------|-----------------|--------|
| Credential decryption failure | logs/security.log | 1+ in 5 min | Page on-call immediately |
| API response validation failure | logs/api.log | 5+ in 5 min | Page on-call immediately |
| Symlink traversal attempt | logs/file_operations.log | 1+ occurrence | Page on-call immediately |
| Command injection attempt | logs/security.log | 1+ occurrence | Page on-call immediately |
| Unauthorized credential access | logs/security.log | 1+ occurrence | Page on-call immediately |

### High Events (P2 - Urgent Alert)

| Event | Log Location | Alert Threshold | Action |
|-------|--------------|-----------------|--------|
| Invalid file path format | logs/file_operations.log | 10+ in 1 hour | Alert on-call within 1 hour |
| API timeout | logs/api.log | 10+ in 1 hour | Alert on-call within 1 hour |
| Permission denied error | logs/file_operations.log | 5+ in 1 hour | Check application permissions |
| Deprecated API usage | logs/api.log | 1+ | Plan migration in next sprint |

### Medium Events (P3 - Daily Summary)

| Event | Log Location | Alert Threshold | Action |
|-------|--------------|-----------------|--------|
| Warning: stale credential | logs/security.log | 1+ | Rotate credential next month |
| Retry on API failure | logs/api.log | 3+ in 1 hour | Check API status |
| File operation slowness | logs/file_operations.log | 5+ sec | Profile and optimize |

---

## 4. Logging Implementation

### A. Credentials Manager Logging

**File:** `tools/credentials_manager.py` (add to existing code)

```python
import logging

logger = logging.getLogger(__name__)

class CredentialManager:
    def get_credential(self, key: str) -> str:
        try:
            # ... existing decryption code ...
            logger.info(f"Credential retrieved: {key[:8]}***")
            return decrypted_value
        except Exception as e:
            logger.critical(f"SECURITY: Credential decryption failed for {key}")
            logger.error(f"Decryption error: {str(e)}")
            raise

    def save_credential(self, key: str, value: str) -> None:
        try:
            # ... existing encryption code ...
            logger.info(f"Credential saved: {key[:8]}***")
        except Exception as e:
            logger.critical(f"SECURITY: Credential encryption failed for {key}")
            raise

    def delete_credential(self, key: str) -> None:
        logger.warning(f"SECURITY: Credential deleted: {key[:8]}***")
        # ... deletion code ...
```

### B. API Validators Logging

**File:** `tools/api_validators.py` (add to existing code)

```python
import logging

logger = logging.getLogger("api")

def validate_restore_response(response: dict) -> bool:
    try:
        # ... existing validation code ...
        if valid:
            logger.info(f"API response valid: {response.get('status')}")
            return True
        else:
            logger.warning(f"SECURITY: API response validation failed: {missing_fields}")
            return False
    except Exception as e:
        logger.critical(f"SECURITY: API validation exception: {str(e)}")
        raise
```

### C. Input Validators Logging

**File:** `tools/input_validators.py` (add to existing code)

```python
import logging

logger = logging.getLogger("file_ops")

def validate_file_path(path: str) -> bool:
    try:
        # ... existing validation code ...
        logger.debug(f"File path validated: {path}")
        return True
    except Exception as e:
        logger.warning(f"SECURITY: Invalid file path rejected: {path}")
        logger.debug(f"Reason: {str(e)}")
        return False

def build_safe_applescript_put_back(file_path: str) -> str:
    if not validate_file_path(file_path):
        logger.critical(f"SECURITY: AppleScript injection attempt blocked: {file_path[:50]}***")
        raise ValueError("Invalid file path")
    # ... rest of function ...
```

---

## 5. Alert Rules (Examples)

### A. Using Simple Log Parsing

**File:** `monitoring/check_alerts.py` (create script)

```python
#!/usr/bin/env python3
import subprocess
from datetime import datetime, timedelta

def check_critical_errors():
    """Check for critical security events in logs."""

    # Check logs from last 5 minutes
    time_threshold = datetime.now() - timedelta(minutes=5)

    # Search for critical events
    critical_patterns = [
        "SECURITY: Credential decryption failed",
        "SECURITY: API response validation failed",
        "SECURITY: AppleScript injection attempt",
        "SECURITY: Command injection",
    ]

    for pattern in critical_patterns:
        result = subprocess.run(
            ["grep", pattern, "logs/security.log"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 1:  # Even 1 match is critical
                print(f"🚨 CRITICAL ALERT: {pattern}")
                print(f"   Occurrences: {len(lines)}")
                print(f"   Last: {lines[-1][:100]}")
                # Send notification (see Section 6)
                send_alert("critical", pattern, len(lines))

def check_high_errors():
    """Check for high-severity events in logs."""

    high_patterns = [
        ("Invalid file path", "logs/file_operations.log", 10),
        ("API timeout", "logs/api.log", 10),
        ("Permission denied", "logs/file_operations.log", 5),
    ]

    for pattern, logfile, threshold in high_patterns:
        result = subprocess.run(
            ["grep", pattern, logfile],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            count = len(result.stdout.strip().split('\n'))
            if count >= threshold:
                print(f"⚠️  HIGH ALERT: {pattern} ({count} occurrences)")
                send_alert("high", pattern, count)

if __name__ == "__main__":
    check_critical_errors()
    check_high_errors()
```

### B. Schedule Alert Checks

```bash
# Add to crontab (crontab -e):

# Check for critical errors every 5 minutes
*/5 * * * * cd ~/Desktop/StorageRationalizer && python3 monitoring/check_alerts.py

# Daily summary
0 9 * * * cd ~/Desktop/StorageRationalizer && python3 monitoring/daily_summary.py
```

---

## 6. Notification Channels

### A. Slack Integration (Recommended)

```python
# File: monitoring/slack_notifier.py

import requests
import os
from datetime import datetime

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")  # Set via GitHub Secrets

def send_slack_alert(severity: str, message: str, details: str = ""):
    """Send alert to Slack channel."""

    color_map = {
        "critical": "#FF0000",  # Red
        "high": "#FFA500",      # Orange
        "medium": "#FFFF00",    # Yellow
    }

    payload = {
        "attachments": [
            {
                "color": color_map.get(severity, "#808080"),
                "title": f"🚨 {severity.upper()}: StorageRationalizer",
                "text": message,
                "fields": [
                    {
                        "title": "Details",
                        "value": details[:500],  # Truncate long details
                        "short": False
                    },
                    {
                        "title": "Time",
                        "value": datetime.now().isoformat(),
                        "short": True
                    }
                ],
                "footer": "StorageRationalizer Security Monitoring"
            }
        ]
    }

    try:
        response = requests.post(SLACK_WEBHOOK, json=payload)
        response.raise_for_status()
        print(f"✅ Slack alert sent: {severity}")
    except Exception as e:
        print(f"❌ Slack alert failed: {e}")

# Usage:
# send_slack_alert("critical", "Credential decryption failed", "5 failures in 5 minutes")
```

### B. Email Alerts

```python
# File: monitoring/email_notifier.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_alert(severity: str, message: str, details: str = ""):
    """Send alert via email."""

    sender = "alerts@company.com"
    recipients = {
        "critical": ["security@company.com", "oncall@company.com"],
        "high": ["security@company.com"],
        "medium": ["dev-team@company.com"],
    }

    # Create email
    msg = MIMEMultipart()
    msg["Subject"] = f"🚨 [{severity.upper()}] StorageRationalizer Alert"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients[severity])

    body = f"""
    Alert: {message}

    Severity: {severity}

    Details:
    {details}

    Time: {datetime.now().isoformat()}

    Action: Check logs and incident response runbook
    Repository: https://github.com/novicehunter/StorageRationalizer
    """

    msg.attach(MIMEText(body, "plain"))

    try:
        # Configure SMTP (example: Gmail)
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login("sender@gmail.com", os.getenv("EMAIL_PASSWORD"))
        server.sendmail(sender, recipients[severity], msg.as_string())
        server.quit()
        print(f"✅ Email alert sent to {recipients[severity]}")
    except Exception as e:
        print(f"❌ Email alert failed: {e}")
```

### C. PagerDuty Integration (Enterprise)

```python
# File: monitoring/pagerduty_notifier.py

import requests
import os
from datetime import datetime

PAGERDUTY_KEY = os.getenv("PAGERDUTY_INTEGRATION_KEY")

def send_pagerduty_alert(severity: str, message: str):
    """Send P1/P2 alerts to PagerDuty for on-call escalation."""

    if severity not in ["critical", "high"]:
        return  # Only P1/P2 to PagerDuty

    payload = {
        "routing_key": PAGERDUTY_KEY,
        "event_action": "trigger",
        "dedup_key": f"storagerationalizer-{int(datetime.now().timestamp())}",
        "payload": {
            "summary": message,
            "severity": "critical" if severity == "critical" else "error",
            "source": "StorageRationalizer Monitoring",
            "timestamp": datetime.now().isoformat(),
            "custom_details": {
                "repository": "https://github.com/novicehunter/StorageRationalizer",
                "runbook": "docs/INCIDENT_RESPONSE_RUNBOOK.md"
            }
        }
    }

    try:
        response = requests.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=payload
        )
        response.raise_for_status()
        print(f"✅ PagerDuty incident created")
    except Exception as e:
        print(f"❌ PagerDuty alert failed: {e}")
```

---

## 7. Dashboard & Reporting

### A. Simple Log Dashboard

**File:** `monitoring/dashboard.html` (optional web view)

```html
<!DOCTYPE html>
<html>
<head>
    <title>StorageRationalizer Monitoring Dashboard</title>
    <style>
        body { font-family: monospace; background: #1e1e1e; color: #0f0; margin: 20px; }
        .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .healthy { background: #0a5f0a; }
        .warning { background: #5f5f00; }
        .critical { background: #5f0a0a; }
        h1 { color: #0f0; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #0f0; padding: 8px; text-align: left; }
        th { background: #0a3a0a; }
    </style>
</head>
<body>
    <h1>StorageRationalizer Security Dashboard</h1>

    <div class="status healthy">
        ✅ All systems operational
    </div>

    <h2>Recent Alerts (Last 24 Hours)</h2>
    <table>
        <tr>
            <th>Time</th>
            <th>Severity</th>
            <th>Event</th>
            <th>Details</th>
        </tr>
        <tr>
            <td id="time1">2026-03-09 10:30:00</td>
            <td id="sev1">HIGH</td>
            <td id="event1">API timeout</td>
            <td id="details1">3 occurrences in 1 hour</td>
        </tr>
    </table>

    <h2>Log Files</h2>
    <ul>
        <li><a href="logs/app.log">app.log</a></li>
        <li><a href="logs/security.log">security.log</a></li>
        <li><a href="logs/api.log">api.log</a></li>
        <li><a href="logs/file_operations.log">file_operations.log</a></li>
    </ul>
</body>
</html>
```

### B. Daily Summary Report

**File:** `monitoring/daily_summary.py`

```python
#!/usr/bin/env python3
import subprocess
from datetime import datetime
from pathlib import Path

def generate_daily_summary():
    """Generate and email daily monitoring summary."""

    summary = f"""
=== StorageRationalizer Daily Security Summary ===
Date: {datetime.now().strftime('%Y-%m-%d')}

--- Log Statistics ---
"""

    for logfile in Path("logs").glob("*.log"):
        line_count = subprocess.run(
            ["wc", "-l", str(logfile)],
            capture_output=True,
            text=True
        ).stdout.split()[0]

        # Count errors
        errors = subprocess.run(
            ["grep", "-i", "error\\|critical\\|warning", str(logfile)],
            capture_output=True,
            text=True
        )
        error_count = len(errors.stdout.strip().split('\n')) if errors.returncode == 0 else 0

        summary += f"\n{logfile.name}:\n"
        summary += f"  Lines: {line_count}\n"
        summary += f"  Errors/Warnings: {error_count}\n"

    summary += f"""

--- Alerts Triggered ---
[Check alert logs here]

--- Action Items ---
1. Review any critical alerts
2. Check API availability
3. Verify credential rotation status

---
Next: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
"""

    print(summary)

    # Email summary
    # send_email_alert("medium", "Daily Summary", summary)

if __name__ == "__main__":
    generate_daily_summary()
```

---

## 8. Metrics to Track

### Performance Metrics
| Metric | Target | Alerting Threshold |
|--------|--------|-------------------|
| API response time | <500ms | >2000ms |
| File operation time | <1s | >5s |
| Credential access latency | <10ms | >50ms |

### Security Metrics
| Metric | Target | Alerting Threshold |
|--------|--------|-------------------|
| Validation failure rate | 0% | >0.1% |
| Credential rotation frequency | Monthly | Overdue by 7 days |
| Test coverage | ≥90% | <85% |
| CVE resolution time | <24h | >48h |

---

## 9. Setup Instructions

### Step 1: Enable Application Logging
```bash
cd ~/Desktop/StorageRationalizer
mkdir -p logs monitoring

# Copy logging config
cp config/logging_config.py . # (Create if doesn't exist)

# Update main application files to use logger
```

### Step 2: Set Up Alert Script
```bash
# Create check_alerts.py (see Section 5.A)
# Test it:
python3 monitoring/check_alerts.py
```

### Step 3: Configure Notifications
```bash
# For Slack:
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# For Email:
export EMAIL_PASSWORD="your-app-password"  # pragma: allowlist secret

# Add to ~/.bashrc or GitHub Secrets for CI/CD
```

### Step 4: Schedule Monitoring
```bash
# Add to crontab:
crontab -e

# Paste:
*/5 * * * * cd ~/Desktop/StorageRationalizer && python3 monitoring/check_alerts.py >> logs/monitoring.log 2>&1
0 9 * * * cd ~/Desktop/StorageRationalizer && python3 monitoring/daily_summary.py
```

### Step 5: Verify Setup
```bash
# Test alert generation:
python3 monitoring/check_alerts.py

# Check cron jobs:
crontab -l

# Verify logs:
ls -la logs/
tail -20 logs/security.log
```

---

## 10. Maintenance & Review

### Weekly
- [ ] Review alert logs
- [ ] Check for any missed events
- [ ] Verify notification channels working

### Monthly
- [ ] Analyze alert patterns
- [ ] Tune alert thresholds if needed
- [ ] Review log rotation settings
- [ ] Update SECURITY_AUDIT_LOG.md

### Quarterly
- [ ] Full monitoring system audit
- [ ] Update alert rules
- [ ] Review dashboard accuracy
- [ ] Test incident response procedures

---

## Quick Reference

```bash
# View recent security logs
tail -50 logs/security.log

# Count critical errors (last 24h)
grep "CRITICAL" logs/security.log | wc -l

# Search for specific event
grep "Credential decryption" logs/security.log

# Generate monitoring report
python3 monitoring/check_alerts.py

# Test Slack alert
python3 -c "from monitoring.slack_notifier import send_slack_alert; send_slack_alert('critical', 'Test alert', 'This is a test')"
```

---

## Sign-Off

**Setup Date:** March 9, 2026
**Next Review:** June 9, 2026
**Owner:** Operations Team

---

## Appendix: Alerting Policy

- **P1 (Critical):** Immediate notification + PagerDuty
- **P2 (High):** Notification within 1 hour
- **P3 (Medium):** Daily summary
- **P4 (Low):** Weekly report

All alerts logged automatically. No manual action required for routing.
