from unittest import TestCase

import pandas as pd

from pyaota.grader.autograder import apply_grades_to_gradebook, resolve_grade_records

SCORE = "Exam Score"
FIELDS = ["version_label", "num_questions", "num_correct", SCORE, "status"]


def _rec(page, sid, version="v1", score="80.0", status="ok"):
    return {"page_index": page, "Student ID": sid, "_match_key": sid.lstrip("0") or "0",
            "version_label": version, "num_questions": "10", "num_correct": "8" if score else "",
            SCORE: score, "status": status}


def _gradebook(rows):
    gb = pd.DataFrame(rows, dtype=str).fillna("")
    gb["_match_key"] = gb["Student ID"].str.lstrip("0")
    return gb


class TestResolveGradeRecords(TestCase):

    def test_identical_duplicates_collapse(self):
        chosen, conflicts = resolve_grade_records(pd.DataFrame([_rec(1, "123"), _rec(2, "123")]), SCORE)
        self.assertEqual(conflicts, {})
        self.assertEqual(list(chosen.index), ["123"])

    def test_conflicting_duplicates_are_dropped_and_reported(self):
        df = pd.DataFrame([_rec(1, "123", score="80.0"), _rec(2, "0123", score="40.0"), _rec(3, "456")])
        chosen, conflicts = resolve_grade_records(df, SCORE)
        self.assertEqual(set(conflicts), {"123"})
        self.assertIn("page 1", conflicts["123"])
        self.assertEqual(list(chosen.index), ["456"])

    def test_graded_page_wins_over_failed_page(self):
        df = pd.DataFrame([_rec(1, "123"), _rec(2, "123", score="", status="unknown_version")])
        chosen, _ = resolve_grade_records(df, SCORE)
        self.assertEqual(chosen.loc["123", SCORE], "80.0")
        self.assertTrue(chosen.loc["123", "_graded"])


class TestApplyGrades(TestCase):

    def test_failed_page_does_not_blank_existing_score(self):
        gb = _gradebook([{"Student ID": "123", SCORE: "95.0", "status": "ok"},
                         {"Student ID": "456", SCORE: "", "status": ""}])
        new, _ = resolve_grade_records(pd.DataFrame([
            _rec(1, "123", score="", status="unknown_version"),
            _rec(2, "456", score="", status="unknown_version"),
        ]), SCORE)
        in_new, updated = apply_grades_to_gradebook(gb, new, FIELDS, SCORE, SCORE)
        self.assertEqual(gb.loc[0, SCORE], "95.0")
        self.assertEqual(gb.loc[0, "status"], "ok")
        self.assertEqual(gb.loc[1, "status"], "unknown_version")
        self.assertEqual(list(in_new), [True, True])
        self.assertEqual(list(updated), [False, True])

    def test_new_grade_overwrites_and_matches_leading_zeros(self):
        gb = _gradebook([{"Student ID": "123", SCORE: "50.0"}])
        new, _ = resolve_grade_records(pd.DataFrame([_rec(1, "00123", score="90.0")]), SCORE)
        apply_grades_to_gradebook(gb, new, FIELDS, SCORE, SCORE)
        self.assertEqual(gb.loc[0, SCORE], "90.0")
