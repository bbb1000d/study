from __future__ import annotations

import os
import importlib.util
from typing import List, Mapping, Optional

_openai_spec = importlib.util.find_spec("openai")
if _openai_spec is not None:
    from openai import OpenAI  # type: ignore
else:  # pragma: no cover - executed only when dependency missing
    OpenAI = None  # type: ignore

DEFAULT_MODEL = "gpt-4o-mini"


class StudyGPT:
    """Wrapper around the OpenAI client with graceful fallbacks for local development."""

    def __init__(self, *, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = OpenAI(api_key=self.api_key) if (self.api_key and OpenAI) else None

    def is_configured(self) -> bool:
        return self._client is not None

    def chat(self, messages: List[Mapping[str, str]], *, temperature: float = 0.4, max_tokens: int = 900) -> str:
        if not self._client:
            return self._offline_response(messages)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _offline_response(self, messages: List[Mapping[str, str]]) -> str:
        summary: List[str] = [
            "[offline-mode] No OpenAI API key detected. Returning summarised plan instead of live AI output.",
        ]
        for message in messages:
            if message["role"] == "user":
                summary.append(f"USER: {message['content']}")
        return "\n".join(summary)


def build_guidance_messages(
    *,
    profile: Mapping[str, object],
    documents: List[Mapping[str, object]],
    mode: str,
    prompt: str,
    previous_tests: List[Mapping[str, object]] | None = None,
    insights: Optional[Mapping[str, object]] = None,
) -> List[Mapping[str, str]]:
    learning_style = profile.get("learning_style", "balanced")
    goals = profile.get("goals", "")
    availability = profile.get("availability", "")
    tone = profile.get("tone", "encouraging")

    docs_section = []
    for document in documents:
        excerpt = document.get("excerpt", "")
        docs_section.append(
            f"Title: {document.get('filename')}\nWord count: {document.get('word_count')}\nExcerpt (review twice):\n{excerpt}\n---"
        )
    docs_text = "\n".join(docs_section) if docs_section else "No documents supplied yet."

    tests_text = "\n".join(
        f"Topic: {item.get('topic')}\nNotes: {item.get('notes')}\nScore: {item.get('score')}" for item in (previous_tests or [])
    )

    system_prompt = f"""
You are StudyMate, an academic mentor for UK learners. You only rely on material supplied by the learner or reputable UK curriculum sources such as gov.uk, bbc.co.uk/bitesize, or official exam boards. You never cite or draw on informal forums.
You craft output in a warm but professional tone. Prefer British English spellings.
Before answering, revisit each provided document excerpt twice. Highlight any knowledge gaps, propose practice activities, and adapt to the learner's style.
"""

    mode_instructions = {
        "plan": "Design a weekly planner with milestones, self-reflection checkpoints, and application tasks.",
        "notes": "Generate in-depth revision notes with analogies, diagrams described in text, and exam tips.",
        "weaknesses": "Identify knowledge gaps and recommend targeted exercises or further reading.",
        "quiz": "Create a short diagnostic quiz (4-6 questions) with answers and feedback.",
        "micro_quiz": "Craft a bite-sized check of 3 questions focused on the least confident idea.",
        "mock": "Build an extended mock paper mirroring the learner's teacher with mark scheme guidance.",
        "apply": "Offer practical application scenarios or projects to embed understanding.",
        "chapter_summary": "Produce a chapter-by-chapter digest with key facts, misconceptions, and revision prompts.",
        "confidence_check": "Ask reflective questions to gauge confidence, then adapt follow-up advice.",
        "exam_drill": "Simulate timed exam practice with pacing tips and examiner commentary.",
    }

    mode_text = mode_instructions.get(mode, "Provide helpful guidance that aligns with the learner's goals.")

    profile_summary = f"Learning style: {learning_style}\nGoals: {goals}\nStudy availability: {availability}\nPreferred tone: {tone}"

    history_section = tests_text or "No prior assessments recorded."

    insight_lines: List[str] = []
    if insights:
        documents_count = insights.get("documents")
        assessments = insights.get("assessments")
        avg = insights.get("average_score")
        weak_topics = ", ".join(insights.get("weak_topics", [])) or "None flagged"
        frequent_topics = ", ".join(insights.get("frequent_topics", [])) or "Not enough data"
        insight_lines.append(f"Stored documents: {documents_count} (total words: {insights.get('total_words', 0)})")
        insight_lines.append(f"Assessments logged: {assessments} · Average score: {avg if avg is not None else 'n/a'}")
        insight_lines.append(f"Weaker topics: {weak_topics}")
        insight_lines.append(f"Most practised topics: {frequent_topics}")
        interactions = insights.get("recent_interactions") or []
        if interactions:
            latest = interactions[0]
            insight_lines.append(
                "Latest request: "
                + latest.get("mode", "coach")
                + " — "
                + latest.get("prompt", "")[:200]
            )
    insight_text = "\n".join(insight_lines) if insight_lines else "No additional insights captured yet."

    user_prompt = f"""
Context about the learner:\n{profile_summary}\n\nTrusted documents to use:\n{docs_text}\n\nPast assessments:\n{history_section}\n\nProgress analytics:\n{insight_text}\n\nTask mode: {mode}\nMode brief: {mode_text}\nSpecific request: {prompt}\n\nRespond with structured headings, UK English, and actionable follow-up questions.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
