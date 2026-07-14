# -*- coding: utf-8 -*-
"""Unified tagging primitives shared by remote and local taggers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union


class TaggingError(RuntimeError):
    """A user-facing tagging failure."""


@dataclass
class TagContext:
    """Information available to a tagger for one downloaded image."""

    image_path: str
    source_id: str = ""
    post_id: str = ""
    artist: str = ""
    source_url: str = ""
    native_tags: Union[str, Sequence[str]] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class TagResult:
    """Normalized tagger output before final formatting."""

    tags: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    raw: Any = None
    model: str = ""

    def caption(self, tag_format: str = "comma") -> str:
        return format_tags(self.tags, tag_format)


class Tagger:
    """Small interface implemented by every tagging backend."""

    id = ""
    label = ""
    needs_model = False
    needs_network = False

    def normalize_cfg(self, body: Mapping[str, Any]) -> Union[Dict[str, Any], str]:
        return dict(body or {})

    def test(self, cfg: Mapping[str, Any]):
        """Return ``(ok, message)`` without raising expected user errors."""
        return True, "可用"

    def tag(self, context: TagContext, cfg: Mapping[str, Any]) -> TagResult:
        raise NotImplementedError


class NoneTagger(Tagger):
    id = "none"
    label = "不额外打标"

    def normalize_cfg(self, body: Mapping[str, Any]) -> Dict[str, Any]:
        # Do not retain unrelated task fields or credentials for the no-op mode.
        return {}

    def tag(self, context: TagContext, cfg: Mapping[str, Any]) -> TagResult:
        return TagResult(tags=[], model=self.id)


def split_tags(value: Union[None, str, Iterable[Any]]) -> List[str]:
    """Convert common caption/tag representations into a tag list.

    Comma/newline separated captions are preferred. A plain whitespace string
    is treated as Danbooru-style tags, where spaces separate tokens.
    """
    if value is None:
        return []
    if not isinstance(value, str):
        out = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out

    text = value.strip()
    if not text:
        return []
    if "," in text or "\n" in text or "\r" in text:
        return [part.strip() for part in re.split(r"[,\r\n]+", text) if part.strip()]
    return [part for part in text.split() if part]


def _display_tag(tag: str) -> str:
    tag = re.sub(r"\s+", " ", str(tag).strip())
    return tag


def _dedupe_key(tag: str) -> str:
    tag = tag.replace("\\(", "(").replace("\\)", ")")
    tag = tag.replace("_", " ")
    return re.sub(r"\s+", " ", tag).strip().casefold()


def dedupe_tags(*groups: Union[None, str, Iterable[Any]]) -> List[str]:
    """Stable, case-insensitive deduplication across native/generated tags.

    Spaces and underscores are considered equivalent, so ``blue_eyes`` and
    ``blue eyes`` do not both appear in the final caption.
    """
    seen = set()
    out = []
    for group in groups:
        for raw_tag in split_tags(group):
            tag = _display_tag(raw_tag)
            key = _dedupe_key(tag)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(tag)
    return out


def format_tags(tags: Union[None, str, Iterable[Any]], tag_format: str = "comma") -> str:
    """Format tags like the existing downloader captions.

    ``comma`` produces training captions (spaces, escaped parentheses), while
    ``space`` produces Danbooru-style underscore tokens.
    """
    unique = dedupe_tags(tags)
    if tag_format == "space":
        return " ".join(re.sub(r"\s+", "_", tag.strip()) for tag in unique)
    if tag_format != "comma":
        raise ValueError("tag_format must be 'comma' or 'space'")
    pretty = []
    for tag in unique:
        value = tag.replace("_", " ")
        value = value.replace("\\(", "(").replace("\\)", ")")
        value = value.replace("(", "\\(").replace(")", "\\)")
        pretty.append(value)
    return ", ".join(pretty)


def merge_captions(native_tags: Union[None, str, Iterable[Any]],
                   generated_tags: Union[None, str, Iterable[Any]],
                   tag_format: str = "comma") -> str:
    """Merge native tags first, generated tags second, then format once."""
    return format_tags(dedupe_tags(native_tags, generated_tags), tag_format)
