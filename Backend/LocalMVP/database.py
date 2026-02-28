import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


class LocalDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cv_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    json_path TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    experience_years INTEGER DEFAULT 0,
                    education_level TEXT DEFAULT '',
                    search_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tender_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    json_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    required_skills_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS match_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tender_id INTEGER NOT NULL,
                    report_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (tender_id) REFERENCES tender_documents(id)
                );

                CREATE TABLE IF NOT EXISTS match_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    cv_id INTEGER NOT NULL,
                    lexical_score REAL NOT NULL,
                    semantic_score REAL NOT NULL,
                    final_score REAL NOT NULL,
                    matched_skills_json TEXT NOT NULL,
                    missing_skills_json TEXT NOT NULL,
                    justification_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES match_runs(id),
                    FOREIGN KEY (cv_id) REFERENCES cv_documents(id)
                );
                """
            )

    def upsert_cv_document(self, payload: dict[str, Any]) -> sqlite3.Row:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM cv_documents WHERE content_hash = ?",
                (payload["content_hash"],),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE cv_documents
                    SET source_name = ?, file_path = ?, json_path = ?, full_name = ?, email = ?, phone = ?,
                        experience_years = ?, education_level = ?, search_text = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload["source_name"],
                        payload["file_path"],
                        payload["json_path"],
                        payload["full_name"],
                        payload.get("email", ""),
                        payload.get("phone", ""),
                        payload.get("experience_years", 0),
                        payload.get("education_level", ""),
                        payload["search_text"],
                        now,
                        existing["id"],
                    ),
                )
                return conn.execute(
                    "SELECT * FROM cv_documents WHERE id = ?", (existing["id"],)
                ).fetchone()

            conn.execute(
                """
                INSERT INTO cv_documents (
                    source_name, file_path, content_hash, json_path, full_name, email, phone,
                    experience_years, education_level, search_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["source_name"],
                    payload["file_path"],
                    payload["content_hash"],
                    payload["json_path"],
                    payload["full_name"],
                    payload.get("email", ""),
                    payload.get("phone", ""),
                    payload.get("experience_years", 0),
                    payload.get("education_level", ""),
                    payload["search_text"],
                    now,
                    now,
                ),
            )
            return conn.execute(
                "SELECT * FROM cv_documents WHERE content_hash = ?",
                (payload["content_hash"],),
            ).fetchone()

    def insert_tender_document(self, payload: dict[str, Any]) -> sqlite3.Row:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM tender_documents WHERE content_hash = ?",
                (payload["content_hash"],),
            ).fetchone()
            if existing:
                return existing
            conn.execute(
                """
                INSERT INTO tender_documents (
                    source_name, file_path, content_hash, json_path, title, search_text,
                    required_skills_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["source_name"],
                    payload["file_path"],
                    payload["content_hash"],
                    payload["json_path"],
                    payload["title"],
                    payload["search_text"],
                    json.dumps(payload.get("required_skills", []), ensure_ascii=False),
                    now,
                ),
            )
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return conn.execute(
                "SELECT * FROM tender_documents WHERE id = ?", (row_id,)
            ).fetchone()

    def create_match_run(self, tender_id: int, report_path: str) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO match_runs (tender_id, report_path, created_at) VALUES (?, ?, ?)",
                (tender_id, report_path, utc_now()),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def store_match_results(self, run_id: int, results: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM match_results WHERE run_id = ?", (run_id,))
            for result in results:
                conn.execute(
                    """
                    INSERT INTO match_results (
                        run_id, cv_id, lexical_score, semantic_score, final_score,
                        matched_skills_json, missing_skills_json, justification_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        result["cv_id"],
                        result["lexical_score"],
                        result["semantic_score"],
                        result["score"],
                        json.dumps(result["matched_skills"], ensure_ascii=False),
                        json.dumps(result["missing_skills"], ensure_ascii=False),
                        json.dumps(result["justification"], ensure_ascii=False),
                        utc_now(),
                    ),
                )

    def list_cv_documents(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM cv_documents ORDER BY updated_at DESC, id DESC"
            ).fetchall()

    def list_tender_documents(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM tender_documents ORDER BY created_at DESC, id DESC"
            ).fetchall()

    def list_recent_match_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    mr.id,
                    mr.report_path,
                    mr.created_at,
                    td.title AS tender_title,
                    td.source_name AS tender_source
                FROM match_runs mr
                JOIN tender_documents td ON td.id = mr.tender_id
                ORDER BY mr.created_at DESC, mr.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def count_cv_documents(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM cv_documents").fetchone()[0]
