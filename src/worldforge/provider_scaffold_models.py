"""Validated input models for provider scaffold generation."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from pathlib import Path

CAPABILITIES = ("predict", "embed", "score", "policy")
DEFAULT_TAXONOMY = "unclassified provider scaffold"
IMPLEMENTATION_STATUSES = ("scaffold",)


@dataclass(frozen=True, slots=True)
class ProviderNames:
    raw: str
    display: str
    slug: str
    snake: str
    class_name: str


@dataclass(frozen=True, slots=True)
class ScaffoldOptions:
    root: Path
    names: ProviderNames
    taxonomy: str
    planned_capabilities: tuple[str, ...]
    implementation_status: str
    is_local: bool
    env_var: str | None
    force: bool


def split_provider_name_words(name: str) -> list[str]:
    expanded = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name.strip())
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", expanded)
    return re.findall(r"[A-Za-z][A-Za-z0-9]*|[0-9]+", expanded)


def normalize_provider_name(raw_name: str) -> ProviderNames:
    words = split_provider_name_words(raw_name)
    if not words:
        raise ValueError("provider name must contain at least one alphanumeric word")
    if not words[0][0].isalpha():
        raise ValueError("provider name must start with a letter")

    slug = "-".join(word.lower() for word in words)
    snake = "_".join(word.lower() for word in words)
    if keyword.iskeyword(snake):
        raise ValueError(f"provider module name '{snake}' is a Python keyword")

    class_name = "".join(word[:1].upper() + word[1:] for word in words) + "Provider"
    display = " ".join(word[:1].upper() + word[1:] for word in words)
    return ProviderNames(
        raw=raw_name,
        display=display,
        slug=slug,
        snake=snake,
        class_name=class_name,
    )


def dedupe_capabilities(capabilities: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for capability in capabilities:
        if capability not in seen:
            seen.add(capability)
            deduped.append(capability)
    return tuple(deduped)
