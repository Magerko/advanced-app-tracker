"""Guess a category (study, code, ...) from a page's address and title."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Words searched inside the site name (moodle.university.kz -> "moodle").
STUDY_DOMAIN_WORDS = ["moodle", "univer", "canvas"]

# Sites compared as a whole (subdomains match too).
STUDY_DOMAINS = ["classroom.google.com", "docs.google.com"]
CODE_DOMAINS = [
    "github.com", "gitlab.com", "stackoverflow.com",
    "developer.mozilla.org", "docs.python.org",
]
SOCIAL_DOMAINS = [
    "vk.com", "instagram.com", "tiktok.com",
    "x.com", "twitter.com", "facebook.com",
]
ENTERTAINMENT_DOMAINS = ["youtube.com", "netflix.com", "twitch.tv"]

# Words searched in the page path and in the tab title.
# A word is matched as a whole word (plural "s" allowed), so "exam" does not
# match "Example". A word ending in "*" is a stem: "лекци*" matches "лекции".
STUDY_PATH_WORDS = ["lecture", "course", "assignment", "homework", "exam"]
STUDY_TITLE_WORDS = [
    "лекци*", "lecture", "курс*", "course",
    "tutorial", "учеб*", "экзамен*", "exam",
]

CATEGORY_STUDY = "Учёба"
CATEGORY_CODE = "Код / Разработка"
CATEGORY_SOCIAL = "Соцсети"
CATEGORY_ENTERTAINMENT = "Развлечения"
CATEGORY_OTHER = "Другое"


def get_domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.lower().removeprefix("www.")


def domain_matches(domain: str, names: list[str]) -> bool:
    return any(domain == n or domain.endswith("." + n) for n in names)


def contains_any(text: str, words: list[str]) -> bool:
    """True if any word appears anywhere inside the text."""
    text = text.lower()
    return any(word in text for word in words)


def has_any(text: str, words: list[str]) -> bool:
    """True if any word is found in the text (see the notes above the lists)."""
    text = text.lower()
    for word in words:
        if word.endswith("*"):
            pattern = r"(?<!\w)" + re.escape(word[:-1])
        else:
            pattern = r"(?<!\w)" + re.escape(word) + r"(?:e?s)?(?!\w)"
        if re.search(pattern, text):
            return True
    return False


def categorize_url(url: str, title: str = "") -> str:
    domain = get_domain(url)
    path = urlsplit(url).path.lower()
    title = title or ""

    # Study checks come first, so a lecture on YouTube counts as study.
    if path.endswith(".pdf"):
        return CATEGORY_STUDY
    if contains_any(domain, STUDY_DOMAIN_WORDS) or domain_matches(domain, STUDY_DOMAINS):
        return CATEGORY_STUDY
    if has_any(path, STUDY_PATH_WORDS):
        return CATEGORY_STUDY
    if has_any(title, STUDY_TITLE_WORDS):
        return CATEGORY_STUDY

    if domain_matches(domain, CODE_DOMAINS):
        return CATEGORY_CODE
    if domain_matches(domain, SOCIAL_DOMAINS):
        return CATEGORY_SOCIAL
    if domain_matches(domain, ENTERTAINMENT_DOMAINS):
        return CATEGORY_ENTERTAINMENT

    return CATEGORY_OTHER
