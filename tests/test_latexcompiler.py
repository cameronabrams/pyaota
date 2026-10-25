import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pyaota.generator.document import Document
from pyaota.latex.latexcompiler import LatexBuildError, LatexCompiler, latex_log_errors


class TestLatexErrors(TestCase):

    def test_log_errors_are_extracted(self):
        with TemporaryDirectory() as d:
            log = Path(d) / "x.log"
            log.write_text(
                "This is XeTeX\n"
                "./exam.tex:12: Illegal parameter number in definition of \\foo.\n"
                "! LaTeX Error: Option clash for package xcolor.\n"
                "Overfull \\hbox (1.0pt too wide) in paragraph\n"
            )
            errors = latex_log_errors(log)
            self.assertEqual(len(errors), 2)
            self.assertIn("Option clash", errors[1])

    def test_failed_engine_raises(self):
        # `false` stands in for an engine that exits 1 and writes no PDF
        cwd = os.getcwd()
        with TemporaryDirectory() as d:
            os.chdir(d)
            try:
                compiler = LatexCompiler({'paths': {'latex-engine': 'false', 'build-dir': '.'}, 'job-name': 'doc'})
                with self.assertRaises(LatexBuildError):
                    compiler.build_document(Document("\\documentclass{article}"))
            finally:
                os.chdir(cwd)
