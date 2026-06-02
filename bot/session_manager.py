"""Session persistence via Supabase for ephemeral GitHub Actions runners.

Instead of saving session.json to disk (which is lost after every Actions run),
we store the instagrapi session JSON in the bot_sessions Supabase table.
"""

from __future__ import annotations

import json
import os
from typing import Any

from supabase import Client, create_client

from bot.logger import log

# ---------------------------------------------------------------------------
# Supabase client (shared constants — same creds as database.py)
# ---------------------------------------------------------------------------

_SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")

_client: Client | None = None

# The fixed row ID used for the single-bot session.
_SESSION_ROW_ID = "default"


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


def load_session() -> dict[str, Any] | None:
    """Fetch the stored instagrapi session from Supabase.

    Returns the session dict if one exists, or None on first run / error.
    """
    try:
        result = (
            _get_client()
            .table("bot_sessions")
            .select("session_data")
            .eq("id", _SESSION_ROW_ID)
            .execute()
        )
        if result.data:
            session_data = result.data[0]["session_data"]
            # session_data may already be a dict (JSONB) or a JSON string
            if isinstance(session_data, str):
                session_data = json.loads(session_data)
            log.info("Loaded existing session from Supabase")
            return session_data
        log.info("No existing session found in Supabase (first run?)")
        return None
    except Exception as exc:
        log.warning("Failed to load session from Supabase: %s", exc)
        return None


def save_session(session_data: dict[str, Any]) -> None:
    """Upsert the instagrapi session into Supabase.

    The Postgres trigger on bot_sessions automatically updates the
    updated_at timestamp on every upsert.
    """
    try:
        _get_client().table("bot_sessions").upsert(
            {
                "id": _SESSION_ROW_ID,
                "session_data": session_data,
            },
            on_conflict="id",
        ).execute()
        log.info("Session saved to Supabase")
    except Exception as exc:
        log.error("Failed to save session to Supabase: %s", exc)
