from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

EXPECTATION_SCORE_MIN = 0
EXPECTATION_SCORE_MAX = 4
ACTIVE_WINDOW_RADIUS = 1

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
    elif isinstance(raw_expectations, Sequence) and not isinstance(raw_expectations, (str, bytes, bytearray)):
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


def score_to_status(score: int) -> str:
    return _SCORE_STATUS[_normalize_score(score)]


def _normalize_index(raw_index, *, limit: int) -> int | None:
    if limit <= 0:
        return None

    if isinstance(raw_index, bool):
        parsed = int(raw_index)
    elif isinstance(raw_index, int):
        parsed = raw_index
    elif isinstance(raw_index, str) and raw_index.strip().lstrip("-").isdigit():
        parsed = int(raw_index.strip())
    else:
        return None

    if 0 <= parsed < limit:
        return parsed
    return None


def _normalize_index_list(raw_indexes, *, limit: int) -> list[int]:
    if not isinstance(raw_indexes, Sequence) or isinstance(raw_indexes, (str, bytes, bytearray)):
        return []

    normalized: list[int] = []
    seen: set[int] = set()
    for item in raw_indexes:
        index = _normalize_index(item, limit=limit)
        if index is None or index in seen:
            continue
        seen.add(index)
        normalized.append(index)
    return normalized


def _normalize_scores(raw_scores, *, count: int) -> list[int]:
    scores = [0] * count

    if isinstance(raw_scores, Sequence) and not isinstance(raw_scores, (str, bytes, bytearray)):
        for index, raw_score in enumerate(list(raw_scores)[:count]):
            scores[index] = _normalize_score(raw_score)
        return scores

    if isinstance(raw_scores, Mapping):
        for raw_index, raw_score in raw_scores.items():
            index = _normalize_index(raw_index, limit=count)
            if index is None:
                continue
            scores[index] = _normalize_score(raw_score)
        return scores

    return scores


def _extract_legacy_scores(raw_state: Mapping[str, object], expectations: Sequence[str]) -> list[int]:
    scores = [0] * len(expectations)
    legacy_items = raw_state.get("expectations")
    if not isinstance(legacy_items, Sequence) or isinstance(legacy_items, (str, bytes, bytearray)):
        return scores

    score_by_expectation: dict[str, int] = {}
    for item in legacy_items:
        if not isinstance(item, Mapping):
            continue
        expectation = _clean_expectation(item.get("expectation"))
        if not expectation:
            continue
        score_by_expectation[expectation.casefold()] = _normalize_score(item.get("score"))

    for index, expectation in enumerate(expectations):
        scores[index] = score_by_expectation.get(expectation.casefold(), 0)

    return scores


def _first_incomplete_index(scores: Sequence[int], *, start: int = 0) -> int | None:
    for index in range(max(start, 0), len(scores)):
        if scores[index] < EXPECTATION_SCORE_MAX:
            return index
    return None


def _derive_current_index(scores: Sequence[int]) -> int | None:
    if not scores:
        return None
    first_incomplete = _first_incomplete_index(scores, start=0)
    if first_incomplete is not None:
        return first_incomplete
    return len(scores) - 1


def _derive_next_index(scores: Sequence[int], *, current_index: int | None) -> int | None:
    if not scores:
        return None
    if current_index is None:
        return _first_incomplete_index(scores, start=0)
    if scores[current_index] < EXPECTATION_SCORE_MAX:
        return current_index
    return _first_incomplete_index(scores, start=current_index + 1)


def build_initial_course_state(expectations) -> dict[str, object]:
    normalized_expectations = normalize_expectations(expectations)
    scores = [0] * len(normalized_expectations)
    first_index = 0 if normalized_expectations else None
    return {
        "scores": scores,
        "current_expectation_index": first_index,
        "next_expectation_index": first_index,
        "review_indexes": [],
        "recent_evidence_summary": "No assessed evidence yet." if normalized_expectations else "",
        "reply_focus": "Start with the current expectation." if normalized_expectations else "",
    }


def normalize_course_state(
    raw_state,
    *,
    expectations=None,
) -> dict[str, object]:
    normalized_expectations = normalize_expectations(expectations)
    if not isinstance(raw_state, Mapping):
        raw_state = {}

    scores = _normalize_scores(raw_state.get("scores"), count=len(normalized_expectations))
    if not any(scores) and raw_state.get("expectations"):
        scores = _extract_legacy_scores(raw_state, normalized_expectations)

    current_index = _normalize_index(
        raw_state.get("current_expectation_index"),
        limit=len(normalized_expectations),
    )
    next_index = _normalize_index(
        raw_state.get("next_expectation_index"),
        limit=len(normalized_expectations),
    )

    if current_index is None:
        current_index = _derive_current_index(scores)
    if next_index is None:
        next_index = _derive_next_index(scores, current_index=current_index)

    return {
        "scores": scores,
        "current_expectation_index": current_index,
        "next_expectation_index": next_index,
        "review_indexes": _normalize_index_list(
            raw_state.get("review_indexes"),
            limit=len(normalized_expectations),
        ),
        "recent_evidence_summary": (
            _clean_text(raw_state.get("recent_evidence_summary"))
            or _clean_text(raw_state.get("summary"))
            or ("No assessed evidence yet." if normalized_expectations else "")
        ),
        "reply_focus": _clean_text(raw_state.get("reply_focus")),
    }


def calculate_course_progress(scores: Sequence[int]) -> int:
    if not scores:
        return 0
    return round((sum(_normalize_score(score) for score in scores) / (len(scores) * EXPECTATION_SCORE_MAX)) * 100)


def _expectation_at(expectations: Sequence[str], index: int | None) -> str | None:
    if index is None:
        return None
    if 0 <= index < len(expectations):
        return expectations[index]
    return None


def serialize_course_state(
    course_state,
    *,
    expectations=None,
) -> dict[str, object]:
    normalized_expectations = normalize_expectations(expectations)
    state = normalize_course_state(course_state, expectations=normalized_expectations)
    scores = state["scores"]
    current_index = state["current_expectation_index"]
    next_index = state["next_expectation_index"]
    review_indexes = set(state["review_indexes"])

    expectation_rows = []
    for index, expectation in enumerate(normalized_expectations):
        score = scores[index]
        expectation_rows.append(
            {
                "expectation": expectation,
                "score": score,
                "status": score_to_status(score),
                "is_current": index == current_index,
                "is_next": index == next_index,
                "needs_review": index in review_indexes,
            }
        )

    return {
        "expectations": expectation_rows,
        "scores": list(scores),
        "overall_progress": calculate_course_progress(scores),
        "current_expectation_index": current_index,
        "next_expectation_index": next_index,
        "current_item": _expectation_at(normalized_expectations, current_index),
        "next_item": _expectation_at(normalized_expectations, next_index),
        "review_items": [
            normalized_expectations[index]
            for index in state["review_indexes"]
            if 0 <= index < len(normalized_expectations)
        ],
        "recent_evidence_summary": state["recent_evidence_summary"],
        "reply_focus": state["reply_focus"],
    }


def build_active_course_state_payload(
    course_state,
    *,
    expectations=None,
    window_radius: int = ACTIVE_WINDOW_RADIUS,
) -> dict[str, object]:
    normalized_expectations = normalize_expectations(expectations)
    serialized = serialize_course_state(course_state, expectations=normalized_expectations)
    scores = serialized["scores"]
    current_index = serialized["current_expectation_index"]
    next_index = serialized["next_expectation_index"]

    window_indexes: list[int] = []
    if current_index is not None:
        start = max(current_index - window_radius, 0)
        end = min(current_index + window_radius + 1, len(normalized_expectations))
        window_indexes.extend(range(start, end))
    if next_index is not None and next_index not in window_indexes:
        window_indexes.append(next_index)

    return {
        "overall_progress": serialized["overall_progress"],
        "current_expectation_index": current_index,
        "current_expectation": serialized["current_item"],
        "current_score": (
            scores[current_index]
            if current_index is not None and 0 <= current_index < len(scores)
            else EXPECTATION_SCORE_MIN
        ),
        "next_expectation_index": next_index,
        "next_expectation": serialized["next_item"],
        "next_score": (
            scores[next_index]
            if next_index is not None and 0 <= next_index < len(scores)
            else EXPECTATION_SCORE_MIN
        ),
        "review_items": serialized["review_items"][:2],
        "recent_evidence_summary": serialized["recent_evidence_summary"],
        "reply_focus": serialized["reply_focus"],
        "active_window": [
            {
                "expectation_index": index,
                "expectation": normalized_expectations[index],
                "score": scores[index],
                "status": score_to_status(scores[index]),
            }
            for index in sorted(set(window_indexes))
            if 0 <= index < len(normalized_expectations)
        ],
    }


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def apply_course_state_patch(
    course_state,
    patch,
    *,
    expectations=None,
) -> dict[str, object]:
    normalized_expectations = normalize_expectations(expectations)
    state = normalize_course_state(course_state, expectations=normalized_expectations)
    if not isinstance(patch, Mapping):
        return state

    scores = list(state["scores"])
    count = len(scores)

    for update in patch.get("score_updates", []):
        if not isinstance(update, Mapping):
            continue
        index = _normalize_index(update.get("expectation_index"), limit=count)
        if index is None:
            continue
        scores[index] = _normalize_score(update.get("score"))

    current_index = _normalize_index(
        patch.get("current_expectation_index"),
        limit=count,
    )
    if current_index is None:
        current_index = state["current_expectation_index"]

    if "current_score" in patch and current_index is not None:
        scores[current_index] = _normalize_score(patch.get("current_score"))

    next_index = _normalize_index(
        patch.get("next_expectation_index"),
        limit=count,
    )
    if next_index is None:
        next_index = state["next_expectation_index"]

    if _coerce_bool(patch.get("advance_to_next")):
        advanced_index = _first_incomplete_index(scores, start=(current_index or -1) + 1)
        if advanced_index is not None:
            current_index = advanced_index
        next_index = _derive_next_index(scores, current_index=current_index)

    new_state = {
        "scores": scores,
        "current_expectation_index": current_index,
        "next_expectation_index": next_index,
        "review_indexes": (
            _normalize_index_list(patch.get("review_indexes"), limit=count)
            or state["review_indexes"]
        ),
        "recent_evidence_summary": (
            _clean_text(patch.get("recent_evidence_summary"))
            or state["recent_evidence_summary"]
        ),
        "reply_focus": (
            _clean_text(patch.get("reply_focus"))
            or state["reply_focus"]
        ),
    }
    return normalize_course_state(new_state, expectations=normalized_expectations)


def build_course_state_note(
    course_state,
    *,
    expectations=None,
) -> str:
    serialized = serialize_course_state(course_state, expectations=expectations)
    if not serialized["expectations"]:
        return ""

    current_score = EXPECTATION_SCORE_MIN
    current_index = serialized["current_expectation_index"]
    if current_index is not None and 0 <= current_index < len(serialized["scores"]):
        current_score = serialized["scores"][current_index]

    lines: list[str] = []
    if serialized["current_item"]:
        lines.append(f"Current item: {serialized['current_item']}.")
        lines.append(f"Current mastery: {current_score}/4 ({score_to_status(current_score)}).")
    if serialized["next_item"]:
        lines.append(f"Next item: {serialized['next_item']}.")
    if serialized["review_items"]:
        lines.append(f"Review soon: {', '.join(serialized['review_items'][:2])}.")
    if serialized["recent_evidence_summary"]:
        lines.append(f"Recent evidence: {serialized['recent_evidence_summary']}")
    if serialized["reply_focus"]:
        lines.append(f"Reply focus: {serialized['reply_focus']}")
    lines.append(f"Overall progress: {serialized['overall_progress']}%.")
    return "\n".join(lines)
