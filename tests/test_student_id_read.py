from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import cv2
import numpy as np

from pyaota.generator.answersheet import LayoutConfig
from pyaota.grader.answersheetreader import AnswerSheetReader


def _id_bubble_center(config, col, digit):
    # mirrors the geometry in AnswerSheetReader._read_student_id_bubbles
    px = lambda q: int(q.to('pxl').magnitude)
    ul_x, ul_y = px(config.student_id_digit_boxes_ul[0]), px(config.student_id_digit_boxes_ul[1])
    box_w, box_h = px(config.student_id_digit_boxes_box_size[0]), px(config.student_id_digit_boxes_box_size[1])
    gap, vgap, r = px(config.student_id_digit_boxes_horiz_gap), px(config.bubble_column_vert_gap), px(config.bubble_radius)
    x = ul_x + int(round(col * (gap + box_w))) + int(np.round(0.5 * box_w))
    y = ul_y + box_h + vgap + r + (2 * r + vgap) * digit
    return x, y, r


def _read_id(marks):
    """marks: {column: [(digit, size as a fraction of the bubble radius), ...]};
    unlisted columns get one full mark on the digit equal to the column index."""
    config = LayoutConfig(num_questions=10)
    h, w = int(config.canonical_height.to('pxl').magnitude), int(config.canonical_width.to('pxl').magnitude)
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    for col in range(config.student_id_num_digits):
        for digit, size in marks.get(col, [(col, 0.9)]):
            x, y, r = _id_bubble_center(config, col, digit)
            cv2.circle(img, (x, y), int(r * size), (0, 0, 0), -1)
    with TemporaryDirectory() as d:
        reader = AnswerSheetReader(img, layout_config=config, debug_output_dir=Path(d))
        reader.working_image = img
        reader._read_student_id_bubbles()
        return reader.results['student_id_bubbles']


class TestStudentIdMarks(TestCase):

    def test_clean_marks(self):
        self.assertEqual(_read_id({}), "01234567")

    def test_erasure_resolves_to_clearly_darker_mark(self):
        # a full mark on 3 and an incompletely erased mark on 9 (about a quarter
        # of the bubble, still above the fill threshold)
        self.assertEqual(_read_id({3: [(3, 0.9), (9, 0.55)]}), "01234567")

    def test_two_equal_marks_fail_instead_of_guessing(self):
        with self.assertRaises(RuntimeError) as ctx:
            _read_id({3: [(3, 0.9), (8, 0.9)]})
        self.assertIn("multiple marks", str(ctx.exception))
