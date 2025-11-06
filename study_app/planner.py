"""Generate structured study plans based on saved learner data."""

from __future__ import annotations

import datetime as dt
import itertools
import re
from typing import List, Mapping, Sequence


def _infer_daily_minutes(availability: str | None) -> int:
    """Infer a sensible number of study minutes per day from profile text."""

    if not availability:
        return 120

    availability_lower = availability.lower()
    hour_matches = [int(match) for match in re.findall(r"(\d+)\s*(?:h|hour)", availability_lower)]
    minute_matches = [int(match) for match in re.findall(r"(\d+)\s*(?:m|min|minute)", availability_lower)]

    total_minutes = sum(hour * 60 for hour in hour_matches) + sum(minute_matches)
    if total_minutes == 0:
        number_matches = [int(match) for match in re.findall(r"(\d+)", availability_lower)]
        if number_matches:
            # Assume the learner meant hours if they only typed numbers.
            total_minutes = number_matches[0] * 60

    # Spread the available time across an estimated four study days.
    if total_minutes:
        return max(45, total_minutes // max(len(hour_matches) or len(minute_matches) or 4, 1))
    return 120


def _score_to_percentage(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if "/" in cleaned:
        achieved, total = cleaned.split("/", 1)
        try:
            achieved_value = float(re.sub(r"[^0-9.]", "", achieved) or 0)
            total_value = float(re.sub(r"[^0-9.]", "", total) or 0)
        except ValueError:
            return None
        if total_value <= 0:
            return None
        return (achieved_value / total_value) * 100
    digits = re.sub(r"[^0-9.]", "", cleaned)
    if not digits:
        return None
    value = float(digits)
    if value <= 1:
        return value * 100
    if value > 100:
        return None
    return value


def _collect_topics(documents: Sequence[Mapping[str, object]], assessments: Sequence[Mapping[str, object]]) -> List[str]:
    topics: List[str] = []
    for document in documents:
        for topic in document.get("topics", []) or []:
            topic_name = str(topic).strip()
            if topic_name and topic_name not in topics:
                topics.append(topic_name)
    for assessment in assessments:
        topic = str(assessment.get("topic", "")).strip()
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def _prioritise_topics(topics: Sequence[str], assessments: Sequence[Mapping[str, object]]) -> List[str]:
    if not topics:
        return []

    topic_scores: dict[str, List[float]] = {topic: [] for topic in topics}
    for assessment in assessments:
        topic = str(assessment.get("topic", "")).strip()
        if topic not in topic_scores:
            continue
        score = _score_to_percentage(str(assessment.get("score")))
        if score is not None:
            topic_scores[topic].append(score)

    def priority(topic: str) -> tuple[int, float]:
        scores = topic_scores.get(topic) or []
        if not scores:
            return (0, 0.0)
        average = sum(scores) / len(scores)
        return (1 if average < 70 else 2, average)

    ordered = sorted(topics, key=lambda topic: (priority(topic)[0], priority(topic)[1]))
    return ordered


def generate_study_plan(
    profile: Mapping[str, object],
    documents: Sequence[Mapping[str, object]],
    assessments: Sequence[Mapping[str, object]],
    *,
    days: int = 7,
) -> Mapping[str, object]:
    """Return a structured weekly plan tailored to the learner."""

    today = dt.date.today()
    topics = _collect_topics(documents, assessments)
    ordered_topics = _prioritise_topics(topics, assessments)
    if not ordered_topics:
        ordered_topics = ["Independent revision"]

    daily_minutes = _infer_daily_minutes(str(profile.get("availability", "")))
    deep_focus = max(30, int(daily_minutes * 0.6))
    recap_time = max(15, daily_minutes - deep_focus)

    focus_cycle = itertools.cycle(ordered_topics)
    review_cycle = itertools.cycle(reversed(ordered_topics))

    blocks = []
    for index in range(days):
        current_date = today + dt.timedelta(days=index)
        focus_topic = next(focus_cycle)
        review_topic = next(review_cycle)
        blocks.append(
            {
                "date": current_date.isoformat(),
                "focus_topic": focus_topic,
                "review_topic": review_topic,
                "deep_focus_minutes": deep_focus,
                "recap_minutes": recap_time,
                "checkpoint": "Log a mini-quiz or reflection once finished.",
            }
        )

    plan_summary = {
        "days": days,
        "daily_minutes": daily_minutes,
        "topics": ordered_topics,
        "tone": profile.get("tone", "encouraging"),
    }

    return {"summary": plan_summary, "blocks": blocks}


__all__ = ["generate_study_plan"]

