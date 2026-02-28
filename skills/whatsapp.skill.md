# Skill: WhatsApp (Inbound + Outbound)

## Purpose
Handle WhatsApp messages for the AI Employee:
- **Inbound** — detect keyword messages via Playwright/WhatsApp Web → create `/Needs_Action` tasks
- **Outbound** — send approved replies via WhatsApp Business Cloud API → via MCP `send_whatsapp_message`

---

## Two-Channel Architecture

| Channel | Tool | Use Case |
|---------|------|----------|
| **Inbound (read)** | `sentinels/whatsapp_watcher.py` (Playwright) | Monitor personal/business WhatsApp for urgent messages |
| **Outbound (send)** | MCP `send_whatsapp_message` (Business API) | Send approved replies from the business WhatsApp number |

---

## Inbound: WhatsApp Watcher (Playwright)

### How it works
1. Launches headless Chromium with a saved browser session
2. Loads `https://web.whatsapp.com` using stored cookies (no QR scan after setup)
3. Scans unread chat rows for keyword matches
4. Writes `/Needs_Action/YYYY-MM-DD_whatsapp_<sender>.md` task files
5. Claude reads the task, drafts a reply, moves draft to `/Pending_Approval/`

### Keywords monitored
`urgent`, `asap`, `invoice`, `payment`, `help`, `problem`, `issue`

### First-time setup (QR scan)
```bash
python sentinels/whatsapp_watcher.py --setup
```
- Browser opens → scan QR with phone → session saved to `.claude/whatsapp_session/`
- After setup, all subsequent runs are headless

### Session renewal
If watcher times out (session expired), re-run setup:
```bash
python sentinels/whatsapp_watcher.py --setup
```

### Running manually
```bash
# Run once (headless)
python sentinels/whatsapp_watcher.py

# Run in a polling loop (every 30s)
python sentinels/whatsapp_watcher.py --loop
```

### Scheduler
Runs automatically every 5 minutes via `sentinels/scheduler.py` (`job_check_whatsapp`).

---

## Outbound: WhatsApp Business Cloud API (MCP)

### Setup
1. Create a Meta Business app at https://developers.facebook.com/
2. Add the WhatsApp product to your app
3. Get a Phone Number ID and permanent System User token
4. Add to `.env`:
```
WHATSAPP_API_TOKEN=your_system_user_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_RECIPIENT=+447911123456   # default reply-to number
```

### Using the MCP tool (via Claude)
Only call `send_whatsapp_message` AFTER a reply has been approved in `/Approved/`:
```
Tool: send_whatsapp_message
Args:
  to: "+447911123456"
  message: "Hi [Name], thank you for reaching out..."
```

---

## Domain
**Personal** for personal chats → log in `/Logs/personal/`
**Business** for client/supplier chats → log in `/Logs/`

When in doubt → move task to `/Needs_Action` for human review.

---

## Workflow: Inbound → Reply

```
WhatsApp message (keyword detected)
  ↓
/Needs_Action/YYYY-MM-DD_whatsapp_<sender>.md    (created by watcher)
  ↓ Claude reads, drafts reply
/Pending_Approval/YYYY-MM-DD_whatsapp_reply_<sender>.md
  ↓ Human approves (moves to /Approved/)
send_whatsapp_message MCP tool
  ↓
/Done/  (task moved after send)
Logs/YYYY-MM-DD_whatsapp_sent.md  (logged automatically)
```

---

## Rules of Engagement

- **Never** send a WhatsApp reply without explicit human approval in `/Approved/`
- Payment requests > $500 → flag in `/Needs_Action` with `priority: critical`
- Tone: warm, professional — see `Company_Handbook.md`
- Personal messages (family/friends) → handle with extra care, tag `domain: personal`

---

## Status Check

```bash
# Check if session is valid (headless run)
python sentinels/whatsapp_watcher.py

# Check env vars
python -c "
from dotenv import load_dotenv; import os; load_dotenv('.env')
for k in ['WHATSAPP_SESSION_PATH','WHATSAPP_API_TOKEN','WHATSAPP_PHONE_NUMBER_ID']:
    v = os.getenv(k,'MISSING')
    print(k, ':', 'SET' if v and 'your_' not in v else 'NEEDS SETUP', '('+v[:30]+')')
"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Chat list not found — session may need renewal` | Session expired | Run `--setup` again |
| `WhatsApp Web timed out` | Network or session issue | Re-run `--setup` |
| `WHATSAPP_API_TOKEN not set` | Placeholder in .env | Add real token from Meta dashboard |
| No task files created | No keyword matches | Normal — no action needed |
| `ERROR: Run: pip install playwright` | Missing dependency | `pip install playwright && playwright install chromium` |
