"""Entry point for the Instagram Auto-Comment Bot.

Orchestrates: config → login → cleanup → fetch → check DB → comment → summary.
"""

from __future__ import annotations

import os
import random
import sys
import time

from instagrapi.exceptions import ClientError, LoginRequired

from bot.config import load_config
from bot.database import cleanup_old_records, is_seen, mark_seen
from bot.instagram import ChallengeError, get_new_posts, login, post_comment
from bot.logger import log
from bot.notifier import send_alert


def main() -> None:
    """Run a single bot cycle."""

    # ------------------------------------------------------------------
    # 1. Load configuration
    # ------------------------------------------------------------------
    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)

    if config.dry_run:
        log.info("*** DRY RUN MODE — no comments will be posted ***")

    log.info(
        "=== Bot run started | %d target account(s) | dry_run=%s ===",
        len(config.target_accounts),
        config.dry_run,
    )

    # ------------------------------------------------------------------
    # 2. Clean up old seen_posts records (FR-9)
    # ------------------------------------------------------------------
    cleanup_old_records(config.seen_posts_retention_days)

    # ------------------------------------------------------------------
    # 3. Instagram login (FR-1)
    # ------------------------------------------------------------------
    ig_username = os.environ.get("IG_USERNAME", "")
    ig_password = os.environ.get("IG_PASSWORD", "")
    if not ig_username or not ig_password:
        log.error("IG_USERNAME and IG_PASSWORD must be set as environment variables")
        sys.exit(1)

    try:
        client = login(ig_username, ig_password)
    except ChallengeError as exc:
        log.error("Challenge required during login: %s", exc)
        send_alert(
            f"⚠️ **Instagram challenge required** — manual intervention needed.\n"
            f"Challenge URL: {exc.challenge_url or 'N/A'}"
        )
        sys.exit(1)
    except LoginRequired as exc:
        log.error("Login failed: %s", exc)
        send_alert(f"❌ **Instagram login failed**: {exc}")
        sys.exit(1)
    except Exception as exc:
        log.error("Unexpected login error: %s", exc)
        send_alert(f"❌ **Unexpected login error**: {exc}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. Process each target account
    # ------------------------------------------------------------------
    total_checked = 0
    total_new = 0
    total_commented = 0
    consecutive_failures = 0

    for target in config.target_accounts:
        account = target.username
        log.info("--- Processing @%s ---", account)
        total_checked += 1

        try:
            posts = get_new_posts(
                client,
                account,
                config.posts_to_check,
                config.max_post_age_hours,
            )
        except Exception as exc:
            log.error("Failed to fetch posts for @%s: %s", account, exc)
            consecutive_failures += 1
            if consecutive_failures >= 3:
                send_alert(
                    f"⚠️ **3+ consecutive account failures** in this run.\n"
                    f"Last error on @{account}: {exc}"
                )
            continue

        if not posts:
            log.info("No new posts for @%s", account)
            consecutive_failures = 0  # Reset on successful fetch
            continue

        # Track per-account comment count for the cap
        comments_this_account = 0

        for post in posts:
            post_id = str(post.pk)

            # Duplicate check (FR-3)
            if is_seen(post_id):
                log.debug("Post %s already seen — skipping", post_id)
                continue

            total_new += 1

            # Per-account cap (anti-ban)
            if comments_this_account >= config.max_comments_per_account_per_run:
                log.info(
                    "Reached comment cap (%d) for @%s — skipping remaining posts",
                    config.max_comments_per_account_per_run,
                    account,
                )
                break

            # Pick a random comment variant
            comment_text = random.choice(target.comments)

            if config.dry_run:
                log.info(
                    "[DRY RUN] Would comment on post %s by @%s: \"%s\"",
                    post_id,
                    account,
                    comment_text,
                )
                mark_seen(post_id, account)
                total_commented += 1
                comments_this_account += 1
                continue

            # Post the comment (FR-4)
            try:
                success = post_comment(client, post_id, comment_text)
            except ChallengeError as exc:
                # FR-7: Abort immediately on challenge
                log.error("Challenge triggered while commenting: %s", exc)
                send_alert(
                    f"⚠️ **Instagram challenge required** during commenting.\n"
                    f"Post: {post_id} | Account: @{account}\n"
                    f"Challenge URL: {exc.challenge_url or 'N/A'}"
                )
                sys.exit(1)
            except ClientError as exc:
                # FR-5: Rate limit — abort entire run
                log.error("Rate limit hit — aborting run: %s", exc)
                send_alert(
                    f"🚫 **Rate limit hit** — bot run aborted.\n"
                    f"Post: {post_id} | Account: @{account}\n"
                    f"Error: {exc}"
                )
                sys.exit(1)

            if success:
                mark_seen(post_id, account)
                total_commented += 1
                comments_this_account += 1
                log.info(
                    "✅ Commented on post %s by @%s: \"%s\"",
                    post_id,
                    account,
                    comment_text,
                )

                # Random delay between comments (anti-ban)
                delay = random.uniform(
                    config.comment_delay.min,
                    config.comment_delay.max,
                )
                log.info("Sleeping %.1f seconds before next comment...", delay)
                time.sleep(delay)
            else:
                log.warning("Comment failed on post %s by @%s", post_id, account)

        consecutive_failures = 0  # Reset after successful account processing

    # ------------------------------------------------------------------
    # 5. Run summary (FR-6)
    # ------------------------------------------------------------------
    log.info(
        "=== Bot run complete | %d account(s) checked | %d new post(s) found | %d comment(s) posted ===",
        total_checked,
        total_new,
        total_commented,
    )


if __name__ == "__main__":
    main()
