from unittest import TestCase
from pyaota.generator.answersheet import AnswerSheetGenerator, LayoutConfig


def _old_slots(num_questions, num_cols, blocksize=5):
    # the pre-0.5.1 placement, which only worked when the blocks divided evenly into the columns
    total_blocks = -(-num_questions // blocksize)
    slots = []
    for col in range(num_cols):
        for block in range(total_blocks // num_cols):
            for row in range(blocksize):
                if len(slots) < num_questions:
                    slots.append((col, block, row))
    return slots


class TestBubbleFieldSlots(TestCase):

    def test_every_question_gets_a_distinct_slot_within_num_cols(self):
        for nq in range(1, 101):
            for nc in (1, 2, 3, 4):
                slots = LayoutConfig(num_questions=nq, bubble_field_num_cols=nc).bubble_field_slots()
                self.assertEqual(len(slots), nq)
                self.assertEqual(len(set(slots)), nq)
                self.assertTrue(all(col < nc for col, _, _ in slots), (nq, nc))

    def test_layouts_that_already_worked_are_unchanged(self):
        # any sheet already printed must still be read at the same bubble positions
        for nq, nc in [(30, 3), (45, 3), (60, 3), (20, 2), (40, 4), (12, 1)]:
            slots = LayoutConfig(num_questions=nq, bubble_field_num_cols=nc).bubble_field_slots()
            self.assertEqual(slots, _old_slots(nq, nc), (nq, nc))

    def test_default_answersheet_generates(self):
        # make-answersheet defaults: 50 questions, 3 columns
        config = LayoutConfig(num_questions=50, bubble_field_num_cols=3)
        tex = AnswerSheetGenerator(config, question_list=[{'type': 'mcq'}] * 50)._place_bubblefield()
        self.assertIn(r'\textbf{50.}', tex)

    def test_few_questions_and_no_question_list(self):
        tex = AnswerSheetGenerator(LayoutConfig(num_questions=10, bubble_field_num_cols=3))._place_bubblefield()
        self.assertIn(r'\textbf{10.}', tex)


class TestSinglePageLayout(TestCase):

    def test_strip_sits_between_the_questions_and_the_corner_marks(self):
        c = LayoutConfig(num_questions=10, single_page=True)
        inch = lambda q: q.to('inch').magnitude
        strip_top = inch(c.strip_top)
        self.assertLess(strip_top, inch(c.name_blank_ul[1]))
        self.assertLess(strip_top, inch(c.qr_ul[1]))
        self.assertLess(strip_top, inch(c.student_id_digit_boxes_ul[1]))
        # last question row and last ID-digit row end above the bottom corner marks' line
        id_bottom = (inch(c.student_id_digit_boxes_ul[1]) + inch(c.student_id_digit_boxes_box_size[1])
                     + inch(c.bubble_column_vert_gap) + 10 * inch(2 * c.bubble_radius + c.bubble_column_vert_gap))
        sw_y = inch(c.indicial_sw_location[1])
        self.assertLess(id_bottom, sw_y - 0.2)
        # the bubbles end inside the right-hand boundary
        east = inch(c.canonical_width + c.indicial_east_offset) - 0.25
        right_edge = (inch(c.bubble_field_ul[0]) + inch(c.intrablock_numbering_gap)
                      + 3 * inch(c.intrablock_choice_gap + 2 * c.bubble_radius) + inch(c.bubble_radius))
        self.assertLess(right_edge, east)

    def test_question_rows_line_up_with_id_digit_rows(self):
        c = LayoutConfig(num_questions=10, single_page=True)
        self.assertEqual(c.bubble_field_slots(), [(0, b, r) for b in range(2) for r in range(5)])
        first_digit_y = (c.student_id_digit_boxes_ul[1] + c.student_id_digit_boxes_box_size[1]
                         + c.bubble_column_vert_gap + c.bubble_radius)
        self.assertAlmostEqual(c.bubble_field_ul[1].to('pxl').magnitude, first_digit_y.to('pxl').magnitude)
        self.assertEqual(c.intrablock_row_gap, 2 * c.bubble_radius + c.bubble_column_vert_gap)

    def test_too_many_questions(self):
        with self.assertRaises(ValueError):
            LayoutConfig(num_questions=11, single_page=True)

    def test_strip_tex_goes_first_and_keeps_its_font(self):
        tex = AnswerSheetGenerator(LayoutConfig(num_questions=3, single_page=True),
                                   [{'type': 'mcq'}] * 3).generate_tex(version_label='v', qr_image_filename='q.png')
        self.assertIn(r'\noindent\makebox[0pt][l]{%', tex)
        self.assertTrue(tex.rstrip().endswith('}%'))
        self.assertNotIn(r'\clearpage', tex)
