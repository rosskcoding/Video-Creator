"""
Shared validation helpers for API routes.
"""

from __future__ import annotations

import os
import re
from typing import AbstractSet

from fastapi import HTTPException

from app.db.models import Project

# Allowed languages whitelist (security layer)
SUPPORTED_LANGUAGES: AbstractSet[str] = frozenset(
    [
        "en",
        "ru",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "nl",
        "pl",
        "uk",
        "zh",
        "ja",
        "ko",
        "ar",
        "hi",
        "tr",
        "vi",
        "th",
        "id",
        "ms",
        "cs",
        "sv",
        "da",
        "fi",
        "no",
        "el",
        "he",
        "hu",
        "ro",
        "sk",
    ]
)

# Pattern to validate language codes (2-3 lowercase letters)
LANG_PATTERN = re.compile(r"^[a-z]{2,3}$")

# Filename pattern: allow dots in basename, enforce extension, forbid path separators.
FILENAME_PATTERN = re.compile(r"^[\w.\-]+\.[a-z0-9]+$", re.IGNORECASE)


def normalize_lang(lang: str) -> str:
    return (lang or "").lower().strip()


def validate_lang_code(lang: str) -> str:
    """
    Validate language code against:
    - format guard (regex)
    - global supported whitelist (security layer)
    """
    lang = normalize_lang(lang)
    if not LANG_PATTERN.match(lang):
        raise HTTPException(status_code=400, detail=f"Invalid language format: {lang}")
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")
    return lang


def project_allowed_languages(project: Project) -> set[str]:
    """
    Effective per-project allowlist.
    Always includes base_language, even if DB field is missing/empty.
    """
    allowed: set[str] = set(project.allowed_languages or [])
    if project.base_language:
        allowed.add(project.base_language)
    return allowed


def validate_lang_for_project(lang: str, project: Project) -> str:
    """
    Validate language code + ensure it's allowed for the given project.
    """
    lang = validate_lang_code(lang)
    if lang not in project_allowed_languages(project):
        raise HTTPException(status_code=400, detail=f"Language not enabled for this project: {lang}")
    return lang


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal.

    Allows dots in the basename to support versioning like:
    - deck.en.mp4
    - deck_en.v2.mp4
    """
    raw = (filename or "").strip()

    # Get only the basename, removing any directory components
    basename = os.path.basename(raw)

    # Reject any path separators / directory components
    if not raw or basename != raw or "/" in raw or "\\" in raw:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Reject hidden files and suspicious patterns
    if basename.startswith(".") or ".." in basename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Allow alphanumeric, underscore, hyphen, dot, plus extension
    if not FILENAME_PATTERN.match(basename):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    return basename


