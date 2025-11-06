from study_app.gpt import build_guidance_messages


def test_build_guidance_messages_includes_documents_and_mode() -> None:
    profile = {"learning_style": "visual", "goals": "A-level maths"}
    documents = [
        {"id": "doc1", "filename": "chapter1.txt", "word_count": 1200, "excerpt": "Trigonometry identities"}
    ]
    messages = build_guidance_messages(
        profile=profile,
        documents=documents,
        mode="quiz",
        prompt="Check my understanding of sine rules",
        previous_tests=[{"topic": "Trigonometry", "score": "60%", "notes": "Need more practice"}],
        insights={
            "documents": 2,
            "total_words": 2400,
            "assessments": 3,
            "average_score": 72.5,
            "weak_topics": ["Trigonometry"],
            "frequent_topics": ["Trigonometry"],
            "recent_interactions": [],
        },
    )
    assert messages[0]["role"] == "system"
    body = messages[-1]["content"]
    assert "quiz" in body.lower()
    assert "Trigonometry identities" in body
    assert "60%" in body
    assert "Progress analytics" in body
