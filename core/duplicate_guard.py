"""Duplicate News Guard domain logic.

This module is intentionally independent from publication delivery.

Responsibilities:
- normalize publishable news text
- detect exact duplicates
- detect near-duplicates
- return a decision only

It must NOT:
- publish or block a message
- access Telegram/Bale directly
- depend on a specific workspace
- modify publication state
- raise an error into the publication path

Persistence and user interaction are connected in later stages.
"""

from __future__ import annotations

import hashlib
import re

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Optional


DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.88
MIN_COMPARABLE_LENGTH = 40


@dataclass(frozen=True)
class DuplicateCandidate:
    """Previously published logical news item."""

    publication_id: str
    media_identity_id: int
    text: str
    actor_user_id: Optional[int] = None
    published_at: Optional[str] = None


@dataclass(frozen=True)
class DuplicateMatch:
    """One duplicate match returned by the guard."""

    publication_id: str
    media_identity_id: int
    match_type: str
    similarity: float
    actor_user_id: Optional[int] = None
    published_at: Optional[str] = None


@dataclass(frozen=True)
class DuplicateDecision:
    """Result of checking one incoming news item."""

    duplicate: bool
    match_type: Optional[str] = None
    similarity: float = 0.0
    match: Optional[DuplicateMatch] = None


def normalize_duplicate_text(text: str) -> str:
    """
    Normalize news text for duplicate comparison.

    The normalization intentionally ignores superficial differences such as:
    - repeated whitespace
    - zero-width characters
    - Arabic/Persian forms of ی and ک
    - simple punctuation differences

    It does not rewrite the actual publication text.
    """
    value = str(text or "")

    value = (
        value.replace("\u200c", " ")
        .replace("\u200f", " ")
        .replace("\u200e", " ")
        .replace("\ufeff", " ")
        .replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
    )

    value = value.casefold()

    value = re.sub(
        r"[^\w\s]",
        " ",
        value,
        flags=re.UNICODE,
    )

    value = value.replace("_", " ")

    value = re.sub(r"\s+", " ", value).strip()

    return value


def duplicate_fingerprint(text: str) -> str:
    """Return a stable fingerprint for exact duplicate comparison."""
    normalized = normalize_duplicate_text(text)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _token_set(text: str) -> set[str]:
    return {
        token
        for token in normalize_duplicate_text(text).split()
        if token
    }


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)

    if not union:
        return 0.0

    return intersection / union


def duplicate_similarity(left: str, right: str) -> float:
    """
    Calculate near-duplicate similarity.

    We combine:
    - sequence similarity
    - token overlap

    The stronger signal wins so reordered but substantially identical
    news can still be detected.
    """
    normalized_left = normalize_duplicate_text(left)
    normalized_right = normalize_duplicate_text(right)

    if not normalized_left or not normalized_right:
        return 0.0

    if normalized_left == normalized_right:
        return 1.0

    sequence_score = SequenceMatcher(
        None,
        normalized_left,
        normalized_right,
        autojunk=False,
    ).ratio()

    token_score = _token_similarity(
        normalized_left,
        normalized_right,
    )

    return max(sequence_score, token_score)


def _eligible_for_near_duplicate(
    incoming_text: str,
    candidate_text: str,
) -> bool:
    incoming = normalize_duplicate_text(incoming_text)
    candidate = normalize_duplicate_text(candidate_text)

    return (
        len(incoming) >= MIN_COMPARABLE_LENGTH
        and len(candidate) >= MIN_COMPARABLE_LENGTH
    )


def check_duplicate(
    *,
    media_identity_id: int,
    text: str,
    candidates: Iterable[DuplicateCandidate],
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> DuplicateDecision:
    """
    Check one incoming publication against previous publications
    belonging to the SAME Media Identity.

    Exact match has priority over near-duplicate match.

    This function never blocks publication. It only returns a decision.
    """
    incoming = normalize_duplicate_text(text)

    if not incoming:
        return DuplicateDecision(duplicate=False)

    incoming_fingerprint = duplicate_fingerprint(incoming)

    best_match: Optional[DuplicateMatch] = None

    for candidate in candidates:
        if int(candidate.media_identity_id) != int(media_identity_id):
            continue

        candidate_text = normalize_duplicate_text(candidate.text)

        if not candidate_text:
            continue

        if duplicate_fingerprint(candidate_text) == incoming_fingerprint:
            match = DuplicateMatch(
                publication_id=str(candidate.publication_id),
                media_identity_id=int(candidate.media_identity_id),
                match_type="exact",
                similarity=1.0,
                actor_user_id=candidate.actor_user_id,
                published_at=candidate.published_at,
            )

            return DuplicateDecision(
                duplicate=True,
                match_type="exact",
                similarity=1.0,
                match=match,
            )

        if not _eligible_for_near_duplicate(
            incoming,
            candidate_text,
        ):
            continue

        similarity = duplicate_similarity(
            incoming,
            candidate_text,
        )

        if similarity < near_duplicate_threshold:
            continue

        match = DuplicateMatch(
            publication_id=str(candidate.publication_id),
            media_identity_id=int(candidate.media_identity_id),
            match_type="near",
            similarity=similarity,
            actor_user_id=candidate.actor_user_id,
            published_at=candidate.published_at,
        )

        if (
            best_match is None
            or match.similarity > best_match.similarity
        ):
            best_match = match

    if best_match is None:
        return DuplicateDecision(
            duplicate=False,
        )

    return DuplicateDecision(
        duplicate=True,
        match_type=best_match.match_type,
        similarity=best_match.similarity,
        match=best_match,
    )


def safe_check_duplicate(
    *,
    media_identity_id: int,
    text: str,
    candidates: Iterable[DuplicateCandidate],
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> DuplicateDecision:
    """
    Fail-open wrapper.

    Duplicate Guard must never stop normal publication because of
    an internal detector failure.
    """
    try:
        return check_duplicate(
            media_identity_id=media_identity_id,
            text=text,
            candidates=candidates,
            near_duplicate_threshold=near_duplicate_threshold,
        )
    except Exception:
        return DuplicateDecision(
            duplicate=False,
        )
