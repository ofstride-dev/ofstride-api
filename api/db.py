from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Callable, Optional

from .config import DATA_DIR, DB_FILE, CONSULTANTS_FILE, HR_CANDIDATE_FILE, HR_HIRING_FILE, LEADS_FILE, NOTIFY_FILE


def ensure_file(path: Path, header: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                timestamp TEXT,
                name TEXT,
                phone TEXT,
                location TEXT,
                company TEXT,
                task_summary TEXT,
                preferred_time TEXT,
                preferred_timezone TEXT
            );
            CREATE TABLE IF NOT EXISTS consultants (
                name TEXT,
                location TEXT,
                mobile TEXT,
                role TEXT,
                email TEXT
            );
            CREATE TABLE IF NOT EXISTS notifications (
                timestamp TEXT,
                lead_name TEXT,
                lead_phone TEXT,
                consultant_name TEXT,
                consultant_phone TEXT,
                consultant_email TEXT,
                task_summary TEXT,
                preferred_time TEXT,
                preferred_timezone TEXT
            );
            CREATE TABLE IF NOT EXISTS hr_hiring_requests (
                timestamp TEXT,
                company TEXT,
                role_title TEXT,
                employment_type TEXT,
                work_mode TEXT,
                location TEXT,
                experience TEXT,
                skills TEXT,
                positions_count TEXT,
                salary_range TEXT,
                urgency TEXT,
                contract_duration TEXT,
                office_address TEXT,
                timezone TEXT,
                contact_name TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS hr_candidate_profiles (
                timestamp TEXT,
                full_name TEXT,
                email TEXT,
                phone TEXT,
                location TEXT,
                role_interest TEXT,
                experience TEXT,
                skills TEXT,
                linkedin TEXT,
                portfolio TEXT,
                resume_path TEXT
            );
            """
        )


def _table_is_empty(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.execute(f"SELECT COUNT(*) as total FROM {table}")
    row = cursor.fetchone()
    return (row["total"] if row else 0) == 0


def normalize_csv_file(path: Path, header: list[str], row_mapper: Optional[Callable[[list[str]], list[str]]] = None) -> None:
    if not path.exists():
        return
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = list(reader)

    if not rows:
        return

    data_rows = rows[1:] if rows else []
    normalized: list[list[str]] = []

    for row in data_rows:
        if not row or all(not str(item).strip() for item in row):
            continue
        items = [str(item).strip() for item in row]
        if row_mapper:
            items = row_mapper(items)
        if len(items) < len(header):
            items = items + [""] * (len(header) - len(items))
        elif len(items) > len(header):
            items = items[: len(header)]
        normalized.append(items)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(normalized)


def migrate_csv_to_db() -> None:
    ensure_file(CONSULTANTS_FILE, ["name", "location", "mobile", "role", "email"])
    ensure_file(
        LEADS_FILE,
        [
            "timestamp",
            "name",
            "phone",
            "location",
            "company",
            "task_summary",
            "preferred_time",
            "preferred_timezone",
        ],
    )
    ensure_file(
        NOTIFY_FILE,
        [
            "timestamp",
            "lead_name",
            "lead_phone",
            "consultant_name",
            "consultant_phone",
            "consultant_email",
            "task_summary",
            "preferred_time",
            "preferred_timezone",
        ],
    )
    ensure_file(
        HR_HIRING_FILE,
        [
            "timestamp",
            "company",
            "role_title",
            "employment_type",
            "work_mode",
            "location",
            "experience",
            "skills",
            "positions_count",
            "salary_range",
            "urgency",
            "contract_duration",
            "office_address",
            "timezone",
            "contact_name",
            "contact_email",
            "contact_phone",
            "notes",
        ],
    )
    ensure_file(
        HR_CANDIDATE_FILE,
        [
            "timestamp",
            "full_name",
            "email",
            "phone",
            "location",
            "role_interest",
            "experience",
            "skills",
            "linkedin",
            "portfolio",
            "resume_path",
        ],
    )

    with get_db() as conn:
        if _table_is_empty(conn, "consultants") and CONSULTANTS_FILE.exists():
            with CONSULTANTS_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO consultants (name, location, mobile, role, email)
                    VALUES (:name, :location, :mobile, :role, :email)
                    """,
                    rows,
                )
        if _table_is_empty(conn, "leads") and LEADS_FILE.exists():
            with LEADS_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO leads (timestamp, name, phone, location, company, task_summary, preferred_time, preferred_timezone)
                    VALUES (:timestamp, :name, :phone, :location, :company, :task_summary, :preferred_time, :preferred_timezone)
                    """,
                    rows,
                )
        if _table_is_empty(conn, "notifications") and NOTIFY_FILE.exists():
            with NOTIFY_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO notifications (timestamp, lead_name, lead_phone, consultant_name, consultant_phone, consultant_email, task_summary, preferred_time, preferred_timezone)
                    VALUES (:timestamp, :lead_name, :lead_phone, :consultant_name, :consultant_phone, :consultant_email, :task_summary, :preferred_time, :preferred_timezone)
                    """,
                    rows,
                )
        if _table_is_empty(conn, "hr_hiring_requests") and HR_HIRING_FILE.exists():
            with HR_HIRING_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO hr_hiring_requests (
                        timestamp, company, role_title, employment_type, work_mode, location, experience, skills,
                        positions_count, salary_range, urgency, contract_duration, office_address, timezone,
                        contact_name, contact_email, contact_phone, notes
                    )
                    VALUES (
                        :timestamp, :company, :role_title, :employment_type, :work_mode, :location, :experience, :skills,
                        :positions_count, :salary_range, :urgency, :contract_duration, :office_address, :timezone,
                        :contact_name, :contact_email, :contact_phone, :notes
                    )
                    """,
                    rows,
                )
        if _table_is_empty(conn, "hr_candidate_profiles") and HR_CANDIDATE_FILE.exists():
            with HR_CANDIDATE_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO hr_candidate_profiles (
                        timestamp, full_name, email, phone, location, role_interest, experience, skills,
                        linkedin, portfolio, resume_path
                    )
                    VALUES (
                        :timestamp, :full_name, :email, :phone, :location, :role_interest, :experience, :skills,
                        :linkedin, :portfolio, :resume_path
                    )
                    """,
                    rows,
                )
