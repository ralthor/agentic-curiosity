from __future__ import annotations

import re
from collections.abc import Sequence

EXPECTATION_SCORE_MIN = 0
EXPECTATION_SCORE_MAX = 4

_EXPECTATION_PREFIX_RE = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")
_SCORE_STATUS = {
    0: "not_started",
    1: "introduced",
    2: "developing",
    3: "secure",
    4: "mastered",
}


def _clean_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _clean_expectation(value) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    return _EXPECTATION_PREFIX_RE.sub("", cleaned).strip()


def normalize_expectations(raw_expectations) -> list[str]:
    if raw_expectations is None:
        return []

    if isinstance(raw_expectations, str):
        items = raw_expectations.splitlines()
    elif isinstance(raw_expectations, Sequence) and not isinstance(raw_expectations, (str, bytes)):
        items = list(raw_expectations)
    else:
        raise ValueError("expectations must be provided as a list of strings.")

    expectations: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise ValueError("Each expectation must be a string.")
        cleaned = _clean_expectation(item)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        expectations.append(cleaned)

    return expectations


def require_expectations(raw_expectations) -> list[str]:
    expectations = normalize_expectations(raw_expectations)
    if not expectations:
        raise ValueError("expectations must contain at least one item.")
    return expectations


def score_to_status(score: int) -> str:
    return _SCORE_STATUS[_normalize_score(score)]


def _normalize_score(raw_score) -> int:
    if isinstance(raw_score, bool):
        parsed = int(raw_score)
    elif isinstance(raw_score, int):
        parsed = raw_score
    elif isinstance(raw_score, float):
        parsed = round(raw_score)
    elif isinstance(raw_score, str):
        stripped = raw_score.strip()
        if not stripped:
            parsed = 0
        else:
            try:
                parsed = round(float(stripped))
            except ValueError:
                parsed = 0
    else:
        parsed = 0

    return max(EXPECTATION_SCORE_MIN, min(EXPECTATION_SCORE_MAX, parsed))


def _coerce_state_expectations(raw_expectations) -> list[dict[str, object]]:
    if not isinstance(raw_expectations, Sequence) or isinstance(raw_expectations, (str, bytes)):
        return []

    expectations: list[dict[str, object]] = []
    for item in raw_expectations:
        if isinstance(item, str):
            cleaned = _clean_expectation(item)
            if cleaned:
                expectations.append(
                    {
                        "expectation": cleaned,
                        "score": 0,
                        "status": score_to_status(0),
                        "evidence": "",
                    }
                )
            continue

        if not isinstance(item, dict):
            continue

        cleaned = _clean_expectation(item.get("expectation"))
        if not cleaned:
            continue

        score = _normalize_score(item.get("score"))
        expectations.append(
            {
                "expectation": cleaned,
                "score": score,
                "status": score_to_status(score),
                "evidence": _clean_text(item.get("evidence")),
            }
        )

    return expectations


def calculate_course_progress(expectations: Sequence[dict[str, object]]) -> int:
    if not expectations:
        return 0

    total_score = sum(_normalize_score(item.get("score")) for item in expectations)
    return round((total_score / (len(expectations) * EXPECTATION_SCORE_MAX)) * 100)


def _pick_current_item(expectations: Sequence[dict[str, object]]) -> str | None:
    for item in expectations:
        score = _normalize_score(item.get("score"))
        if EXPECTATION_SCORE_MIN < score < EXPECTATION_SCORE_MAX:
            return str(item["expectation"])

    for item in expectations:
        if _normalize_score(item.get("score")) < EXPECTATION_SCORE_MAX:
            return str(item["expectation"])

    if expectations:
        return str(expectations[-1]["expectation"])
    return None


def _pick_next_item(expectations: Sequence[dict[str, object]]) -> str | None:
    for item in expectations:
        if _normalize_score(item.get("score")) < EXPECTATION_SCORE_MAX:
            return str(item["expectation"])
    return None


def build_initial_course_state(expectations) -> dict[str, object]:
    normalized_expectations = normalize_expectations(expectations)
    expectation_states = [
        {
            "expectation": expectation,
            "score": 0,
            "status": score_to_status(0),
            "evidence": "",
        }
        for expectation in normalized_expectations
    ]
    first_item = normalized_expectations[0] if normalized_expectations else None
    return {
        "expectations": expectation_states,
        "overall_progress": 0,
        "current_item": first_item,
        "next_item": first_item,
        "summary": "No assessed evidence yet.",
        "reply_focus": "Start with the first unmet expectation." if first_item else "",
    }


def normalize_course_state(
    raw_state,
    *,
    expectations=None,
) -> dict[str, object]:
    if not isinstance(raw_state, dict):
        raw_state = {}

    state_expectations = _coerce_state_expectations(raw_state.get("expectations"))
    topic_expectations = (
        normalize_expectations(expectations)
        if expectations is not None
        else [str(item["expectation"]) for item in state_expectations]
    )

    expectation_map = {str(item["expectation"]).casefold(): item for item in state_expectations}
    normalized_expectations: list[dict[str, object]] = []
    for expectation in topic_expectations:
        existing = expectation_map.get(expectation.casefold(), {})
        score = _normalize_score(existing.get("score"))
        normalized_expectations.append(
            {
                "expectation": expectation,
                "score": score,
                "status": score_to_status(score),
                "evidence": _clean_text(existing.get("evidence")),
            }
        )

    current_item = _clean_text(raw_state.get("current_item")) or _pick_current_item(normalized_expectations)
    next_item = _clean_text(raw_state.get("next_item")) or _pick_next_item(normalized_expectations)
    summary = _clean_text(raw_state.get("summary"))
    reply_focus = _clean_text(raw_state.get("reply_focus"))

    return {
        "expectations": normalized_expectations,
        "overall_progress": calculate_course_progress(normalized_expectations),
        "current_item": current_item or None,
        "next_item": next_item or None,
        "summary": summary or ("No assessed evidence yet." if normalized_expectations else ""),
        "reply_focus": reply_focus,
    }


def build_course_state_note(course_state) -> str:
    normalized_state = normalize_course_state(course_state)
    if not normalized_state["expectations"]:
        return ""

    lines = [f"Overall progress: {normalized_state['overall_progress']}%."]
    if normalized_state["current_item"]:
        lines.append(f"Current item: {normalized_state['current_item']}.")
    if normalized_state["next_item"]:
        lines.append(f"Next item: {normalized_state['next_item']}.")
    if normalized_state["summary"]:
        lines.append(f"Planner summary: {normalized_state['summary']}")
    if normalized_state["reply_focus"]:
        lines.append(f"Reply focus: {normalized_state['reply_focus']}")

    lines.append("Expectation scores (0-4):")
    for item in normalized_state["expectations"]:
        evidence = str(item["evidence"])
        suffix = f" Evidence: {evidence}" if evidence else ""
        lines.append(
            f"- {item['expectation']}: {item['score']}/4 ({item['status']}).{suffix}"
        )

    return "\n".join(lines)
