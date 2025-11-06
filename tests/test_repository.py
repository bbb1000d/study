from __future__ import annotations

from study_app.repository import StorageRepository, truncate_documents


def create_user(repo: StorageRepository, *, email: str = "alex@example.com", password: str = "hunter222", name: str = "Alex"):
    return repo.create_user(email=email, password=password, name=name)


def test_create_and_authenticate_user(repo: StorageRepository) -> None:
    user = create_user(repo)
    assert user["email"] == "alex@example.com"

    authenticated = repo.authenticate(email="alex@example.com", password="hunter222")
    assert authenticated is not None
    token = repo.create_session(authenticated)
    looked_up = repo.get_user_by_token(token)
    assert looked_up is not None
    assert looked_up["id"] == authenticated["id"]


def test_documents_scoped_per_user(repo: StorageRepository) -> None:
    learner_one = create_user(repo, email="alex@example.com", password="password123")
    learner_two = create_user(repo, email="bea@example.com", password="password123", name="Bea")

    repo.add_document(user=learner_one, filename="bio.txt", content="cell division", topics=["Biology"])
    repo.add_document(user=learner_two, filename="chem.txt", content="organic chemistry", topics=["Chemistry"])

    docs_one = repo.list_documents(learner_one)
    docs_two = repo.list_documents(learner_two)

    assert docs_one[0]["filename"] == "bio.txt"
    assert docs_two[0]["filename"] == "chem.txt"
    assert docs_one[0]["filename"] != docs_two[0]["filename"]


def test_summary_highlights_weak_topics(repo: StorageRepository) -> None:
    user = create_user(repo)
    repo.log_assessment(user, topic="Algebra", score="45/100", notes="Need practice")
    repo.log_assessment(user, topic="Algebra", score="52/100")
    repo.log_assessment(user, topic="Biology", score="18/20")

    summary = repo.summary(user)
    assert "Algebra" in summary["weak_topics"]
    assert summary["average_score"] is not None


def test_truncate_documents_limits_words(repo: StorageRepository) -> None:
    user = create_user(repo)
    repo.add_document(user=user, filename="long.txt", content="word " * 5000)
    documents = repo.list_documents(user)
    trimmed = truncate_documents(documents, word_limit=50)
    assert len(trimmed[0]["excerpt"].split()) == 50


def test_document_lifecycle(repo: StorageRepository) -> None:
    user = create_user(repo)
    created = repo.add_document(user=user, filename="notes.txt", content="energy transfer", topics=["Physics"])
    fetched = repo.get_document(user, created["id"])
    assert fetched["filename"] == "notes.txt"
    assert "energy" in fetched["content"]

    repo.delete_document(user, created["id"])
    remaining = repo.list_documents(user)
    assert remaining == []
