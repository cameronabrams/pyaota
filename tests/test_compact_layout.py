from unittest import TestCase

from pyaota.generator.document import ExamDocument
from pyaota.generator.yaml2tex import TEXTWIDTH_PT, _choices_columns, length_to_pt, render_question

HALF = (TEXTWIDTH_PT - 24) / 2   # one of two question columns, 2em gap at 12pt


def _code_choices(*texts):
    return [{'key': k, 'type': 'code', 'text': t} for k, t in zip('abcd', texts)]


class TestChoiceColumns(TestCase):

    def test_short_choices_go_on_one_row(self):
        self.assertEqual(_choices_columns(_code_choices('-9', '9', '-6', '6')), 4)

    def test_medium_choices_use_two_columns(self):
        self.assertEqual(_choices_columns(_code_choices('3.5 1', '3 1', 'x = n % 10 + 1', 'error')), 2)
        self.assertEqual(_choices_columns([{'key': 'a', 'text': 'Nothing; it raises an error'}]), 2)

    def test_long_choices_use_one_column(self):
        self.assertEqual(_choices_columns(_code_choices('print(len(s), s[1], s[-1], s[2:4])')), 1)

    def test_half_width_question_halves_the_room(self):
        choices = _code_choices('3 1', '3 0', '3.5 1', '3.5 0.5')
        self.assertEqual(_choices_columns(choices), 4)
        self.assertEqual(_choices_columns(choices, column_width_pt=HALF), 2)
        self.assertEqual(_choices_columns([{'key': 'a', 'text': 'Nothing; it raises an error'}],
                                          column_width_pt=HALF), 1)


    def test_fit_allows_for_font_size_and_gap(self):
        # 4 mono characters fit four across at 11pt with a 2em gap; 5 overflow (measured)
        half_11 = (TEXTWIDTH_PT - length_to_pt('2em', 11)) / 2
        self.assertEqual(_choices_columns(_code_choices('2000', '8000', '1000', '60'),
                                          column_width_pt=half_11, font_pt=11), 4)
        self.assertEqual(_choices_columns(_code_choices('20000'), column_width_pt=half_11, font_pt=11), 2)
        # a wider gap leaves less room
        half_12_3em = (TEXTWIDTH_PT - length_to_pt('3em', 12)) / 2
        self.assertEqual(_choices_columns(_code_choices('2000'), column_width_pt=half_12_3em), 2)


class TestLengths(TestCase):

    def test_units(self):
        self.assertAlmostEqual(length_to_pt('2em', 11), 22)
        self.assertAlmostEqual(length_to_pt('1in'), 72.27)
        self.assertAlmostEqual(length_to_pt('2.54cm'), 72.27)
        self.assertAlmostEqual(length_to_pt('18pt'), 18)
        with self.assertRaises(ValueError):
            length_to_pt('2 furlongs')


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

    def test_gap_and_rule_apply_to_question_columns_only(self):
        doc = ExamDocument({'question_list': [self.QUESTION], 'questioncolumns': 2,
                            'questioncolumnsep': '3em', 'questioncolumnrule': True})
        self.assertIn(r'\setlength{\columnsep}{3em}\setlength{\columnseprule}{0.4pt}', doc.content)
        self.assertIn(r'\end{multicols}\endgroup', doc.content)
        # the choices environment resets both for its own columns
        self.assertIn(r'\setlength{\columnsep}{10pt}\setlength{\columnseprule}{0pt}', doc.content)

    def test_question_boxes_are_opt_in(self):
        self.assertNotIn(r'\questionboxestrue', ExamDocument({'question_list': [self.QUESTION]}).content)
        doc = ExamDocument({'question_list': [self.QUESTION], 'questionboxes': True})
        self.assertIn('\n\\questionboxestrue\n', doc.content)
        self.assertNotIn('<<<', doc.content)

    def test_one_column_is_unchanged(self):
        doc = ExamDocument({'question_list': [self.QUESTION]})
        self.assertNotIn(r'\begin{multicols}{', doc.content.split(r'\begin{document}')[1].split(r'\begin{mcq}')[0])

    def test_renderer_passes_width_to_choices(self):
        q = dict(self.QUESTION, choices=[{'key': k, 'type': 'code', 'text': '3.5 0.5'} for k in 'abcd'])
        self.assertIn(r'\begin{choices}[4]', render_question(q))
        self.assertIn(r'\begin{choices}[2]', render_question(q, column_width_pt=HALF))


class TestTrueFalseLabel(TestCase):

    def test_label_has_its_own_line(self):
        q = {'id': 1, 'type': 'tf', 'correct': True, 'stem': [{'type': 'text', 'text': '[1] is a list.'}]}
        self.assertIn(r'\textbf{True\,(T)\,/\,False\,(F)}\newline [1] is a list.', render_question(q))
        key_t = render_question(q, highlight_correct=True)
        key_f = render_question(dict(q, correct=False), highlight_correct=True)
        self.assertIn(r'\correctlabel{T}\,True\,/\,False\,(F)\newline [1]', key_t)
        self.assertIn(r'True\,(T)\,/\,\correctlabel{F}\,False\newline [1]', key_f)
