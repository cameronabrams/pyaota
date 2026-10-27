from unittest import TestCase

from pyaota.generator.document import ExamDocument
from pyaota.generator.yaml2tex import _choices_columns, render_question


def _code_choices(*texts):
    return [{'key': k, 'type': 'code', 'text': t} for k, t in zip('abcd', texts)]


class TestChoiceColumns(TestCase):

    def test_short_choices_go_on_one_row(self):
        self.assertEqual(_choices_columns(_code_choices('-9', '9', '-6', '6')), 4)

    def test_medium_choices_use_two_columns(self):
        self.assertEqual(_choices_columns(_code_choices('3.5 1', '3 1', 'x = n % 10 + 1', 'error')), 2)
        self.assertEqual(_choices_columns([{'key': 'a', 'text': 'Nothing; it raises an error'}]), 2)

    def test_long_choices_use_one_column(self):
        self.assertEqual(_choices_columns(_code_choices('print(len(s), s[1], s[-1]) ok')), 1)

    def test_half_width_question_halves_the_room(self):
        choices = _code_choices('3 1', '3 0', '3.5 1', '3.5 0.5')
        self.assertEqual(_choices_columns(choices), 4)
        self.assertEqual(_choices_columns(choices, line_width=0.5), 2)
        self.assertEqual(_choices_columns([{'key': 'a', 'text': 'Nothing; it raises an error'}],
                                          line_width=0.5), 1)


class TestQuestionColumns(TestCase):
    QUESTION = {'id': 1, 'type': 'mcq', 'correct': 'a', 'stem': [{'type': 'text', 'text': 'Q?'}],
                'choices': [{'key': 'a', 'text': 'yes'}, {'key': 'b', 'text': 'no'}]}

    def test_two_columns_wrap_only_the_questions(self):
        doc = ExamDocument({'question_list': [self.QUESTION], 'questioncolumns': 2,
                            'endmessage': 'End of Exam', 'answersheet_tex': '% sheet'})
        body = doc.content
        start, end = body.index(r'\begin{multicols}{2}'), body.index(r'\end{multicols}', body.index(r'\begin{mcq}'))
        self.assertLess(start, body.index(r'\begin{mcq}'))
        self.assertLess(end, body.index('End of Exam'))
        self.assertLess(end, body.index('% sheet'))

    def test_one_column_is_unchanged(self):
        doc = ExamDocument({'question_list': [self.QUESTION]})
        self.assertNotIn(r'\begin{multicols}{', doc.content.split(r'\begin{document}')[1].split(r'\begin{mcq}')[0])

    def test_renderer_passes_width_to_choices(self):
        q = dict(self.QUESTION, choices=[{'key': k, 'type': 'code', 'text': '3.5 0.5'} for k in 'abcd'])
        self.assertIn(r'\begin{choices}[4]', render_question(q))
        self.assertIn(r'\begin{choices}[2]', render_question(q, line_width=0.5))
