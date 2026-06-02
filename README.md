# 🤖 Instagram Auto-Comment Bot

A lightweight Python automation that monitors Instagram accounts for new posts and reels, and automatically posts a randomized comment from your account. Runs every 30 minutes via GitHub Actions — completely free.

## Features

- 🔄 **Automatic monitoring** — checks target accounts every 30 minutes
- 💬 **Randomized comments** — picks from a pool of variants per account to avoid detection
- 🛡️ **Anti-ban measures** — random delays, per-account caps, session reuse
- 🗄️ **Duplicate prevention** — never comments on the same post twice (Supabase-backed)
- 🔔 **Failure alerts** — optional Discord notifications on critical errors
- 🧪 **Dry-run mode** — test the full flow without posting real comments
- ☁️ **Zero cost** — runs on GitHub Actions (public repo) + Supabase free tier

## Quick Setup

### 1. Fork this repo

Click **Fork** on GitHub to create your own copy.

### 2. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a free project
2. Open the **SQL Editor** and run the following:

```sql
-- Tracks which posts have already been commented on
CREATE TABLE seen_posts (
  post_id       TEXT PRIMARY KEY,
  account       TEXT NOT NULL,
  commented_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Stores the instagrapi session for persistence across runs
CREATE TABLE bot_sessions (
  id            TEXT PRIMARY KEY DEFAULT 'default',
  session_data  JSONB NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at on session upsert
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

-- Index for efficient cleanup
CREATE INDEX idx_seen_posts_commented_at ON seen_posts (commented_at);
```

3. Copy your **Project URL** and **anon key** from **Settings → API**

### 3. Add GitHub Secrets

Go to your forked repo → **Settings → Secrets and variables → Actions** → **New repository secret**:

| Secret Name | Value |
|---|---|
| `IG_USERNAME` | Your Instagram username (no @) |
| `IG_PASSWORD` | Your Instagram password |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon key |
| `DISCORD_WEBHOOK_URL` | *(Optional)* Discord webhook for failure alerts |

### 4. Edit `config.yaml`

Replace the placeholder accounts with the accounts you want to monitor:

```yaml
target_accounts:
  - username: "some_account"
    comments:
      - "Great post! 🔥"
      - "This is awesome! 💪"
      - "Love this content!"
```

> **Tip:** Use at least 3 comment variants per account to look more natural.

### 5. Push & go

Commit your changes and push. The bot will start running automatically every 30 minutes.

To trigger a manual run: go to **Actions** → **Instagram Auto-Comment Bot** → **Run workflow**.

## Configuration Reference

| Setting | Default | Description |
|---|---|---|
| `target_accounts` | — | List of accounts to monitor, each with a `comments` pool |
| `posts_to_check` | `5` | How many recent posts to check per account per run |
| `max_comments_per_account_per_run` | `2` | Cap on comments per account per run (anti-ban) |
| `comment_delay.min` | `30` | Minimum seconds to wait between comments |
| `comment_delay.max` | `90` | Maximum seconds to wait between comments |
| `max_post_age_hours` | `24` | Ignore posts older than this |
| `seen_posts_retention_days` | `30` | Auto-delete DB records older than this |
| `dry_run` | `false` | Set to `true` to test without posting comments |

## Dry-Run Mode

To test without posting real comments, set `dry_run: true` in `config.yaml`. The bot will:

- Log in to Instagram normally
- Fetch posts and check the database
- Log what it *would* comment, but skip the actual API call
- Still mark posts as "seen" to test the full flow

## Discord Notifications

If you set the `DISCORD_WEBHOOK_URL` secret, the bot will send alerts when:

- ⚠️ Instagram requires a challenge (2FA / captcha)
- 🚫 Rate limit is hit
- ❌ Login fails
- ⚠️ 3+ consecutive account failures in one run

To create a webhook: **Discord → Server Settings → Integrations → Webhooks → New Webhook**

## Anti-Ban Measures

The bot implements multiple safeguards to minimize detection risk:

- **Randomized comments** — never posts the same string every time
- **Random delays** — 30–90 second wait between comments
- **Session reuse** — avoids fresh login every run (session stored in Supabase)
- **Post age filter** — only comments on recent posts
- **Per-account cap** — max 2 comments per account per run
- **Conservative schedule** — 30-minute intervals

> **Recommendation:** Start with 1–2 target accounts and gradually increase. Don't monitor 10+ accounts from day one.

## ⚠️ Disclaimer

This tool interacts with Instagram's private API via the [instagrapi](https://github.com/subzeroid/instagrapi) library, which is against Instagram's Terms of Service. Use at your own risk. The authors are not responsible for any account restrictions, bans, or other consequences.
