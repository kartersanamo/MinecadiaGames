"""Fetch quotes from API Ninjas and build fill-in-the-blank puzzles."""
from __future__ import annotations

import os
import random
import re
from typing import Any, Optional

import aiohttp

from core.config.manager import ConfigManager
from core.logging.setup import get_logger

logger = get_logger("ChatGames")

_WORD_RE = re.compile(r"\b[\w']+\b")

_DEFAULT_STOPWORDS = {
    "a", "an", "the", "or", "and", "to", "of", "in", "is", "it", "be", "as", "at",
    "by", "for", "on", "with", "that", "this", "you", "your", "we", "our", "are",
    "was", "were", "been", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "can", "not", "no", "nor",
    "but", "if", "so", "than", "then", "them", "they", "their", "there", "these",
    "those", "what", "when", "where", "who", "whom", "which", "while", "how", "why",
    "all", "each", "every", "both", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "too", "very", "just", "also", "into", "over", "after",
    "before", "between", "through", "during", "from", "up", "down", "out", "off",
    "about", "again", "once", "here", "he", "she", "his", "her", "its", "my", "me",
    "us", "him", "i",
}


def _load_config() -> dict[str, Any]:
    config = ConfigManager.get_instance().get("fill_in_the_blank") or {}
    if not isinstance(config, dict):
        return {}
    return config


def _normalize_word(word: str) -> str:
    return word.strip("'\"").lower()


def _eligible_words(quote: str, stopwords: set[str], min_length: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for match in _WORD_RE.finditer(quote):
        word = match.group()
        clean = _normalize_word(word)
        if clean in stopwords or len(clean) < min_length:
            continue
        candidates.append(
            {
                "word": word,
                "clean": clean,
                "start": match.start(),
                "end": match.end(),
            }
        )
    return candidates


def _pick_correct(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("No eligible words in quote")
    ranked = sorted(candidates, key=lambda c: len(c["clean"]), reverse=True)
    top = ranked[: max(1, len(ranked) // 2 + 1)]
    return random.choice(top)


def _collect_distractors(
    correct: dict[str, Any],
    same_quote: list[dict[str, Any]],
    extra_words: list[str],
    fallback_words: list[str],
) -> list[str]:
    distractors: list[str] = []
    seen = {correct["clean"]}

    for candidate in same_quote:
        if candidate["clean"] in seen:
            continue
        distractors.append(candidate["word"])
        seen.add(candidate["clean"])
        if len(distractors) >= 3:
            return distractors

    pool = list(extra_words) + list(fallback_words)
    random.shuffle(pool)
    for word in pool:
        clean = _normalize_word(word)
        if clean in seen or len(clean) < 3:
            continue
        distractors.append(word)
        seen.add(clean)
        if len(distractors) >= 3:
            break

    if len(distractors) < 3:
        raise ValueError("Not enough distractor words")

    return distractors[:3]


def _build_puzzle_from_quote(
    quote: str,
    author: str,
    work: str,
    *,
    stopwords: set[str],
    min_length: int,
    extra_words: list[str],
    fallback_words: list[str],
) -> dict[str, Any]:
    candidates = _eligible_words(quote, stopwords, min_length)
    correct = _pick_correct(candidates)
    distractors = _collect_distractors(
        correct,
        [c for c in candidates if c["clean"] != correct["clean"]],
        extra_words,
        fallback_words,
    )
    quote_display = quote[: correct["start"]] + "______" + quote[correct["end"] :]
    answers = [correct["word"], *distractors]
    random.shuffle(answers)

    return {
        "quote_display": quote_display,
        "quote_original": quote,
        "correct_answer": correct["word"],
        "answers": answers,
        "author": author,
        "work": work or "",
    }


async def _fetch_quotes(session: aiohttp.ClientSession, api_url: str, api_key: str) -> list[dict[str, Any]]:
    headers = {"X-Api-Key": api_key}
    async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"API Ninjas returned {resp.status}: {body[:200]}")
        data = await resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected API response type: {type(data).__name__}")
    return [item for item in data if isinstance(item, dict) and item.get("quote")]


async def fetch_quote_puzzle() -> Optional[dict[str, Any]]:
    """Return a puzzle dict or None if the API/key/config cannot produce one."""
    cfg = _load_config()
    api_cfg = cfg.get("api", {})
    api_url = api_cfg.get(
        "url",
        "https://api.api-ninjas.com/v2/randomquotes",
    )
    categories = api_cfg.get("categories", "success,wisdom")
    if "?" in api_url:
        full_url = f"{api_url}&categories={categories}"
    else:
        full_url = f"{api_url}?categories={categories}"

    api_key = os.getenv("API_NINJAS_KEY", "").strip()
    if not api_key:
        logger.error("API_NINJAS_KEY is not set — cannot run Fill in the Blank")
        return None

    stopwords = set(cfg.get("stopwords") or _DEFAULT_STOPWORDS)
    min_length = int(cfg.get("min_word_length", 4))
    fallback_words = list(cfg.get("fallback_words") or [])

    max_attempts = 3
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_attempts):
            try:
                quotes = await _fetch_quotes(session, full_url, api_key)
            except Exception as exc:
                logger.error("Fill in the Blank API fetch failed (attempt %s): %s", attempt + 1, exc)
                continue

            if not quotes:
                continue

            random.shuffle(quotes)
            extra_words: list[str] = []
            for item in quotes:
                for candidate in _eligible_words(item["quote"], stopwords, min_length):
                    extra_words.append(candidate["word"])

            for item in quotes:
                try:
                    return _build_puzzle_from_quote(
                        item["quote"],
                        item.get("author", "Unknown"),
                        item.get("work", ""),
                        stopwords=stopwords,
                        min_length=min_length,
                        extra_words=extra_words,
                        fallback_words=fallback_words,
                    )
                except ValueError:
                    continue

    logger.error("Fill in the Blank: could not build puzzle after %s attempts", max_attempts)
    return None
