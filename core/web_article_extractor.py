"""Professional web-article extraction for external content ingestion."""

from __future__ import annotations

import json
import re

from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlsplit

from trafilatura import bare_extraction

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_fetcher import (
    SafeExternalFetcher,
    canonicalize_external_url,
)


ARTICLE_JSONLD_TYPES = frozenset(
    {
        "article",
        "newsarticle",
        "reportagenewsarticle",
        "analysisnewsarticle",
        "blogposting",
        "liveblogposting",
        "opinionnewsarticle",
        "reviewnewsarticle",
    }
)

_PAYWALL_MARKERS = (
    "paywall",
    "subscribe to continue",
    "subscription required",
    "premium content",
    "members only",
    "برای ادامه اشتراک",
    "اشتراک ویژه",
    "ویژه مشترکان",
)

_LOW_VALUE_IMAGE_MARKERS = (
    "logo",
    "avatar",
    "icon",
    "sprite",
    "banner",
    "advert",
    "ads/",
    "/ad/",
    "tracking",
    "pixel",
    "favicon",
    "sponsor",
    "promoted",
    "recommendation",
    "recommended",
    "related-post",
)

_MAX_ARTICLE_MEDIA = 10

_SPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n+")


class WebArticleExtractionError(RuntimeError):
    """Raised when a web page cannot produce a useful article candidate."""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    lines = []

    for line in text.splitlines():
        normalized = _SPACE_RE.sub(
            " ",
            line,
        ).strip()

        if normalized:
            lines.append(
                normalized
            )
        elif lines and lines[-1] != "":
            lines.append("")

    result = "\n".join(
        lines
    ).strip()

    return _BLANK_LINE_RE.sub(
        "\n\n",
        result,
    )


def _first_nonempty(
    *values: Any,
) -> str:
    for value in values:
        cleaned = _clean_text(
            value
        )

        if cleaned:
            return cleaned

    return ""


def _normalize_language(
    value: Any,
) -> str:
    language = _clean_text(
        value
    ).lower()

    if not language:
        return ""

    language = language.replace(
        "_",
        "-",
    )

    return language.split(
        "-",
        1,
    )[0]


def _absolute_public_url(
    value: Any,
    base_url: str,
) -> str:
    raw = _clean_text(
        value
    )

    if not raw:
        return ""

    try:
        joined = urljoin(
            base_url,
            raw,
        )

        return canonicalize_external_url(
            joined
        )
    except Exception:
        return ""


def _parse_int(
    value: Any,
) -> Optional[int]:
    try:
        parsed = int(
            str(value).strip()
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if parsed <= 0:
        return None

    return parsed


def _best_srcset_url(
    srcset: str,
) -> str:
    candidates = []

    for item in str(
        srcset or ""
    ).split(","):
        item = item.strip()

        if not item:
            continue

        parts = item.split()

        url = parts[0].strip()

        score = 0

        if len(parts) > 1:
            descriptor = (
                parts[-1]
                .strip()
                .lower()
            )

            try:
                if descriptor.endswith(
                    "w"
                ):
                    score = int(
                        descriptor[:-1]
                    )
                elif descriptor.endswith(
                    "x"
                ):
                    score = int(
                        float(
                            descriptor[:-1]
                        )
                        * 1000
                    )
            except ValueError:
                score = 0

        candidates.append(
            (
                score,
                url,
            )
        )

    if not candidates:
        return ""

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


class _ArticleHTMLFacts(HTMLParser):
    """
    Lightweight HTML inspection layer.

    Trafilatura remains responsible for main-content extraction.
    This parser gathers metadata and image candidates that complement
    Trafilatura and JSON-LD.
    """

    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.meta: Dict[
            str,
            List[str],
        ] = {}

        self.canonical_href = ""

        self.html_language = ""

        self.images: List[
            Dict[str, Any]
        ] = []

        self.json_ld_raw: List[
            str
        ] = []

        self.h1: List[str] = []
        self.paragraphs: List[str] = []

        self.title_text = ""

        self.script_count = 0

        self._capture_tag: Optional[
            str
        ] = None

        self._capture_buffer: List[
            str
        ] = []

        self._json_ld_active = False
        self._json_ld_buffer: List[
            str
        ] = []

    @staticmethod
    def _attributes(
        attrs: Sequence[
            Tuple[
                str,
                Optional[str],
            ]
        ],
    ) -> Dict[str, str]:
        return {
            str(key).lower(): (
                value
                if value is not None
                else ""
            )
            for key, value in attrs
        }

    def handle_starttag(
        self,
        tag: str,
        attrs,
    ) -> None:
        tag = tag.lower()

        attributes = self._attributes(
            attrs
        )

        if tag == "html":
            self.html_language = (
                attributes.get(
                    "lang",
                    "",
                )
            )

        elif tag == "meta":
            key = _first_nonempty(
                attributes.get(
                    "property"
                ),
                attributes.get(
                    "name"
                ),
                attributes.get(
                    "itemprop"
                ),
                attributes.get(
                    "http-equiv"
                ),
            ).lower()

            content = _clean_text(
                attributes.get(
                    "content"
                )
            )

            if key and content:
                self.meta.setdefault(
                    key,
                    [],
                ).append(
                    content
                )

        elif tag == "link":
            rel = {
                value.strip().lower()
                for value in (
                    attributes.get(
                        "rel",
                        ""
                    )
                ).split()
                if value.strip()
            }

            if (
                "canonical" in rel
                and not self.canonical_href
            ):
                self.canonical_href = (
                    attributes.get(
                        "href",
                        ""
                    )
                )

        elif tag == "img":
            src = _first_nonempty(
                attributes.get(
                    "data-src"
                ),
                attributes.get(
                    "data-original"
                ),
                attributes.get(
                    "data-lazy-src"
                ),
                attributes.get(
                    "src"
                ),
            )

            srcset = _first_nonempty(
                attributes.get(
                    "data-srcset"
                ),
                attributes.get(
                    "srcset"
                ),
            )

            best_srcset = (
                _best_srcset_url(
                    srcset
                )
            )

            self.images.append(
                {
                    "src": (
                        best_srcset
                        or src
                    ),
                    "alt": (
                        attributes.get(
                            "alt",
                            ""
                        )
                    ),
                    "title": (
                        attributes.get(
                            "title",
                            ""
                        )
                    ),
                    "width": (
                        attributes.get(
                            "width"
                        )
                    ),
                    "height": (
                        attributes.get(
                            "height"
                        )
                    ),
                    "class": (
                        attributes.get(
                            "class",
                            ""
                        )
                    ),
                    "id": (
                        attributes.get(
                            "id",
                            ""
                        )
                    ),
                }
            )

        elif tag == "script":
            self.script_count += 1

            script_type = (
                attributes.get(
                    "type",
                    ""
                )
                .split(
                    ";",
                    1,
                )[0]
                .strip()
                .lower()
            )

            if script_type == (
                "application/ld+json"
            ):
                self._json_ld_active = (
                    True
                )

                self._json_ld_buffer = []

        if (
            tag in {
                "title",
                "h1",
                "p",
            }
            and self._capture_tag is None
        ):
            self._capture_tag = tag
            self._capture_buffer = []

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        tag = tag.lower()

        if (
            self._json_ld_active
            and tag == "script"
        ):
            raw = "".join(
                self._json_ld_buffer
            ).strip()

            if raw:
                self.json_ld_raw.append(
                    raw
                )

            self._json_ld_active = False
            self._json_ld_buffer = []

        if (
            self._capture_tag
            and tag == self._capture_tag
        ):
            text = _clean_text(
                "".join(
                    self._capture_buffer
                )
            )

            if text:
                if (
                    self._capture_tag
                    == "title"
                ):
                    if not self.title_text:
                        self.title_text = (
                            text
                        )

                elif (
                    self._capture_tag
                    == "h1"
                ):
                    self.h1.append(
                        text
                    )

                elif (
                    self._capture_tag
                    == "p"
                ):
                    self.paragraphs.append(
                        text
                    )

            self._capture_tag = None
            self._capture_buffer = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._json_ld_active:
            self._json_ld_buffer.append(
                data
            )

        if self._capture_tag:
            self._capture_buffer.append(
                data
            )


def _meta_first(
    facts: _ArticleHTMLFacts,
    *keys: str,
) -> str:
    for key in keys:
        values = facts.meta.get(
            key.lower(),
            [],
        )

        for value in values:
            cleaned = _clean_text(
                value
            )

            if cleaned:
                return cleaned

    return ""


def _iter_jsonld_nodes(
    value: Any,
) -> Iterable[
    Mapping[str, Any]
]:
    if isinstance(
        value,
        Mapping,
    ):
        yield value

        graph = value.get(
            "@graph"
        )

        if graph is not None:
            yield from _iter_jsonld_nodes(
                graph
            )

        for key in (
            "mainEntity",
            "mainEntityOfPage",
            "subjectOf",
        ):
            nested = value.get(
                key
            )

            if isinstance(
                nested,
                (
                    Mapping,
                    list,
                    tuple,
                ),
            ):
                yield from _iter_jsonld_nodes(
                    nested
                )

    elif isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        for item in value:
            yield from _iter_jsonld_nodes(
                item
            )


def _jsonld_types(
    node: Mapping[
        str,
        Any,
    ],
) -> Tuple[str, ...]:
    raw = node.get(
        "@type"
    )

    if isinstance(
        raw,
        str,
    ):
        values = [
            raw,
        ]

    elif isinstance(
        raw,
        (
            list,
            tuple,
        ),
    ):
        values = [
            str(item)
            for item in raw
        ]

    else:
        values = []

    return tuple(
        value.strip().lower()
        for value in values
        if value
        and value.strip()
    )


def _parse_json_ld(
    facts: _ArticleHTMLFacts,
) -> List[
    Mapping[str, Any]
]:
    nodes: List[
        Mapping[str, Any]
    ] = []

    for raw in facts.json_ld_raw:
        try:
            parsed = json.loads(
                raw
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            continue

        for node in _iter_jsonld_nodes(
            parsed
        ):
            nodes.append(
                node
            )

    return nodes


def _select_article_jsonld(
    nodes: Iterable[
        Mapping[str, Any]
    ],
) -> Optional[
    Mapping[str, Any]
]:
    best_node = None
    best_score = -1

    for node in nodes:
        types = _jsonld_types(
            node
        )

        score = 0

        if any(
            item
            in ARTICLE_JSONLD_TYPES
            for item in types
        ):
            score += 100

        if _clean_text(
            node.get(
                "headline"
            )
        ):
            score += 20

        if _clean_text(
            node.get(
                "articleBody"
            )
        ):
            score += 30

        if node.get(
            "datePublished"
        ):
            score += 5

        if node.get(
            "image"
        ):
            score += 5

        if score > best_score:
            best_score = score
            best_node = node

    if best_score <= 0:
        return None

    return best_node


def _extract_author(
    value: Any,
) -> str:
    if isinstance(
        value,
        str,
    ):
        return _clean_text(
            value
        )

    if isinstance(
        value,
        Mapping,
    ):
        return _first_nonempty(
            value.get(
                "name"
            ),
            value.get(
                "alternateName"
            ),
        )

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        names = []

        for item in value:
            name = _extract_author(
                item
            )

            if (
                name
                and name not in names
            ):
                names.append(
                    name
                )

        return ", ".join(
            names
        )

    return ""


def _extract_publisher_name(
    value: Any,
) -> str:
    if isinstance(
        value,
        str,
    ):
        return _clean_text(
            value
        )

    if isinstance(
        value,
        Mapping,
    ):
        return _first_nonempty(
            value.get(
                "name"
            ),
            value.get(
                "alternateName"
            ),
        )

    return ""


def _extract_jsonld_url(
    value: Any,
    base_url: str,
) -> str:
    if isinstance(
        value,
        str,
    ):
        return _absolute_public_url(
            value,
            base_url,
        )

    if isinstance(
        value,
        Mapping,
    ):
        return _absolute_public_url(
            _first_nonempty(
                value.get(
                    "@id"
                ),
                value.get(
                    "url"
                ),
            ),
            base_url,
        )

    return ""


def _jsonld_image_values(
    value: Any,
) -> Iterable[
    Tuple[
        str,
        Optional[int],
        Optional[int],
    ]
]:
    if isinstance(
        value,
        str,
    ):
        yield (
            value,
            None,
            None,
        )
        return

    if isinstance(
        value,
        Mapping,
    ):
        raw_url = _first_nonempty(
            value.get(
                "url"
            ),
            value.get(
                "contentUrl"
            ),
            value.get(
                "@id"
            ),
        )

        if raw_url:
            yield (
                raw_url,
                _parse_int(
                    value.get(
                        "width"
                    )
                ),
                _parse_int(
                    value.get(
                        "height"
                    )
                ),
            )

        return

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        for item in value:
            yield from _jsonld_image_values(
                item
            )


def _image_score(
    *,
    url: str,
    width: Optional[int],
    height: Optional[int],
    alt_text: str,
    title: str,
    source_kind: str,
    article_title: str,
) -> int:
    score = 0

    if source_kind == "og":
        score += 120

    elif source_kind == "json_ld":
        score += 110

    elif source_kind == "twitter":
        score += 95

    else:
        score += 20

    if (
        width is not None
        and height is not None
    ):
        pixels = (
            width
            * height
        )

        if pixels >= 1_000_000:
            score += 30

        elif pixels >= 400_000:
            score += 20

        elif pixels >= 100_000:
            score += 10

        if (
            width < 200
            or height < 120
        ):
            score -= 100

    combined = (
        f"{url} {alt_text} {title}"
        .lower()
    )

    if any(
        marker in combined
        for marker
        in _LOW_VALUE_IMAGE_MARKERS
    ):
        score -= 150

    title_words = {
        word
        for word in re.findall(
            r"\w+",
            article_title.lower(),
        )
        if len(word) >= 4
    }

    image_words = set(
        re.findall(
            r"\w+",
            (
                f"{alt_text} {title}"
                .lower()
            ),
        )
    )

    overlap = len(
        title_words
        & image_words
    )

    score += min(
        overlap * 5,
        20,
    )

    return score


def _is_low_value_image(
    *,
    url: str,
    width: Optional[int],
    height: Optional[int],
    alt_text: str,
    title: str,
) -> bool:
    combined = f"{url} {alt_text} {title}".lower()

    if any(
        marker in combined
        for marker in _LOW_VALUE_IMAGE_MARKERS
    ):
        return True

    return bool(
        width is not None
        and height is not None
        and (
            width < 200
            or height < 120
        )
    )


def _build_media(
    *,
    facts: _ArticleHTMLFacts,
    article_node: Optional[
        Mapping[str, Any]
    ],
    base_url: str,
    article_title: str,
) -> Tuple[
    ExternalMedia,
    ...,
]:
    candidates: List[
        Dict[str, Any]
    ] = []

    order = 0

    def add_candidate(
        *,
        raw_url: Any,
        source_kind: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        alt_text: str = "",
        title: str = "",
    ) -> None:
        nonlocal order

        url = _absolute_public_url(
            raw_url,
            base_url,
        )

        if not url:
            return

        candidates.append(
            {
                "url": url,
                "source_kind": (
                    source_kind
                ),
                "width": width,
                "height": height,
                "alt_text": (
                    _clean_text(
                        alt_text
                    )
                ),
                "title": (
                    _clean_text(
                        title
                    )
                ),
                "order": order,
            }
        )

        order += 1

    og_image = _meta_first(
        facts,
        "og:image",
        "og:image:url",
        "og:image:secure_url",
    )

    if og_image:
        add_candidate(
            raw_url=og_image,
            source_kind="og",
            width=_parse_int(
                _meta_first(
                    facts,
                    "og:image:width",
                )
            ),
            height=_parse_int(
                _meta_first(
                    facts,
                    "og:image:height",
                )
            ),
            alt_text=_meta_first(
                facts,
                "og:image:alt",
            ),
        )

    twitter_image = _meta_first(
        facts,
        "twitter:image",
        "twitter:image:src",
    )

    if twitter_image:
        add_candidate(
            raw_url=twitter_image,
            source_kind="twitter",
            alt_text=_meta_first(
                facts,
                "twitter:image:alt",
            ),
        )

    if article_node is not None:
        for (
            raw_url,
            width,
            height,
        ) in _jsonld_image_values(
            article_node.get(
                "image"
            )
        ):
            add_candidate(
                raw_url=raw_url,
                source_kind="json_ld",
                width=width,
                height=height,
            )

    for image in facts.images:
        add_candidate(
            raw_url=image.get(
                "src"
            ),
            source_kind="html",
            width=_parse_int(
                image.get(
                    "width"
                )
            ),
            height=_parse_int(
                image.get(
                    "height"
                )
            ),
            alt_text=_first_nonempty(
                image.get(
                    "alt"
                ),
                image.get(
                    "title"
                ),
            ),
            title=_first_nonempty(
                image.get(
                    "class"
                ),
                image.get(
                    "id"
                ),
            ),
        )

    unique: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for candidate in candidates:
        url = candidate[
            "url"
        ]

        candidate["score"] = (
            _image_score(
                url=url,
                width=candidate[
                    "width"
                ],
                height=candidate[
                    "height"
                ],
                alt_text=candidate[
                    "alt_text"
                ],
                title=candidate[
                    "title"
                ],
                source_kind=candidate[
                    "source_kind"
                ],
                article_title=article_title,
            )
        )

        existing = unique.get(
            url
        )

        if existing is None:
            unique[url] = candidate
            continue

        if (
            candidate["score"]
            > existing["score"]
        ):
            candidate["order"] = min(
                candidate["order"],
                existing["order"],
            )

            unique[url] = candidate

    usable = [
        candidate
        for candidate
        in unique.values()
        if candidate["score"] > -50
        and not _is_low_value_image(
            url=candidate["url"],
            width=candidate["width"],
            height=candidate["height"],
            alt_text=candidate["alt_text"],
            title=candidate["title"],
        )
    ]

    if not usable:
        return ()

    hero = max(
        usable,
        key=lambda item: (
            item["score"],
            -item["order"],
        ),
    )

    remaining = sorted(
        (
            item
            for item in usable
            if item is not hero
        ),
        key=lambda item: (
            -item["score"],
            item["order"],
        ),
    )

    ordered = [
        hero,
        *remaining,
    ][:_MAX_ARTICLE_MEDIA]

    media = []

    for position, item in enumerate(
        ordered
    ):
        media.append(
            ExternalMedia(
                type="photo",
                source_url=item[
                    "url"
                ],
                width=item[
                    "width"
                ],
                height=item[
                    "height"
                ],
                alt_text=item[
                    "alt_text"
                ],
                position=position,
                presentation=(
                    "cover"
                    if position == 0
                    else "gallery"
                ),
                metadata={
                    "source_kind": (
                        item[
                            "source_kind"
                        ]
                    ),
                    "score": item[
                        "score"
                    ],
                    "original_position": (
                        item[
                            "order"
                        ]
                    ),
                },
            )
        )

    return tuple(
        media
    )


def _extract_trafilatura(
    html: str,
    url: str,
) -> Dict[str, Any]:
    try:
        document = bare_extraction(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            deduplicate=True,
            with_metadata=True,
        )
    except Exception:
        return {}

    if document is None:
        return {}

    try:
        data = document.as_dict()
    except AttributeError:
        if isinstance(
            document,
            Mapping,
        ):
            data = dict(
                document
            )
        else:
            return {}

    if not isinstance(
        data,
        Mapping,
    ):
        return {}

    return dict(
        data
    )


def _fallback_body(
    facts: _ArticleHTMLFacts,
    article_node: Optional[
        Mapping[str, Any]
    ],
) -> str:
    if article_node is not None:
        article_body = _clean_text(
            article_node.get(
                "articleBody"
            )
        )

        if article_body:
            return article_body

    useful_paragraphs = []

    for paragraph in facts.paragraphs:
        paragraph = _clean_text(
            paragraph
        )

        if len(paragraph) < 25:
            continue

        if paragraph not in useful_paragraphs:
            useful_paragraphs.append(
                paragraph
            )

    return "\n\n".join(
        useful_paragraphs
    )


def _first_body_paragraph(
    body: str,
) -> str:
    for paragraph in re.split(
        r"\n\s*\n",
        body,
    ):
        paragraph = _clean_text(
            paragraph
        )

        if len(paragraph) >= 30:
            return paragraph

    return ""


def _detect_language(
    text: str,
    declared_language: str,
) -> Tuple[
    str,
    Optional[str],
]:
    declared = _normalize_language(
        declared_language
    )

    sample = _clean_text(
        text
    )

    if len(sample) < 80:
        return (
            declared,
            None,
        )

    try:
        import py3langid
    except ImportError:
        return (
            declared,
            None,
        )

    try:
        detected, _score = (
            py3langid.classify(
                sample[:20000]
            )
        )
    except Exception:
        return (
            declared,
            None,
        )

    detected = _normalize_language(
        detected
    )

    if not detected:
        return (
            declared,
            None,
        )

    if (
        declared
        and declared != detected
    ):
        return (
            detected,
            (
                "declared_language_mismatch:"
                f"{declared}->{detected}"
            ),
        )

    return (
        detected,
        None,
    )


def _is_probable_paywall(
    html: str,
    body: str,
) -> bool:
    haystack = (
        f"{html[:100000]} {body}"
        .lower()
    )

    return any(
        marker in haystack
        for marker
        in _PAYWALL_MARKERS
    )


def _confidence_score(
    *,
    title: str,
    body: str,
    lead: str,
    author: str,
    published_at: str,
    canonical_url: str,
    source_name: str,
    language: str,
    media: Tuple[
        ExternalMedia,
        ...,
    ],
) -> float:
    score = 0.0

    body_length = len(
        body
    )

    if body_length >= 1000:
        score += 0.40

    elif body_length >= 500:
        score += 0.34

    elif body_length >= 200:
        score += 0.24

    elif body_length >= 80:
        score += 0.12

    if title:
        score += 0.15

    if lead:
        score += 0.08

    if author:
        score += 0.05

    if published_at:
        score += 0.05

    if canonical_url:
        score += 0.06

    if source_name:
        score += 0.05

    if language:
        score += 0.06

    if media:
        score += 0.10

    return round(
        min(
            score,
            1.0,
        ),
        3,
    )


class WebArticleExtractor:
    """
    Professional web-news extraction adapter.

    Network acquisition always goes through SafeExternalFetcher.
    The resulting object remains transport-neutral and is not yet
    a PreparedContent publication object.
    """

    def __init__(
        self,
        fetcher: Optional[
            SafeExternalFetcher
        ] = None,
    ) -> None:
        self.fetcher = (
            fetcher
            or SafeExternalFetcher()
        )

    def extract(
        self,
        url: str,
    ) -> NormalizedExternalContent:
        result = self.fetcher.fetch(
            url,
            allowed_content_types={
                "text/html",
                "application/xhtml+xml",
            },
        )

        html = result.text
        final_url = result.final_url

        # -------------------------------------------------
        # HTML / JavaScript transfer-page recovery
        # -------------------------------------------------
        #
        # Some news sites return HTTP 200 for short links and then
        # redirect inside the HTML instead of issuing an HTTP 3xx.
        #
        # Any discovered destination is fetched again only through
        # SafeExternalFetcher, so SSRF / DNS / port / redirect
        # protections remain in force.
        # -------------------------------------------------

        redirect_url = ""

        head = html[:50000]

        # -------------------------------------------------
        # META REFRESH
        # -------------------------------------------------

        meta_refresh_patterns = (
            (
                r"""(?is)<meta[^>]+"""
                r"""http-equiv\s*=\s*["']?refresh["']?"""
                r"""[^>]+content\s*=\s*["']"""
                r"""[^"']*url\s*=\s*([^"'>;]+)"""
            ),
            (
                r"""(?is)<meta[^>]+"""
                r"""content\s*=\s*["']"""
                r"""[^"']*url\s*=\s*([^"'>;]+)"""
                r"""["'][^>]+"""
                r"""http-equiv\s*=\s*["']?refresh["']?"""
            ),
        )

        for pattern in meta_refresh_patterns:
            match = re.search(
                pattern,
                head,
            )

            if not match:
                continue

            redirect_url = _absolute_public_url(
                match.group(1),
                final_url,
            )

            if redirect_url:
                break

        # -------------------------------------------------
        # JAVASCRIPT REDIRECT
        # -------------------------------------------------

        if not redirect_url:
            javascript_patterns = (
                (
                    r"""(?is)window\.location"""
                    r"""(?:\.href)?\s*=\s*"""
                    r"""["']([^"']+)["']"""
                ),
                (
                    r"""(?is)location\.href"""
                    r"""\s*=\s*"""
                    r"""["']([^"']+)["']"""
                ),
                (
                    r"""(?is)location\.replace"""
                    r"""\(\s*["']([^"']+)["']\s*\)"""
                ),
                (
                    r"""(?is)window\.location\.replace"""
                    r"""\(\s*["']([^"']+)["']\s*\)"""
                ),
                (
                    r"""(?is)location\.assign"""
                    r"""\(\s*["']([^"']+)["']\s*\)"""
                ),
                (
                    r"""(?is)window\.location\.assign"""
                    r"""\(\s*["']([^"']+)["']\s*\)"""
                ),
            )

            for pattern in javascript_patterns:
                match = re.search(
                    pattern,
                    head,
                )

                if not match:
                    continue

                redirect_url = _absolute_public_url(
                    match.group(1),
                    final_url,
                )

                if redirect_url:
                    break

        # -------------------------------------------------
        # SIMPLE TRANSFER LINKS
        # -------------------------------------------------
        #
        # Some interstitials have no meta refresh but contain one
        # obvious destination anchor. Only use this fallback when the
        # page itself looks like a transfer page.
        # -------------------------------------------------

        transfer_probe = (
            _clean_text(
                html[:20000]
            )
            .lower()
        )

        transfer_markers = (
            "transferring to the website",
            "redirecting to the website",
            "redirecting...",
            "در حال انتقال به",
            "در حال هدایت به",
            "در حال انتقال به سایت",
        )

        looks_like_transfer_page = any(
            marker in transfer_probe
            for marker in transfer_markers
        )

        if (
            not redirect_url
            and looks_like_transfer_page
        ):
            href_matches = re.findall(
                (
                    r"""(?is)<a[^>]+"""
                    r"""href\s*=\s*["']([^"']+)["']"""
                ),
                head,
            )

            current_host = (
                urlsplit(
                    final_url
                ).hostname
                or ""
            ).lower()

            for href in href_matches:
                candidate = _absolute_public_url(
                    href,
                    final_url,
                )

                if not candidate:
                    continue

                candidate_host = (
                    urlsplit(
                        candidate
                    ).hostname
                    or ""
                ).lower()

                # Ignore empty/self/navigation anchors. An external or
                # meaningfully different article URL is preferred.
                if candidate == final_url:
                    continue

                if not candidate_host:
                    continue

                if (
                    candidate_host == current_host
                    and urlsplit(candidate).path
                    in {
                        "",
                        "/",
                    }
                ):
                    continue

                redirect_url = candidate
                break

        # -------------------------------------------------
        # SAFE SECOND FETCH
        # -------------------------------------------------

        if (
            redirect_url
            and redirect_url != final_url
        ):
            redirected_result = (
                self.fetcher.fetch(
                    redirect_url,
                    allowed_content_types={
                        "text/html",
                        "application/xhtml+xml",
                    },
                )
            )

            html = redirected_result.text
            final_url = (
                redirected_result.final_url
            )

            transfer_probe = (
                _clean_text(
                    html[:20000]
                )
                .lower()
            )

            looks_like_transfer_page = any(
                marker in transfer_probe
                for marker in transfer_markers
            )

        # -------------------------------------------------
        # FAIL CLOSED ON UNRESOLVED INTERSTITIAL
        # -------------------------------------------------

        if looks_like_transfer_page:
            raise WebArticleExtractionError(
                (
                    "web page is a transfer/interstitial "
                    "page and no usable article destination "
                    "could be resolved"
                )
            )

        return self.extract_from_html(
            html,
            source_url=result.requested_url,
            final_url=final_url,
        )

    def extract_from_html(
        self,
        html: str,
        *,
        source_url: str,
        final_url: str = "",
    ) -> NormalizedExternalContent:
        html = str(
            html or ""
        )

        if not html.strip():
            raise WebArticleExtractionError(
                "web article HTML is empty"
            )

        base_url = (
            final_url.strip()
            or source_url.strip()
        )

        base_url = (
            canonicalize_external_url(
                base_url
            )
        )

        facts = _ArticleHTMLFacts()

        try:
            facts.feed(
                html
            )
        except Exception:
            # Metadata inspection failure must not discard a page that
            # Trafilatura may still be able to extract correctly.
            facts = _ArticleHTMLFacts()

        json_ld_nodes = (
            _parse_json_ld(
                facts
            )
        )

        article_node = (
            _select_article_jsonld(
                json_ld_nodes
            )
        )

        trafilatura_data = (
            _extract_trafilatura(
                html,
                base_url,
            )
        )

        json_title = ""

        json_description = ""

        json_author = ""

        json_date = ""

        json_source_name = ""

        json_language = ""

        json_canonical = ""

        json_type = ""

        if article_node is not None:
            json_title = _first_nonempty(
                article_node.get(
                    "headline"
                ),
                article_node.get(
                    "name"
                ),
            )

            json_description = (
                _clean_text(
                    article_node.get(
                        "description"
                    )
                )
            )

            json_author = (
                _extract_author(
                    article_node.get(
                        "author"
                    )
                )
            )

            json_date = (
                _first_nonempty(
                    article_node.get(
                        "datePublished"
                    ),
                    article_node.get(
                        "dateCreated"
                    ),
                )
            )

            json_source_name = (
                _extract_publisher_name(
                    article_node.get(
                        "publisher"
                    )
                )
            )

            json_language = (
                _normalize_language(
                    article_node.get(
                        "inLanguage"
                    )
                )
            )

            json_canonical = (
                _extract_jsonld_url(
                    _first_nonempty(
                        article_node.get(
                            "url"
                        )
                    ),
                    base_url,
                )
            )

            if not json_canonical:
                json_canonical = (
                    _extract_jsonld_url(
                        article_node.get(
                            "mainEntityOfPage"
                        ),
                        base_url,
                    )
                )

            json_types = (
                _jsonld_types(
                    article_node
                )
            )

            if json_types:
                json_type = (
                    json_types[0]
                )

        body = _first_nonempty(
            trafilatura_data.get(
                "text"
            ),
            trafilatura_data.get(
                "raw_text"
            ),
        )

        if not body:
            body = _fallback_body(
                facts,
                article_node,
            )

        title = _first_nonempty(
            json_title,
            _meta_first(
                facts,
                "og:title",
                "twitter:title",
            ),
            trafilatura_data.get(
                "title"
            ),
            (
                facts.h1[0]
                if facts.h1
                else ""
            ),
            facts.title_text,
        )

        lead = _first_nonempty(
            json_description,
            _meta_first(
                facts,
                "og:description",
                "twitter:description",
                "description",
            ),
            trafilatura_data.get(
                "description"
            ),
        )

        if not lead:
            first_paragraph = (
                _first_body_paragraph(
                    body
                )
            )

            if (
                first_paragraph
                and first_paragraph
                != body
            ):
                lead = first_paragraph

        author = _first_nonempty(
            json_author,
            trafilatura_data.get(
                "author"
            ),
            _meta_first(
                facts,
                "author",
                "article:author",
            ),
        )

        published_at = _first_nonempty(
            json_date,
            trafilatura_data.get(
                "date"
            ),
            _meta_first(
                facts,
                "article:published_time",
                "datepublished",
                "date",
            ),
        )

        canonical_url = _first_nonempty(
            _absolute_public_url(
                facts.canonical_href,
                base_url,
            ),
            json_canonical,
            _absolute_public_url(
                _meta_first(
                    facts,
                    "og:url",
                ),
                base_url,
            ),
            _absolute_public_url(
                trafilatura_data.get(
                    "url"
                ),
                base_url,
            ),
            base_url,
        )

        source_name = _first_nonempty(
            json_source_name,
            _meta_first(
                facts,
                "og:site_name",
                "application-name",
            ),
            trafilatura_data.get(
                "sitename"
            ),
            urlsplit(
                canonical_url
            ).hostname,
        )

        declared_language = (
            _first_nonempty(
                json_language,
                _normalize_language(
                    facts.html_language
                ),
                _normalize_language(
                    _meta_first(
                        facts,
                        "content-language",
                        "language",
                    )
                ),
                _normalize_language(
                    trafilatura_data.get(
                        "language"
                    )
                ),
            )
        )

        language, language_warning = (
            _detect_language(
                f"{title}\n\n{lead}\n\n{body}",
                declared_language,
            )
        )

        media = _build_media(
            facts=facts,
            article_node=article_node,
            base_url=canonical_url,
            article_title=title,
        )

        warnings: List[str] = []

        if language_warning:
            warnings.append(
                language_warning
            )

        if not title:
            warnings.append(
                "missing_title"
            )

        if len(body) < 200:
            warnings.append(
                "short_or_incomplete_body"
            )

        if not media:
            warnings.append(
                "no_article_image"
            )

        if _is_probable_paywall(
            html,
            body,
        ):
            warnings.append(
                "possible_paywall"
            )

        if (
            len(body) < 200
            and facts.script_count >= 20
            and len(
                facts.paragraphs
            ) <= 2
        ):
            warnings.append(
                "possible_js_rendered_page"
            )

        confidence = (
            _confidence_score(
                title=title,
                body=body,
                lead=lead,
                author=author,
                published_at=published_at,
                canonical_url=canonical_url,
                source_name=source_name,
                language=language,
                media=media,
            )
        )

        if confidence < 0.45:
            warnings.append(
                "low_extraction_confidence"
            )

        if (
            not title
            and not body
            and not media
        ):
            raise WebArticleExtractionError(
                "no useful article content could be extracted"
            )

        metadata = {
            "extraction_engine": (
                "trafilatura+metadata"
            ),
            "json_ld_article_type": (
                json_type
            ),
            "declared_language": (
                declared_language
            ),
            "paragraph_count": len(
                [
                    item
                    for item in re.split(
                        r"\n\s*\n",
                        body,
                    )
                    if item.strip()
                ]
            ),
            "html_paragraph_count": len(
                facts.paragraphs
            ),
            "script_count": (
                facts.script_count
            ),
            "has_json_ld_article": (
                article_node
                is not None
            ),
            "has_open_graph": bool(
                _meta_first(
                    facts,
                    "og:title",
                    "og:url",
                    "og:image",
                )
            ),
        }

        return NormalizedExternalContent(
            source_type="web_article",
            source_url=(
                canonicalize_external_url(
                    source_url
                )
            ),
            canonical_url=canonical_url,
            content_type="article",
            title=title,
            lead=lead,
            body=body,
            author=author,
            published_at=published_at,
            original_language=language,
            source_name=source_name,
            media=media,
            extraction_confidence=confidence,
            warnings=tuple(
                warnings
            ),
            metadata=metadata,
        )
