# PRD: Instagram Auto-Comment Bot
**Version:** 2.0  
**Stack:** Python · instagrapi · Supabase · GitHub Actions  
**Deployment:** GitHub Actions (public repo, free tier) + Supabase (free tier)

---

## 1. Overview

A lightweight Python automation that monitors a configurable list of Instagram accounts for new posts and reels, and automatically posts a randomized comment from the user's Instagram account. Runs every 30 minutes via GitHub Actions cron schedule at zero cost.

---

## 2. Problem Statement

Manually checking Instagram accounts and leaving comments is time-consuming and easy to forget. This tool automates the process reliably and runs 24/7 in the cloud without any server costs.

---

## 3. Goals

- Monitor N target Instagram accounts for new posts/reels
- Auto-comment from the user's account when a new post is detected
- Never double-comment on the same post
- Run every 30 minutes, 24/7, for free
- Be configurable without touching code (just edit a config file)
- Avoid bot detection through randomized comments, delays, and frequency caps

---

## 4. Non-Goals (Out of Scope)

- No UI or dashboard
- No DM automation
- No liking or following automation
- No support for multiple commenting accounts
- No story monitoring
- No analytics or reporting

---

## 5. Tech Stack

| Layer | Tool | Reason |
|---|---|---|
| Language | Python 3.11 | instagrapi is Python-native |
| Instagram API | `instagrapi` | Best maintained unofficial IG library |
| Database | Supabase (PostgreSQL) | Free tier, cloud-native, no infra |
| Scheduler | GitHub Actions cron | Free unlimited mins on public repo |
| Config | `config.yaml` | Human-editable, no code changes needed |
| Secrets | GitHub Actions Secrets | Secure credential storage |
| Logging | Python `logging` + stdout | Visible in GitHub Actions run logs |
| Notifications | Discord/Slack Webhook (optional) | Alert on failures without checking logs |

---

## 6. Repository Structure

```
instagram-autocomment-bot/
├── .github/
│   └── workflows/
│       └── bot.yml              # GitHub Actions cron workflow
├── bot/
│   ├── __init__.py
│   ├── main.py                  # Entry point
│   ├── instagram.py             # instagrapi login, fetch, comment logic
│   ├── database.py              # Supabase read/write logic
│   ├── session_manager.py       # Session persistence via Supabase
│   ├── notifier.py              # Discord/Slack webhook notifications
│   ├── config.py                # Config loader
│   └── logger.py                # Logging setup
├── config.yaml                  # User-editable settings
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 7. Configuration (`config.yaml`)

This is the only file the user needs to edit to change behavior.

```yaml
# Instagram accounts to monitor
target_accounts:
  - username: "account_one"
    comments:  # Bot picks one at random per post
      - "Great post! 🔥"
      - "This is awesome! 💪"
      - "Love this content!"
  - username: "account_two"
    comments:
      - "Amazing content as always!"
      - "This is incredible! 🙌"
      - "Always delivering quality 💯"
  - username: "account_three"
    comments:
      - "Love this! 💯"
      - "So good! 🔥"
      - "Absolutely fire content!"

# How many recent posts to check per account per run
posts_to_check: 5

# Maximum comments to post per account in a single run
# Prevents burst-commenting if an account posts multiple times at once
max_comments_per_account_per_run: 2

# Delay between consecutive comments (seconds) - randomized between min and max
comment_delay:
  min: 30
  max: 90

# Only comment on posts newer than this many hours
max_post_age_hours: 24

# Delete seen_posts records older than this many days (keeps DB clean)
seen_posts_retention_days: 30

# Set to true to run without actually posting comments (for testing)
dry_run: false
```

---

## 8. Environment Variables (GitHub Secrets)

These must be set in the GitHub repo under **Settings → Secrets → Actions**:

| Secret Name | Description |
|---|---|
| `IG_USERNAME` | Instagram username (no @) |
| `IG_PASSWORD` | Instagram password |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |
| `DISCORD_WEBHOOK_URL` | *(Optional)* Discord webhook URL for failure alerts |

---

## 9. Database Schema (Supabase)

Run this SQL in the Supabase SQL editor to create the required tables:

```sql
-- Tracks which posts have already been commented on
CREATE TABLE seen_posts (
  post_id       TEXT PRIMARY KEY,
  account       TEXT NOT NULL,
  commented_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Stores the instagrapi session JSON for persistence across ephemeral runners
CREATE TABLE bot_sessions (
  id            TEXT PRIMARY KEY DEFAULT 'default',
  session_data  JSONB NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at on bot_sessions whenever a row is upserted
CREATE OR REPLACE FUNCTION update_bot_sessions_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bot_sessions_updated_at
  BEFORE UPDATE ON bot_sessions
  FOR EACH ROW
  EXECUTE FUNCTION update_bot_sessions_timestamp();

-- Index for efficient cleanup of old seen_posts records
CREATE INDEX idx_seen_posts_commented_at ON seen_posts (commented_at);
```

---

## 10. Functional Requirements

### FR-1: Instagram Login & Session Persistence

> **Critical:** GitHub Actions runners are ephemeral — every run gets a fresh container. Storing `session.json` locally will NOT persist. Sessions must be stored in Supabase.

- On run start, attempt to load session from Supabase `bot_sessions` table
- If a valid session exists, inject it into the `instagrapi.Client` via `cl.set_settings(session_data)`
- If the session is expired or missing, perform a fresh login using `IG_USERNAME` and `IG_PASSWORD`
- After successful login (fresh or resumed), save the updated session back to Supabase via upsert
- Handle `ChallengeRequired` — see FR-7

### FR-2: Fetch Recent Posts Per Target Account

- For each `target_accounts` entry in `config.yaml`:
  - Resolve username → user ID via `cl.user_id_from_username()`
  - Fetch last N posts/reels via `cl.user_medias(user_id, amount=posts_to_check)`
  - Filter out posts older than `max_post_age_hours`
  - Both feed posts and reels must be included (media types: `Photo`, `Video`, `Album`)

### FR-3: Duplicate Prevention

- Before commenting on any post, check Supabase `seen_posts` table for `post_id`
- If found → skip silently
- If not found → proceed to comment, then insert into `seen_posts`

### FR-4: Comment Posting

- Pick a random comment from the account's `comments` list (not a single hardcoded string)
- Use `cl.media_comment(media_id, comment_text)`
- After each comment, sleep for a random duration between `comment_delay.min` and `comment_delay.max` seconds
- Respect `max_comments_per_account_per_run` — stop commenting on an account once the cap is reached, even if more new posts exist
- Log success with post ID, target account name, and the comment used
- If `dry_run` is `true`, log what would be commented but skip the actual API call

### FR-5: Error Handling

- Wrap all Instagram API calls in try/except
- On `LoginRequired` → attempt re-login once, then abort the entire run with error
- On `MediaNotFound` → skip that post, continue
- On `ClientError` (rate limit) → log warning, **abort the entire run** (let the next cron run 30 min later handle remaining work — do NOT retry within the same run to avoid extending rate-limit windows)
- On Supabase errors → log error, skip DB write (do not crash the full run)
- Always process all target accounts even if one fails (except on rate limit or challenge — see below)

### FR-6: Logging

- Use Python `logging` with level `INFO` by default
- Log format: `[TIMESTAMP] [LEVEL] message`
- Log each run start with timestamp and number of target accounts
- Log each new post found, comment attempted, comment success/failure
- Log when `dry_run` mode is active (clearly indicate no comments will be posted)
- Log run summary at end: X accounts checked, Y new posts found, Z comments posted

### FR-7: Challenge Handling (Critical)

When Instagram raises `ChallengeRequired`:
- Log the challenge type and challenge URL (if available from the exception)
- **Immediately stop all commenting** — do NOT continue processing other accounts
- Send a notification via the configured webhook (see FR-8) with the message: "⚠️ Instagram challenge required — manual intervention needed"
- Exit with a non-zero exit code so GitHub Actions marks the run as failed

### FR-8: Failure Notifications (Optional)

If `DISCORD_WEBHOOK_URL` is set:
- Send a webhook message on: `ChallengeRequired`, rate-limit hit, login failure, or 3+ consecutive account failures in a single run
- Message should include: timestamp, failure type, and any relevant details
- If the webhook itself fails, log the error and continue (do not crash)
- If `DISCORD_WEBHOOK_URL` is not set, skip notification silently (no error)

### FR-9: Database Cleanup

At the start of each run (before processing accounts):
- Delete rows from `seen_posts` where `commented_at` is older than `seen_posts_retention_days`
- Log how many stale records were cleaned up
- This prevents unbounded table growth on the free Supabase tier

---

## 11. GitHub Actions Workflow (`.github/workflows/bot.yml`)

```yaml
name: Instagram Auto-Comment Bot

on:
  schedule:
    - cron: '*/30 * * * *'   # Every 30 minutes
  workflow_dispatch:           # Allow manual trigger from GitHub UI

jobs:
  run-bot:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run bot
        env:
          IG_USERNAME: ${{ secrets.IG_USERNAME }}
          IG_PASSWORD: ${{ secrets.IG_PASSWORD }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python -m bot.main
```

> **Note on action version pinning:** For production use, consider pinning actions to full commit SHAs instead of version tags (e.g., `actions/checkout@<sha>`) to prevent supply-chain attacks. This is especially important since the repo must be public to get free Actions minutes.

---

## 12. `requirements.txt`

```
instagrapi==2.7.20   # Latest stable as of June 2026 — check PyPI before building
supabase==2.4.0
PyYAML==6.0.1
requests==2.32.3     # For Discord webhook notifications
```

---

## 13. Module Specs

### `bot/config.py`
- Load `config.yaml` using PyYAML
- Expose a single `Config` dataclass with typed fields
- Validate that each target account has at least one comment in its `comments` list
- Validate `max_comments_per_account_per_run >= 1`
- Raise a clear error if required fields are missing

### `bot/database.py`
- `is_seen(post_id: str) -> bool` — query Supabase for post_id
- `mark_seen(post_id: str, account: str) -> None` — insert row into seen_posts
- `cleanup_old_records(retention_days: int) -> int` — delete records older than N days, return count deleted
- Initialize Supabase client from env vars on import

### `bot/session_manager.py`
- `load_session() -> dict | None` — fetch session JSON from `bot_sessions` table
- `save_session(session_data: dict) -> None` — upsert session JSON into `bot_sessions` table
- Handles the case where no session exists yet (first run)

### `bot/instagram.py`
- `login(username, password) -> Client` — load session from Supabase first; fresh login only if needed; save session back after login
- `get_new_posts(client, username, count, max_age_hours) -> list[Media]` — fetch and filter posts
- `post_comment(client, media_id, comment) -> bool` — comment with error handling
- On `ChallengeRequired` → raise a custom `ChallengeError` so `main.py` can handle it

### `bot/notifier.py`
- `send_alert(message: str) -> None` — POST to Discord webhook if `DISCORD_WEBHOOK_URL` is set
- Fail silently if webhook URL is not configured or request fails

### `bot/main.py`
- Entry point: cleanup old records → load config → login → for each target account → get new posts → check DB → comment (up to cap) → mark seen
- On `ChallengeError` → send notification, abort all remaining work, exit with code 1
- On rate-limit `ClientError` → send notification, abort all remaining work, exit with code 1
- In `dry_run` mode, log all actions but skip actual API comment calls
- Print run summary at end

---

## 14. Anti-Ban Measures (Required)

These must be implemented — skipping them risks account restriction:

| Measure | Implementation |
|---|---|
| Randomized comments | Pick from a list of variants per account, never repeat the same string |
| Random delay between comments | `random.uniform(min, max)` sleep (default 30–90s) |
| Session reuse via Supabase | Avoid fresh login every run — reuse session across ephemeral runners |
| Max post age filter | Skip old posts to avoid burst commenting |
| Per-account comment cap | `max_comments_per_account_per_run` (default 2) |
| Low post check count | Only check last 5 posts per account |
| Single account only | No parallel comment threads |
| Conservative schedule | 30-min intervals (not faster) |
| Abort on rate limit | Stop immediately, let next cron run handle the rest |

---

## 15. Privacy & Public Repo Considerations

Since the repo must be public for free GitHub Actions minutes:

- **Never commit credentials** — all secrets go through GitHub Actions Secrets
- **`config.yaml` is public** — target account usernames and comment texts will be visible to anyone
- **Alternative:** If privacy is needed, move the config to a Supabase table (`bot_config`) and load it at runtime instead of from a file. This keeps target lists private.
- **`session.json` must never exist in the repo** — sessions are stored in Supabase, not as files

---

## 16. `.gitignore`

```
*.pyc
__pycache__/
.env
```

---

## 17. README (outline for the agent to generate)

- Project description
- Setup steps:
  1. Fork repo
  2. Add GitHub Secrets (`IG_USERNAME`, `IG_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY`, optionally `DISCORD_WEBHOOK_URL`)
  3. Run SQL schema in Supabase
  4. Edit `config.yaml` with target accounts and comments
  5. Push — bot starts automatically on cron
- How to edit `config.yaml`
- How to use `dry_run` mode for testing
- How to trigger manually from GitHub Actions UI
- How to set up Discord notifications
- Disclaimer about Instagram ToS

---

## 18. Known Risks

| Risk | Mitigation |
|---|---|
| Instagram detects bot activity | Random delays, randomized comments, session reuse, per-account caps |
| Account gets restricted | Start with 1-2 targets, not 10+. Use `dry_run` first. |
| Challenge/2FA triggered | Notification alert, manual intervention, bot auto-pauses |
| instagrapi breaks after IG update | Pin version in requirements.txt, monitor repo issues |
| GitHub cron has up to 15min delay | Acceptable for this use case |
| Supabase free tier limits | 500MB DB, 50k rows — more than sufficient. Cleanup job prevents unbounded growth. |
| Public repo exposes config | Move config to Supabase table if privacy is needed |

---

## 19. Acceptance Criteria

- [ ] Bot runs end-to-end without errors on a fresh GitHub Actions run
- [ ] Comments appear on target accounts' new posts within 1 hour of posting
- [ ] Comments are randomly selected from the configured list (not always the same)
- [ ] Same post is never commented on twice
- [ ] Session is persisted in Supabase and reused across runs (no fresh login every time)
- [ ] All secrets are injected via env vars — zero hardcoded credentials
- [ ] Bot continues processing remaining accounts if one account fails
- [ ] Bot stops immediately on rate-limit or challenge and sends a notification
- [ ] `dry_run` mode logs all actions without posting any comments
- [ ] Old `seen_posts` records are cleaned up automatically
- [ ] GitHub Actions run logs clearly show what happened each run
- [ ] Discord notification is received on critical failures (when webhook is configured)
