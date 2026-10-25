import copy
from unittest import TestCase

from pyaota.generator.questionset import QuestionSet, normalize_question
from pyaota.generator.yaml2tex import render_tf

JS_BANK = 'examples/question_banks/simple_javascript.yaml'


def _mcq(**fields):
    q = {'id': 1, 'type': 'mcq', 'choices': [{'key': k, 'text': t} for k, t in zip('abcd', 'WXYZ')]}
    q.update(fields)
    return q


class TestNormalizeQuestion(TestCase):

    def test_mcq_answer_field_and_case(self):
        q = _mcq(answer='C')
        self.assertEqual(normalize_question(q), [])
        self.assertEqual(q['correct'], 'c')

    def test_correct_wins_over_answer(self):
        q = _mcq(correct='a', answer='d')
        normalize_question(q)
        self.assertEqual(q['correct'], 'a')

    def test_tf_strings(self):
        for raw, expected in [(True, True), ('False', False), ('f', False), ('T', True), ('no', False)]:
            q = {'id': 1, 'type': 'tf', 'answer': raw}
            self.assertEqual(normalize_question(q), [])
            self.assertIs(q['correct'], expected, raw)

    def test_problems_reported(self):
        self.assertTrue(normalize_question(_mcq()))
        self.assertTrue(normalize_question(_mcq(correct='e')))
        self.assertTrue(normalize_question({'id': 1, 'type': 'tf', 'answer': 'maybe'}))
        self.assertTrue(normalize_question({'id': 1, 'type': 'essay', 'correct': 'x'}))

    def test_render_tf_string_false(self):
        self.assertIn('{F}', render_tf({'id': 1, 'type': 'tf', 'stem': [], 'answer': 'False'}))


class TestChoiceShuffling(TestCase):

    def test_keys_follow_shuffled_choices_for_answer_field_banks(self):
        # simple_javascript.yaml gives MCQ answers as `answer:`; before
        # normalization, shuffled choices left most keys pointing at the wrong choice
        qs = QuestionSet([JS_BANK])
        truth = {q['id']: next(c['text'] for c in q['choices'] if c['key'] == q['correct'])
                 for q in qs.raw_question_list if q['type'] == 'mcq'}
        sel = qs.get_random_selection(num_questions=15, topics_order=None, seed=7, shuffle=True, shuffle_choices=True)
        for q in sel:
            if q['type'] == 'mcq':
                self.assertEqual(next(c['text'] for c in q['choices'] if c['key'] == q['correct']), truth[q['id']])

    def test_selection_does_not_mutate_bank(self):
        qs = QuestionSet([JS_BANK])
        before = copy.deepcopy(qs.raw_question_list)
        first = qs.get_random_selection(num_questions=15, topics_order=None, seed=8, shuffle=True, shuffle_choices=True)
        qs.get_random_selection(num_questions=15, topics_order=None, seed=9, shuffle=True, shuffle_choices=True)
        again = qs.get_random_selection(num_questions=15, topics_order=None, seed=8, shuffle=True, shuffle_choices=True)
        self.assertEqual(qs.raw_question_list, before)
        self.assertEqual(first, again)
