import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pyaota.grader.autograder import write_question_tally


def _result(sid, version, answers, key):
    return {"student_id": sid, "version_label": version, "answers_detected": answers, "answer_key": key}


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestQuestionTally(TestCase):

    def test_first_run_writes_file(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "tally.csv"
            write_question_tally(path, [_result("123", "v1", {1: "a", 2: "c"}, ["a", "b"])])
            rows = _read(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Q1"], "a")
            self.assertEqual(rows[0]["Q2"], "c")

    def test_second_run_merges_and_keeps_existing(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "tally.csv"
            write_question_tally(path, [_result("123", "v1", {1: "a"}, ["a"])])
            write_question_tally(path, [
                _result("123", "v1", {1: "d"}, ["a"]),
                _result("456", "v2", {1: "b", 2: "b", 3: "a"}, ["b", "b", "a"]),
            ])
            rows = {r["student_id"]: r for r in _read(path)}
            self.assertEqual(set(rows), {"123", "456"})
            self.assertEqual(rows["123"]["Q1"], "a")
            self.assertEqual(rows["456"]["Q3"], "a")

    def test_ungraded_pages_are_skipped(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "tally.csv"
            write_question_tally(path, [_result(None, None, {}, None)])
            self.assertFalse(path.exists())
