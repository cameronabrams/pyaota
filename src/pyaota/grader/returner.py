"""
returner.py

Email graded answer sheets and exam version PDFs to students
via Outlook COM automation (Windows).
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_id(s: str) -> str:
    stripped = s.lstrip("0")
    return stripped if stripped else "0"


def return_graded_exams(
    gradebook_paths: List[Path | str],
    graded_dir: Path | str,
    exams_dir: Path | str,
    email_column: str = "Username",
    email_suffix: str = "@drexel.edu",
    subject: str = "Your graded exam",
    body: str = (
        "Attached are your graded answer sheet and a copy of the exam you took.\n"
        "If you have questions about your grade, please contact your instructor."
    ),
    dry_run: bool = False,
):
    """
    Email each student their graded answer sheet and exam version PDF.

    Parameters
    ----------
    gradebook_paths : list of Path | str
        Gradebook CSVs with ``Student ID`` and *email_column* columns.
    graded_dir : Path | str
        Directory containing ``graded_<student_id>_<version>.pdf`` files.
    exams_dir : Path | str
        Directory containing ``exam-<version>.pdf`` files.
    email_column : str
        Column name in the gradebook that holds the email (or email prefix).
    email_suffix : str
        Suffix appended to the email column value (e.g. ``@drexel.edu``).
        Set to ``""`` if the column already contains full addresses.
    subject : str
        Email subject line.
    body : str
        Plain-text email body.
    dry_run : bool
        If True, print what would be sent without actually sending.
    """
    graded_dir = Path(graded_dir)
    exams_dir = Path(exams_dir)

    # ------------------------------------------------------------------
    # 1. Build student lookup from gradebook(s): match_key -> email
    # ------------------------------------------------------------------
    id_to_email: Dict[str, str] = {}
    for gb_path in gradebook_paths:
        gb_path = Path(gb_path)
        if not gb_path.exists():
            raise FileNotFoundError(f"Gradebook not found: {gb_path}")
        gb_df = pd.read_csv(gb_path, dtype=str, index_col=False).fillna("")
        unnamed_cols = [c for c in gb_df.columns if c.startswith("Unnamed")]
        if unnamed_cols:
            gb_df = gb_df.drop(columns=unnamed_cols)
        if "Student ID" not in gb_df.columns:
            raise ValueError(f"Gradebook {gb_path} missing 'Student ID' column")
        if email_column not in gb_df.columns:
            raise ValueError(
                f"Gradebook {gb_path} missing '{email_column}' column. "
                f"Columns found: {gb_df.columns.tolist()}"
            )
        for _, row in gb_df.iterrows():
            sid = str(row["Student ID"]).strip()
            email_val = str(row[email_column]).strip()
            if sid and email_val:
                mk = _normalize_id(sid)
                addr = email_val if not email_suffix else email_val + email_suffix
                id_to_email[mk] = addr

    logger.info(f"Loaded {len(id_to_email)} student email(s) from gradebook(s)")

    # ------------------------------------------------------------------
    # 2. Discover graded answer sheet PDFs
    # ------------------------------------------------------------------
    graded_pattern = re.compile(r"^graded_(.+?)_([0-9a-fA-F]+)\.pdf$")
    graded_files: Dict[str, tuple[Path, str]] = {}  # match_key -> (path, version)
    for pdf in sorted(graded_dir.glob("graded_*.pdf")):
        m = graded_pattern.match(pdf.name)
        if m:
            sid_raw, version = m.group(1), m.group(2)
            mk = _normalize_id(sid_raw)
            graded_files[mk] = (pdf, version)

    logger.info(f"Found {len(graded_files)} graded answer sheet(s) in {graded_dir}")

    # ------------------------------------------------------------------
    # 3. Discover exam version PDFs
    # ------------------------------------------------------------------
    exam_versions: Dict[str, Path] = {}
    for pdf in exams_dir.glob("exam-*.pdf"):
        # exam-01234567.pdf -> version "01234567"
        version = pdf.stem.removeprefix("exam-")
        exam_versions[version] = pdf

    logger.info(f"Found {len(exam_versions)} exam version PDF(s) in {exams_dir}")

    # ------------------------------------------------------------------
    # 4. Match and send
    # ------------------------------------------------------------------
    if not dry_run:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")

    sent = 0
    skipped_no_email = []
    skipped_no_exam = []
    failed = []

    for mk, (graded_path, version) in sorted(graded_files.items()):
        email = id_to_email.get(mk)
        if not email:
            skipped_no_email.append(mk)
            logger.warning(f"Student {mk}: no email found in gradebook — skipped")
            continue

        exam_path = exam_versions.get(version)
        if not exam_path:
            skipped_no_exam.append((mk, version))
            logger.warning(f"Student {mk}: exam version {version} not found — skipped")
            continue

        if dry_run:
            print(f"  [DRY RUN] To: {email}")
            print(f"            Graded sheet: {graded_path.name}")
            print(f"            Exam version: {exam_path.name}")
            print()
            sent += 1
            continue

        try:
            mail = outlook.CreateItem(0)
            mail.To = email
            mail.Subject = subject
            mail.Body = body
            mail.Attachments.Add(str(graded_path.resolve()))
            mail.Attachments.Add(str(exam_path.resolve()))
            mail.Send()
            sent += 1
            sys.stderr.write(f"\rSent {sent}...")
            sys.stderr.flush()
            logger.info(f"Sent to {email} ({graded_path.name}, {exam_path.name})")
        except Exception as e:
            failed.append((mk, email, str(e)))
            logger.error(f"Failed to send to {email}: {e}")

    sys.stderr.write("\r" + " " * 40 + "\r")
    sys.stderr.flush()

    # ------------------------------------------------------------------
    # 5. Summary
    # ------------------------------------------------------------------
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Return summary:")
    print(f"  {prefix}Emails sent: {sent}")
    if skipped_no_email:
        print(f"  Skipped (no email in gradebook): {len(skipped_no_email)}")
    if skipped_no_exam:
        print(f"  Skipped (exam PDF not found): {len(skipped_no_exam)}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for mk, email, err in failed:
            print(f"    {mk} ({email}): {err}")
