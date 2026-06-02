"""Supabase CRUD operations for seen_posts and target_accounts tables."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from supabase import Client, create_client

from bot.logger import log

# ---------------------------------------------------------------------------
# Supabase client initialisation
# ---------------------------------------------------------------------------

_SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")

_client: Client | None = None


def _get_client() -> Client:
    """Lazily initialise and return the Supabase client."""
    global _client
    if _client is None:
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_KEY must be set as environment variables"
            )
        _client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_seen(post_id: str) -> bool:
    """Check whether a post has already been commented on.

    Returns True if the post_id exists in the seen_posts table.
    """
    try:
        result = (
            _get_client()
            .table("seen_posts")
            .select("post_id")
            .eq("post_id", post_id)
            .execute()
        )
        return len(result.data) > 0
    except Exception as exc:
        log.error("Supabase error checking seen status for %s: %s", post_id, exc)
        # On DB error, assume NOT seen so we don't silently skip posts forever.
        # The duplicate-insert will fail harmlessly if it turns out we already commented.
        return False


def mark_seen(post_id: str, account: str) -> None:
    """Record that we have commented on a post.

    Inserts a row into seen_posts. If the row already exists (race condition
    or retry), the insert is silently ignored via upsert.
    """
    try:
        _get_client().table("seen_posts").upsert(
            {"post_id": post_id, "account": account},
            on_conflict="post_id",
        ).execute()
        log.debug("Marked post %s as seen", post_id)
    except Exception as exc:
        log.error("Supabase error marking post %s as seen: %s", post_id, exc)


def cleanup_old_records(retention_days: int) -> int:
    """Delete seen_posts rows older than *retention_days* days.

    Returns the number of rows deleted, or 0 on error.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_iso = cutoff.isoformat()

    try:
        result = (
            _get_client()
            .table("seen_posts")
            .delete()
            .lt("commented_at", cutoff_iso)
            .execute()
        )
        count = len(result.data) if result.data else 0
        if count:
            log.info("Cleaned up %d stale seen_posts records (older than %d days)", count, retention_days)
        return count
    except Exception as exc:
        log.error("Supabase error during cleanup: %s", exc)
        return 0


def get_target_accounts() -> list[dict]:
    """Fetch active target accounts from the Supabase target_accounts table.

    Returns a list of dicts, each with 'username' (str) and 'comments' (list[str]).
    Returns an empty list on error.
    """
    try:
        result = (
            _get_client()
            .table("target_accounts")
            .select("username, comments")
            .eq("is_active", True)
            .execute()
        )
        accounts = result.data if result.data else []
        log.info("Loaded %d active target account(s) from Supabase", len(accounts))
        return accounts
    except Exception as exc:
        log.error("Failed to load target accounts from Supabase: %s", exc)
        return []
