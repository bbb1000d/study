from study_app.planner import generate_study_plan


def test_generate_study_plan_distributes_topics() -> None:
    profile = {
        "availability": "Mon Wed Fri 2h",
        "tone": "encouraging",
    }
    documents = [
        {"filename": "bio.txt", "topics": ["Biology"]},
        {"filename": "chem.txt", "topics": ["Chemistry"]},
    ]
    assessments = [
        {"topic": "Biology", "score": "45/100"},
        {"topic": "Chemistry", "score": "80%"},
    ]

    plan = generate_study_plan(profile, documents, assessments, days=4)

    assert plan["summary"]["days"] == 4
    assert len(plan["blocks"]) == 4
    focus_topics = {block["focus_topic"] for block in plan["blocks"]}
    assert "Biology" in focus_topics
    assert plan["summary"]["daily_minutes"] >= 45
