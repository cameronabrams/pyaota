"""
Build a real exam, fill its answer sheets programmatically, and grade them.

Needs xelatex and poppler (pdftoppm) on PATH; skipped otherwise.
"""
import csv
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

import cv2
import numpy as np
from PIL import Image

from pyaota import cli
from pyaota.generator.answersheet import LayoutConfig, _ureg
from pyaota.generator.layout_config_serialization import load_layout_config
from pyaota.grader.answersheetreader import AnswerSheetReader

BANK = Path(__file__).resolve().parents[1] / 'examples' / 'question_banks' / 'simple_history.yaml'
HAVE_TOOLS = shutil.which('xelatex') is not None and shutil.which('pdftoppm') is not None


def _px(q):
    return int(q.to('pxl').magnitude)


def _id_center(layout, col, digit):
    # same geometry as AnswerSheetReader._read_student_id_bubbles
    ul_x, ul_y = _px(layout.student_id_digit_boxes_ul[0]), _px(layout.student_id_digit_boxes_ul[1])
    bw, bh = _px(layout.student_id_digit_boxes_box_size[0]), _px(layout.student_id_digit_boxes_box_size[1])
    gap, vgap = _px(layout.student_id_digit_boxes_horiz_gap), _px(layout.bubble_column_vert_gap)
    r = _px(layout.bubble_radius)
    return (ul_x + int(round(col * (gap + bw))) + int(np.round(0.5 * bw)),
            ul_y + bh + vgap + r + (2 * r + vgap) * digit)


def _fill_sheet(build, layout, keys, version, id_marks, wrong=(), blank=(), rotate=0.0, noise=0):
    from pdf2image import convert_from_path
    page = np.array(convert_from_path(str(build / f'exam-{version}.pdf'), dpi=300)[-1].convert('RGB'))
    img = cv2.cvtColor(page, cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    r = int(_px(layout.bubble_radius) * 0.8)
    for col, digits in enumerate(id_marks):
        for d in digits:
            cv2.circle(img, _id_center(layout, col, d), r, (40, 40, 40), -1)
    with TemporaryDirectory() as dbg:
        centers = AnswerSheetReader(img, layout_config=layout, debug_output_dir=Path(dbg))._locate_bubbles()
    for q, a in enumerate(keys[version], start=1):
        if q in blank:
            continue
        tf = a in ('True', 'False')
        i = {'True': 0, 'False': 1}[a] if tf else 'abcd'.index(a)
        if q in wrong:
            i = (i + 1) % (2 if tf else 4)
        cv2.circle(img, centers[(q, 'abcd'[i])], r, (40, 40, 40), -1)
    if rotate:
        img = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), rotate, 1.0), (w, h),
                             borderValue=(255, 255, 255))
    if noise:
        img = np.clip(img.astype(int) + np.random.default_rng(0).normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


@skipUnless(HAVE_TOOLS, 'needs xelatex and pdftoppm on PATH')
class TestBuildAndGrade(TestCase):

    def test_build_fill_grade(self):
        cwd = os.getcwd()
        with TemporaryDirectory() as d:
            os.chdir(d)
            try:
                self._run(Path(d))
            finally:
                os.chdir(cwd)

    def _run(self, d):
        self.assertEqual(cli.main(['build', '--encode-answers-in-qr', '-q', str(BANK), '-n', '2', '-nq', '20',
                                   '-nc', '4', '-sc', '-sq', '-en', 'Quiz 1', '-od', 'build']) or 0, 0)
        build = d / 'build'
        layout = load_layout_config(build / 'answersheet_layout.json', LayoutConfig, _ureg)
        keys = {r['version_label']: [r[f'Q{i}'] for i in range(1, 21)]
                for r in csv.DictReader(open(build / 'exam_version_keys.csv'))}
        v1, v2 = list(keys)
        ids = lambda s: [[int(c)] for c in s]
        pages = [
            _fill_sheet(build, layout, keys, v1, ids('10214573')),
            _fill_sheet(build, layout, keys, v2, ids('00512345'), wrong={1, 2, 3, 4, 5}, rotate=0.4, noise=8),
            _fill_sheet(build, layout, keys, v1, ids('222') + [[2, 7]] + ids('2222')),
            _fill_sheet(build, layout, keys, v2, ids('33333333'), blank={20}),
        ]
        pages[0].save(d / 'scans.pdf', save_all=True, append_images=pages[1:], resolution=300.0)
        gradebook = d / 'gradebook.csv'
        with open(gradebook, 'w', newline='') as f:
            csv.writer(f).writerows([['Student ID', 'score'], ['10214573', ''], ['512345', ''],
                                     ['22222222', '88.0'], ['33333333', '']])

        # no -k: answers come from the encrypted QR codes
        cli.main(['grade', '-i', 'scans.pdf', '-alj', 'build/answersheet_layout.json', '-od', 'graded',
                  '-gb', str(gradebook), '-qt', 'graded/tally.csv'])

        scores = {r['Student ID']: r['score'] for r in csv.DictReader(open(gradebook))}
        self.assertEqual(scores, {'10214573': '100.0', '512345': '75.0',   # leading-zero ID matched
                                  '22222222': '88.0',                       # ambiguous ID: kept
                                  '33333333': '95.0'})                      # blank Q20
        self.assertIn('multiple marks', (d / 'graded' / 'failed_pages_report.txt').read_text())
        self.assertEqual(len(list(csv.DictReader(open(d / 'graded' / 'tally.csv')))), 3)
