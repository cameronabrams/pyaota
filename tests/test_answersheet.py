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
