from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import secrets
import sqlite3
from collections import Counter
from typing import Dict, Iterable, List, Mapping, Optional

from .database import DATA_DIR


class StorageRepository:
    """Persist learner accounts, study material, and personalised history in SQLite."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------
    @staticmethod
    def _hash_password(password: str, salt: bytes) -> str:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)
        return base64.b64encode(digest).decode("ascii")

    @staticmethod
    def _generate_salt() -> bytes:
        return secrets.token_bytes(16)

    def create_user(self, *, email: str, password: str, name: str):
        email = email.lower()
        cursor = self.connection.execute("SELECT 1 FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise ValueError("Email already registered")
        salt = self._generate_salt()
        now = dt.datetime.utcnow().isoformat()
        password_hash = self._hash_password(password, salt)
        cursor = self.connection.execute(
            """
            INSERT INTO users (email, name, password_hash, password_salt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, name, password_hash, base64.b64encode(salt).decode("ascii"), now, now),
        )
        self.connection.commit()
        return self.get_user(cursor.lastrowid)

    def get_user(self, user_id: int):
        cursor = self.connection.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return row

    def authenticate(self, *, email: str, password: str):
        cursor = self.connection.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        row = cursor.fetchone()
        if not row:
            return None
        salt = base64.b64decode(row["password_salt"].encode("ascii"))
        candidate = self._hash_password(password, salt)
        if secrets.compare_digest(candidate, row["password_hash"]):
            return row
        return None

    def create_session(self, user_row) -> str:
        token = secrets.token_urlsafe(32)
        now = dt.datetime.utcnow().isoformat()
        self.connection.execute(
            "INSERT INTO sessions (token, user_id, created_at, last_active_at) VALUES (?, ?, ?, ?)",
            (token, user_row["id"], now, now),
        )
        self.connection.commit()
        return token

    def get_user_by_token(self, token: str):
        cursor = self.connection.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id WHERE token = ?",
            (token,),
        )
        row = cursor.fetchone()
        if row:
            self.connection.execute(
                "UPDATE sessions SET last_active_at = ? WHERE token = ?",
                (dt.datetime.utcnow().isoformat(), token),
            )
            self.connection.commit()
        return row

    def revoke_session(self, token: str) -> None:
        self.connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self.connection.commit()

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------
    def load_profile(self, user_row) -> Dict[str, object]:
        return {
            "name": user_row["name"],
            "learning_style": user_row["learning_style"],
            "goals": user_row["goals"],
            "availability": user_row["availability"],
            "tone": user_row["tone"],
        }

    def save_profile(self, user_row, profile: Mapping[str, object]) -> None:
        now = dt.datetime.utcnow().isoformat()
        self.connection.execute(
            """
            UPDATE users
            SET name = ?, learning_style = ?, goals = ?, availability = ?, tone = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(profile.get("name", user_row["name"])),
                str(profile.get("learning_style", user_row["learning_style"])),
                str(profile.get("goals", user_row["goals"])),
                str(profile.get("availability", user_row["availability"])),
                str(profile.get("tone", user_row["tone"] or "encouraging")),
                now,
                user_row["id"],
            ),
        )
        self.connection.commit()

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def add_document(
        self,
        *,
        user,
        filename: str,
        content: str,
        topics: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        now = dt.datetime.utcnow().isoformat()
        topics_json = json.dumps(topics or [])
        word_count = len(content.split())
        cursor = self.connection.execute(
            """
            INSERT INTO documents (user_id, filename, topics, content, word_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user["id"], filename, topics_json, content, word_count, now),
        )
        self.connection.commit()
        return self._serialize_document(cursor.lastrowid)

    def _serialize_document(self, document_id: int) -> Dict[str, object]:
        cursor = self.connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Document not found")
        return {
            "id": row["id"],
            "filename": row["filename"],
            "topics": json.loads(row["topics"] or "[]"),
            "word_count": row["word_count"],
            "created_at": row["created_at"],
            "content": row["content"],
        }

    def list_documents(self, user) -> List[Dict[str, object]]:
        cursor = self.connection.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY datetime(created_at) DESC",
            (user["id"],),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "topics": json.loads(row["topics"] or "[]"),
                "word_count": row["word_count"],
                "created_at": row["created_at"],
                "content": row["content"],
            }
            for row in rows
        ]

    def get_document(self, user, document_id: int) -> Dict[str, object]:
        cursor = self.connection.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (document_id, user["id"]),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Document not found")
        return {
            "id": row["id"],
            "filename": row["filename"],
            "topics": json.loads(row["topics"] or "[]"),
            "word_count": row["word_count"],
            "created_at": row["created_at"],
            "content": row["content"],
        }

    def delete_document(self, user, document_id: int) -> None:
        self.connection.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?",
            (document_id, user["id"]),
        )
        self.connection.commit()

    # ------------------------------------------------------------------
    # Assessments & interactions
    # ------------------------------------------------------------------
    def log_assessment(self, user, *, topic: str, score: str, notes: str = "") -> Dict[str, object]:
        now = dt.datetime.utcnow().isoformat()
        cursor = self.connection.execute(
            """
            INSERT INTO assessments (user_id, topic, score, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], topic, score, notes, now),
        )
        self.connection.commit()
        return self._serialize_assessment(cursor.lastrowid)

    def _serialize_assessment(self, assessment_id: int) -> Dict[str, object]:
        cursor = self.connection.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Assessment not found")
        return {
            "id": row["id"],
            "topic": row["topic"],
            "score": row["score"],
            "notes": row["notes"],
            "timestamp": row["created_at"],
        }

    def list_assessments(self, user) -> List[Dict[str, object]]:
        cursor = self.connection.execute(
            "SELECT * FROM assessments WHERE user_id = ? ORDER BY datetime(created_at) DESC",
            (user["id"],),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "topic": row["topic"],
                "score": row["score"],
                "notes": row["notes"],
                "timestamp": row["created_at"],
            }
            for row in rows
        ]

    def log_interaction(self, user, *, mode: str, prompt: str, response: str) -> None:
        now = dt.datetime.utcnow().isoformat()
        self.connection.execute(
            """
            INSERT INTO interactions (user_id, mode, prompt, response, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], mode, prompt, response, now),
        )
        self.connection.commit()

    def recent_interactions(self, user, limit: int = 5) -> List[Dict[str, object]]:
        cursor = self.connection.execute(
            """
            SELECT mode, prompt, response, created_at
            FROM interactions
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (user["id"], limit),
        )
        rows = cursor.fetchall()
        return [
            {
                "mode": row["mode"],
                "prompt": row["prompt"],
                "response": row["response"][:280],
                "timestamp": row["created_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------
    def summary(self, user) -> Dict[str, object]:
        cursor = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(word_count), 0) FROM documents WHERE user_id = ?",
            (user["id"],),
        )
        doc_count, total_words = cursor.fetchone()

        assessments = self.list_assessments(user)
        average_score = self._calculate_average_score(assessments)
        weak_topics = self._detect_weak_topics(assessments)
        focus_topics = [
            item[0]
            for item in Counter(a.get("topic") for a in assessments if a.get("topic")).most_common(3)
        ]

        return {
            "documents": int(doc_count or 0),
            "total_words": int(total_words or 0),
            "assessments": len(assessments),
            "average_score": average_score,
            "weak_topics": weak_topics,
            "frequent_topics": focus_topics,
            "recent_interactions": self.recent_interactions(user),
        }

    @staticmethod
    def _calculate_average_score(entries: Iterable[Mapping[str, object]]) -> Optional[float]:
        scores: List[float] = []
        for entry in entries:
            value = StorageRepository._interpret_score(str(entry.get("score", "")))
            if value is not None:
                scores.append(value)
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)

    @staticmethod
    def _interpret_score(raw: str) -> Optional[float]:
        if not raw:
            return None
        raw = raw.strip()
        if "/" in raw:
            try:
                achieved, total = raw.split("/", 1)
                achieved_val = float("".join(ch for ch in achieved if ch.isdigit() or ch == "."))
                total_val = float("".join(ch for ch in total if ch.isdigit() or ch == "."))
                if total_val == 0:
                    return None
                return (achieved_val / total_val) * 100
            except ValueError:
                return None
        digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
        if not digits:
            return None
        value = float(digits)
        if value <= 1:
            return value * 100
        if value > 100:
            return None
        return value

    @staticmethod
    def _detect_weak_topics(entries: Iterable[Mapping[str, object]]) -> List[str]:
        bucket: Dict[str, List[float]] = {}
        for entry in entries:
            topic = str(entry.get("topic", "")).strip()
            if not topic:
                continue
            score = StorageRepository._interpret_score(str(entry.get("score", "")))
            if score is None:
                continue
            bucket.setdefault(topic, []).append(score)
        weak = [topic for topic, values in bucket.items() if values and (sum(values) / len(values)) < 70]
        return sorted(weak)


def truncate_documents(documents: List[Mapping[str, object]], *, word_limit: int = 1600) -> List[Dict[str, object]]:
    trimmed: List[Dict[str, object]] = []
    for document in documents:
        content = str(document.get("content", ""))
        words = content.split()
        excerpt = " ".join(words[:word_limit])
        trimmed.append(
            {
                "id": document.get("id"),
                "filename": document.get("filename"),
                "topics": document.get("topics", []),
                "word_count": document.get("word_count"),
                "excerpt": excerpt,
            }
        )
    return trimmed
