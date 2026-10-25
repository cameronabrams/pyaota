from unittest import TestCase

from pyaota.generator.document import ExamDocument
from pyaota.generator.yaml2tex import render_code_block, render_text, tex_escape


class TestTexEscape(TestCase):

    def test_superscripts_are_not_double_escaped(self):
        self.assertEqual(tex_escape("m²"), r"m\textsuperscript{2}")
        self.assertEqual(render_text("``v²`` in m/s³"), r"\texttt{v\textsuperscript{2}} in m/s\textsuperscript{3}")

    def test_verbatim_code_keeps_unicode_superscript(self):
        _, tex = render_code_block("x = 2²\ny = 3", force_env=True)
        self.assertIn("2²", tex)

    def test_header_fields_are_escaped(self):
        doc = ExamDocument({'institution': 'R&D U.', 'course': 'PHYS_101', 'term': '50% Fall',
                            'examname': 'Exam #2', 'version': 'abc'})
        for escaped in (r'R\&D U.', r'PHYS\_101', r'50\% Fall', r'Exam \#2'):
            self.assertIn(escaped, doc.content)
        self.assertNotIn('Exam #2', doc.content)
