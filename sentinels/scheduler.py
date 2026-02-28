"""
Master Scheduler
================
Runs all AI Employee sentinels on a cron-like schedule.
This is the single process to keep running for always-on operation.

Schedule (default):
  Every 5 min  — Gmail watcher (check for new emails)
  Every 10 min — LinkedIn poster (publish approved posts)
  Every 1 min  — File watcher heartbeat (log vault state)
  Monday 9 AM  — Queue weekly CEO briefing task
  Monday 9 AM  — Queue weekly LinkedIn post task
  Every hour   — Check work remaining (Ralph Wiggum gate)

Usage:
    python sentinels/scheduler.py          # run scheduler (blocking)
    python sentinels/scheduler.py --once   # run all jobs once and exit

Register as a Windows background service:
    See scripts/setup_scheduler.ps1
"""

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

try:
    import schedule
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: Run: pip install schedule python-dotenv")
    sys.exit(1)

import time

VAULT_ROOT = Path(__file__).parent.parent
SENTINELS = VAULT_ROOT / "sentinels"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_script(script: str, *args):
    """Run a sentinel script in a subprocess."""
    cmd = [sys.executable, str(SENTINELS / script)] + list(args)
    print(f"[{_now()}] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(VAULT_ROOT))
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"  {line}")
    if result.returncode != 0 and result.stderr.strip():
        print(f"  ERROR: {result.stderr.strip()[:200]}")


# ── Job definitions ───────────────────────────────────────────────────────────

def job_check_gmail():
    _run_script("gmail_watcher.py")


def job_publish_linkedin():
    _run_script("linkedin_poster.py", "--watch")


def job_file_watcher_heartbeat():
    """Log vault inbox count as a heartbeat."""
    inbox = VAULT_ROOT / "Inbox"
    count = len(list(inbox.glob("*.md"))) if inbox.exists() else 0
    if count > 0:
        print(f"[{_now()}] Heartbeat: {count} item(s) in /Inbox — run `claude` to process")
    else:
        print(f"[{_now()}] Heartbeat: vault idle")


def job_weekly_briefing():
    """Monday 9 AM — queue the weekly CEO briefing."""
    from pathlib import Path
    from datetime import date
    inbox = VAULT_ROOT / "Inbox"
    inbox.mkdir(exist_ok=True)
    today = date.today().isoformat()
    fname = f"{today}_weekly-ceo-briefing.md"
    task = inbox / fname
    if not task.exists():
        task.write_text(
            f"# Task: Weekly CEO Briefing\n\n"
            f"> Status: **New**\n"
            f"> Created: {today}\n"
            f"> Priority: High\n"
            f"> Owner: --\n"
            f"> Type: scheduled_briefing\n\n"
            f"---\n\n"
            f"## Description\n\nGenerate the weekly CEO briefing using `ceo_briefing.generate` skill.\n\n"
            f"## Acceptance Criteria\n\n"
            f"- [ ] Briefing file created in /Briefings/\n"
            f"- [ ] Trust ledger updated\n"
            f"- [ ] Dashboard refreshed\n",
            encoding="utf-8",
        )
        print(f"[{_now()}] Queued weekly briefing task → {fname}")


def job_weekly_linkedin_post():
    """Monday 9 AM — queue a LinkedIn post for business promotion."""
    _run_script("linkedin_poster.py", "--draft")


def job_check_odoo():
    """Check Odoo for overdue invoices and new orders."""
    _run_script("odoo_watcher.py")


def job_check_social_media():
    """Check Facebook comments and Twitter mentions."""
    _run_script("social_media_watcher.py")


def job_autonomous_briefing():
    """Sunday 23:00 — run the autonomous Monday Morning CEO briefing generator."""
    _run_script("generate_weekly_briefing.py")


def job_weekly_audit():
    """Monday 9 AM — queue the full weekly business + accounting audit."""
    from pathlib import Path
    from datetime import date
    inbox = VAULT_ROOT / "Inbox"
    inbox.mkdir(exist_ok=True)
    today = date.today().isoformat()
    fname = f"{today}_weekly-business-audit.md"
    task = inbox / fname
    if not task.exists():
        task.write_text(
            f"# Task: Weekly Business & Accounting Audit\n\n"
            f"> Status: **New**\n"
            f"> Created: {today}\n"
            f"> Priority: High\n"
            f"> Owner: --\n"
            f"> Type: weekly_audit\n\n---\n\n"
            f"## Description\n\n"
            f"Generate the weekly business and accounting audit using `weekly_audit.generate` skill.\n"
            f"Pull data from Odoo (financials), social media (reach/engagement), and vault (operations).\n\n"
            f"## Acceptance Criteria\n\n"
            f"- [ ] Audit file created in /Briefings/\n"
            f"- [ ] Odoo accounting data included (or graceful degradation note)\n"
            f"- [ ] Social media summary included (or graceful degradation note)\n"
            f"- [ ] Decisions Needed section populated\n"
            f"- [ ] Trust ledger updated\n"
            f"- [ ] Dashboard refreshed\n",
            encoding="utf-8",
        )
        print(f"[{_now()}] Queued weekly audit task -> {fname}")


def job_check_whatsapp():
    """Check WhatsApp Web for new keyword messages (Playwright)."""
    _run_script("whatsapp_watcher.py")


def job_check_finance():
    """Check bank CSV files or Plaid API for new transactions."""
    _run_script("finance_watcher.py")


def job_sync_dashboard():
    """Sync Dashboard.md metrics into dashboard.html."""
    _run_script("dashboard_sync.py")


def job_check_work_remaining():
    """Hourly check — log if work is pending."""
    result = subprocess.run(
        [sys.executable, str(SENTINELS / "check_work_remaining.py")],
        capture_output=True, text=True, cwd=str(VAULT_ROOT)
    )
    if result.returncode != 0:
        print(f"[{_now()}] PENDING WORK DETECTED:")
        for line in result.stdout.strip().splitlines():
            print(f"  {line}")
        print(f"  >> Run `claude` in the vault directory to process")


# ── Scheduler setup ───────────────────────────────────────────────────────────

def setup_schedule():
    schedule.every(5).minutes.do(job_check_gmail)
    schedule.every(5).minutes.do(job_check_whatsapp)
    schedule.every(10).minutes.do(job_publish_linkedin)
    schedule.every(15).minutes.do(job_check_social_media)
    schedule.every(30).minutes.do(job_check_odoo)
    schedule.every(1).hours.do(job_check_finance)
    schedule.every(1).minutes.do(job_file_watcher_heartbeat)
    schedule.every(5).minutes.do(job_sync_dashboard)
    schedule.every().hour.do(job_check_work_remaining)
    schedule.every().sunday.at("23:00").do(job_autonomous_briefing)
    schedule.every().monday.at("09:00").do(job_weekly_briefing)
    schedule.every().monday.at("09:00").do(job_weekly_audit)
    schedule.every().monday.at("09:05").do(job_weekly_linkedin_post)

    print("Schedule registered:")
    print("  Every  5 min  — Gmail check")
    print("  Every  5 min  — WhatsApp check (Playwright / WhatsApp Web)")
    print("  Every 10 min  — LinkedIn publish approved posts")
    print("  Every 15 min  — Social media mentions (FB/Twitter)")
    print("  Every 30 min  — Odoo events (overdue invoices, new orders)")
    print("  Every  1 hr   — Finance / bank transactions")
    print("  Every  1 min  — Heartbeat")
    print("  Every  5 min  — Dashboard sync (MD -> HTML)")
    print("  Every  1 hr   — Work remaining check (Ralph Wiggum)")
    print("  Sunday  23:00 — Autonomous Monday briefing (reads Goals+Done+Bank)")
    print("  Monday 09:00  — Queue weekly CEO briefing (Claude-driven)")
    print("  Monday 09:00  — Queue weekly business audit")
    print("  Monday 09:05  — Queue LinkedIn post")


def run_all_once():
    """Run every job once, ignoring schedule times."""
    print(f"[{_now()}] Running all jobs once...\n")
    job_file_watcher_heartbeat()
    job_check_gmail()
    job_check_whatsapp()
    job_check_odoo()
    job_check_social_media()
    job_check_finance()
    job_publish_linkedin()
    job_check_work_remaining()
    print(f"\n[{_now()}] Done.")


def main():
    load_dotenv(VAULT_ROOT / ".env")

    if "--once" in sys.argv:
        run_all_once()
        return

    print(f"[AI Employee Scheduler] Starting — {_now()}")
    print(f"Vault: {VAULT_ROOT}\n")
    setup_schedule()
    print("\nScheduler running. Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
