"""Instagram API interactions via instagrapi.

Handles login with session reuse, fetching recent posts, and commenting.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    LoginRequired,
    MediaNotFound,
)
from instagrapi.types import Media

from bot.logger import log
from bot.session_manager import load_session, save_session


# ---------------------------------------------------------------------------
# Custom exception for challenge events (surfaced to main.py)
# ---------------------------------------------------------------------------


class ChallengeError(Exception):
    """Raised when Instagram requires a manual challenge (2FA / captcha)."""

    def __init__(self, message: str, challenge_url: str | None = None):
        super().__init__(message)
        self.challenge_url = challenge_url


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def login(username: str, password: str) -> Client:
    """Create an instagrapi Client, reusing a Supabase-persisted session.

    Flow:
    1. Try to load an existing session from Supabase and inject it.
    2. If the session is missing or expired, perform a fresh login.
    3. After a successful login, save the session back to Supabase.

    Raises:
        ChallengeError: If Instagram demands a challenge.
        LoginRequired: If login fails after retry.
    """
    cl = Client()

    # Attempt session reuse
    session_data = load_session()
    if session_data:
        try:
            cl.set_settings(session_data)
            cl.login(username, password)
            log.info("Logged in using saved session for @%s", username)
            # Persist potentially refreshed session
            save_session(cl.get_settings())
            return cl
        except ChallengeRequired as exc:
            challenge_url = getattr(exc, "challenge_url", None) or str(exc)
            raise ChallengeError(
                f"Challenge required during session reuse: {challenge_url}",
                challenge_url=challenge_url,
            )
        except (LoginRequired, ClientError) as exc:
            log.warning("Saved session expired or invalid (%s) — doing fresh login", exc)

    # Fresh login
    try:
        cl = Client()
        cl.login(username, password)
        log.info("Fresh login successful for @%s", username)
        save_session(cl.get_settings())
        return cl
    except ChallengeRequired as exc:
        challenge_url = getattr(exc, "challenge_url", None) or str(exc)
        raise ChallengeError(
            f"Challenge required during fresh login: {challenge_url}",
            challenge_url=challenge_url,
        )
    except LoginRequired:
        raise
    except Exception as exc:
        log.error("Unexpected login error: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Fetch recent posts
# ---------------------------------------------------------------------------


def get_new_posts(
    client: Client,
    username: str,
    count: int,
    max_age_hours: int,
) -> List[Media]:
    """Fetch recent posts/reels for *username* that are within the age window.

    Args:
        client: An authenticated instagrapi Client.
        username: The target Instagram username.
        count: Number of recent posts to fetch.
        max_age_hours: Ignore posts older than this.

    Returns:
        A list of Media objects newer than the cutoff.
    """
    try:
        user_id = client.user_id_from_username(username)
    except Exception as exc:
        log.error("Failed to resolve user ID for @%s: %s", username, exc)
        return []

    try:
        medias = client.user_medias(user_id, amount=count)
    except MediaNotFound:
        log.warning("No media found for @%s", username)
        return []
    except Exception as exc:
        log.error("Failed to fetch posts for @%s: %s", username, exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    recent: list[Media] = []
    for media in medias:
        # media.taken_at is a datetime; ensure it's timezone-aware
        taken = media.taken_at
        if taken.tzinfo is None:
            taken = taken.replace(tzinfo=timezone.utc)
        if taken >= cutoff:
            recent.append(media)
        else:
            log.debug(
                "Skipping old post %s from @%s (posted %s)",
                media.pk,
                username,
                taken.isoformat(),
            )

    log.info("Found %d recent post(s) for @%s (checked %d)", len(recent), username, len(medias))
    return recent


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


def post_comment(client: Client, media_id: str, comment_text: str) -> bool:
    """Post a comment on the given media.

    Returns True on success, False on handled failure.

    Raises:
        ClientError: Re-raised on rate-limit errors so main.py can abort the run.
        ChallengeError: Re-raised if a challenge is triggered mid-run.
    """
    try:
        client.media_comment(media_id, comment_text)
        return True
    except ChallengeRequired as exc:
        challenge_url = getattr(exc, "challenge_url", None) or str(exc)
        raise ChallengeError(
            f"Challenge required while commenting: {challenge_url}",
            challenge_url=challenge_url,
        )
    except MediaNotFound:
        log.warning("Media %s not found — skipping", media_id)
        return False
    except ClientError as exc:
        # Check if it looks like a rate-limit (e.g. HTTP 429 or "Please wait")
        exc_str = str(exc).lower()
        if "429" in exc_str or "please wait" in exc_str or "rate" in exc_str:
            log.warning("Rate limit hit while commenting on %s: %s", media_id, exc)
            raise  # Let main.py handle abort
        log.error("Client error commenting on %s: %s", media_id, exc)
        return False
    except Exception as exc:
        log.error("Unexpected error commenting on %s: %s", media_id, exc)
        return False
