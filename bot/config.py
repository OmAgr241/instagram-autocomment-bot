"""Configuration loader for the Instagram Auto-Comment Bot.

Loads bot behavior settings from config.yaml.
Target accounts are managed in Supabase (not in this file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bot.logger import log


@dataclass
class CommentDelay:
    """Min/max bounds for the random delay between comments (seconds)."""

    min: int = 30
    max: int = 90


@dataclass
class Config:
    """Typed representation of config.yaml (bot behavior settings only).

    Target accounts are loaded from Supabase at runtime — see database.py.
    """

    posts_to_check: int = 5
    max_comments_per_account_per_run: int = 2
    comment_delay: CommentDelay = field(default_factory=CommentDelay)
    max_post_age_hours: int = 24
    seen_posts_retention_days: int = 30
    dry_run: bool = False


def load_config(config_path: str | None = None) -> Config:
    """Load and validate config.yaml, returning a typed Config object.

    Args:
        config_path: Optional override for the config file location.
                     Defaults to config.yaml in the project root.

    Raises:
        FileNotFoundError: If config.yaml does not exist.
        ValueError: If required fields are missing or invalid.
    """
    if config_path is None:
        # Resolve relative to project root (two levels up from bot/)
        config_path = str(Path(__file__).resolve().parent.parent / "config.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError("config.yaml is empty")

    # --- Parse comment_delay ---
    raw_delay = raw.get("comment_delay", {})
    delay = CommentDelay(
        min=raw_delay.get("min", 30),
        max=raw_delay.get("max", 90),
    )
    if delay.min < 0 or delay.max < delay.min:
        raise ValueError(
            f"comment_delay must satisfy 0 <= min <= max, got min={delay.min}, max={delay.max}"
        )

    # --- Parse scalar fields ---
    max_comments = raw.get("max_comments_per_account_per_run", 2)
    if max_comments < 1:
        raise ValueError("max_comments_per_account_per_run must be >= 1")

    config = Config(
        posts_to_check=raw.get("posts_to_check", 5),
        max_comments_per_account_per_run=max_comments,
        comment_delay=delay,
        max_post_age_hours=raw.get("max_post_age_hours", 24),
        seen_posts_retention_days=raw.get("seen_posts_retention_days", 30),
        dry_run=raw.get("dry_run", False),
    )

    log.info("Config loaded: dry_run=%s", config.dry_run)
    return config
