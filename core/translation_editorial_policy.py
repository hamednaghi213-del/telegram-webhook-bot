"""Explicit, configurable newsroom terminology; not universal political claims.

This layer edits only listed entity/phrase aliases. It never translates,
publishes, or infers a destination's political preferences.
"""
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EditorialTerminologyRule:
    name: str
    source_expressions: tuple[str, ...]
    approved_term: str
    aliases: tuple[str, ...] = ()
    category: str = "terminology"
    automatic_safe: bool = True
    review_on_ambiguity: bool = True
    context_expressions: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditorialTranslationPolicy:
    name: str = "persian_newsroom_initial"
    target_language: str = "fa"
    enabled: bool = True
    rules: tuple[EditorialTerminologyRule, ...] = ()
    sensitive_expressions: tuple[str, ...] = (
        "terrorist", "terrorists", "terror group", "terrorist group",
        "تروریست", "تروریستی", "تروریست‌ها", "تروریست های",
    )
    # These contexts describe a factual designation/quotation, not merely an
    # entity label. Preserve the wording for a human rather than delete it.
    ambiguous_contexts: tuple[str, ...] = (
        "designated", "designation", "designates", "designating",
        "labelled", "labeled", "classified", "listed as",
        "فهرست تروریستی", "تروریستی اعلام", "تروریستی معرفی",
    )
    forbidden_commentary_expressions: tuple[str, ...] = (
        "رسانه مبدأ", "رسانه مبدا", "منبع مبدأ", "منبع مبدا",
    )


@dataclass(frozen=True)
class EditorialPolicyResult:
    status: str
    output_text: str
    matched_rules: tuple[str, ...] = ()
    normalized_rules: tuple[str, ...] = ()
    reason: str = ""
    quality_instruction: str = ""

    @property
    def requires_review(self) -> bool:
        return self.status == "review_required"

    @property
    def blocked(self) -> bool:
        return self.status in {"blocked", "error"}


PERSIAN_NEWSROOM_POLICY = EditorialTranslationPolicy(rules=(
    EditorialTerminologyRule(
        name="houthi_entity", category="entity_house_style",
        source_expressions=("Houthis", "Houthi", "Houthi movement", "حوثی‌ها", "حوثی ها", "انصارالله"),
        approved_term="حوثی‌ها",
        aliases=(
            "گروه تروریستی حوثی‌ها", "گروه تروریستی حوثی ها",
            "گروه تروریستی حوثی", "حوثی‌های تروریست", "حوثی های تروریست",
            "تروریست‌های حوثی", "تروریست های حوثی",
            "terror group Houthis", "terrorist Houthis", "Houthi terrorist group",
            "Houthis", "Houthi movement", "حوثی ها", "جنبش حوثی‌ها",
        ),
    ),
    EditorialTerminologyRule(
        name="west_asia", category="geographic_house_style",
        source_expressions=("Middle East", "خاورمیانه", "خاور میانه"),
        approved_term="غرب آسیا",
        aliases=("Middle East", "خاورمیانه", "خاور میانه"),
    ),
))


def _phrase(expression: str) -> re.Pattern:
    # ZWNJ is part of Persian words; do not match prefixes or protected tags.
    return re.compile(r"(?<![\w\u200c@#])" + re.escape(expression) + r"(?![\w\u200c])", re.IGNORECASE)


def _protected_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.finditer(
        r'https?://\S+|www\.\S+|[@#][\w\u200c]+|\d+(?:[./:\-]\d+)*|"[^"\n]*"|«[^»\n]*»|“[^”\n]*”', text
    )]


def _matches(text: str, expressions: tuple[str, ...]) -> list[re.Match]:
    return [m for expression in expressions for m in _phrase(expression).finditer(text)]


def apply_editorial_translation_policy(
    *, source_text: str, translated_text: str, target_language: str,
    policy: EditorialTranslationPolicy = PERSIAN_NEWSROOM_POLICY,
) -> EditorialPolicyResult:
    if not policy.enabled or target_language != policy.target_language:
        return EditorialPolicyResult("accepted", translated_text)
    if not translated_text.strip():
        logger.warning("EDITORIAL-TRANSLATION-POLICY | status=blocked | reason=empty_text")
        return EditorialPolicyResult("blocked", "", reason="editorial_policy_empty_text")

    output = translated_text
    matched, normalized, instructions = [], [], []
    review = False
    source_sensitive = _matches(source_text, policy.sensitive_expressions)
    ambiguous = bool(source_sensitive and _matches(source_text, policy.ambiguous_contexts))
    covered_source = []
    for rule in policy.rules:
        if (not rule.name or not rule.approved_term.strip() or not rule.source_expressions
                or any(not item.strip() for item in rule.source_expressions + rule.aliases)
                or "\n" in rule.approved_term or "\r" in rule.approved_term):
            logger.error("EDITORIAL-TRANSLATION-POLICY | status=error | reason=invalid_rule")
            return EditorialPolicyResult("error", "", reason="editorial_policy_invalid_rule")
        concepts = _matches(source_text, rule.source_expressions)
        candidates = _matches(output, rule.aliases + (rule.approved_term,))
        if not candidates:
            continue
        matched.append(rule.name)
        context_ok = not rule.context_expressions or bool(_matches(source_text, rule.context_expressions))
        source_protected = _protected_spans(source_text)
        protected_concept = any(m.start() < end and m.end() > start for m in concepts for start, end in source_protected)
        if not concepts or not context_ok or not rule.automatic_safe or ambiguous or protected_concept:
            if rule.review_on_ambiguity:
                review = True
            continue

        # Protect quoted designations, URLs, handles, tags, numbers and dates.
        protected = _protected_spans(output)
        edits = []
        for match in sorted(candidates, key=lambda m: (m.start(), -len(m.group()))):
            if any(match.start() < end and match.end() > start for start, end in protected):
                review = review or rule.review_on_ambiguity
                continue
            if any(match.start() < end for _, end, _ in edits):
                continue
            edits.append((match.start(), match.end(), rule.approved_term))
        changed = False
        for start, end, replacement in reversed(edits):
            changed = changed or output[start:end] != replacement
            output = output[:start] + replacement + output[end:]
        if changed:
            normalized.append(rule.name)
            instructions.append(f"{rule.name}: {rule.source_expressions + rule.aliases!r} -> {rule.approved_term}")

        # A sensitive label is covered only by an exact listed source phrase;
        # an unrelated sensitive statement elsewhere must still be reviewed.
        covered_source.extend(m.span() for m in _matches(source_text, rule.aliases))
        logger.info("EDITORIAL-TRANSLATION-POLICY | rule=%s | category=%s | normalized=%s", rule.name, rule.category, changed)

    if any(not any(start <= m.start() and end >= m.end() for start, end in covered_source) for m in source_sensitive):
        review = True
    if _matches(output, policy.sensitive_expressions):
        review = True
    # Do not invent explanatory attribution to work around a house-style rule.
    # Such a candidate cannot be safely repaired by deleting an entire sentence.
    if (source_sensitive and matched and _matches(output, policy.sensitive_expressions)
            and _matches(output, policy.forbidden_commentary_expressions)):
        logger.warning("EDITORIAL-TRANSLATION-POLICY | status=blocked | reason=attribution_commentary")
        return EditorialPolicyResult("blocked", "", tuple(matched), tuple(normalized), "editorial_policy_attribution_commentary")

    if ([translated_text[a:b] for a, b in _protected_spans(translated_text)]
            != [output[a:b] for a, b in _protected_spans(output)]
            or translated_text.count("\n") != output.count("\n")):
        logger.error("EDITORIAL-TRANSLATION-POLICY | status=blocked | reason=protected_content_changed")
        return EditorialPolicyResult("blocked", "", tuple(matched), tuple(normalized), "editorial_policy_protected_content_changed")

    status = "review_required" if review else "normalized" if normalized else "accepted"
    logger.info("EDITORIAL-TRANSLATION-POLICY | policy=%s | status=%s", policy.name, status)
    instruction = ""
    if instructions:
        instruction = (
            "Explicit configured newsroom terminology exceptions (house style, not universal facts): "
            + "; ".join(instructions)
            + ". Evaluate the post-policy text allowing only these entity/phrase substitutions. "
            "All events, factual attribution, certainty, names outside these rules, numbers, dates and completeness must still pass unchanged. "
            "Do not excuse unrelated omissions or added commentary."
        )
    return EditorialPolicyResult(status, output, tuple(matched), tuple(normalized),
                                 "editorial_policy_review_required" if review else "", instruction)
