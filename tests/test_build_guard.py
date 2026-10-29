"""
Checks build makes before it touches the output directory.  None of these
reach LaTeX, so they run without xelatex.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pyaota import cli

BANK = Path(__file__).resolve().parents[1] / 'examples' / 'question_banks' / 'simple_history.yaml'


class _Reached(Exception):
    pass


class TestBuildGuard(TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = TemporaryDirectory()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def _old_build(self, key):
        Path('build').mkdir()
        layout = Path('build/answersheet_layout.json')
        layout.write_text(json.dumps({'qr_answer_key': key}))
        return layout

    def test_keyed_build_is_not_replaced(self):
        layout = self._old_build('ab' * 32)
        for extra in ([], ['-ow']):
            self.assertEqual(cli.main(['build', '-q', str(BANK), '-nq', '3', '-od', 'build'] + extra), 1)
            self.assertTrue(layout.exists())

    def test_force_replaces_a_keyed_build(self):
        layout = self._old_build('ab' * 32)
        # stop the build just after the guard: reaching the bank load shows it let the build through
        with patch('pyaota.generator.manager.QuestionSet', side_effect=_Reached):
            with self.assertRaises(_Reached):
                cli.main(['build', '-q', str(BANK), '-nq', '3', '-od', 'build', '-ow', '--force'])
        self.assertFalse(layout.exists())

    def test_missing_bank_leaves_the_output_directory(self):
        layout = self._old_build(None)
        self.assertEqual(cli.main(['build', '-q', 'nope.yaml', '-nq', '3', '-od', 'build', '-ow']), 1)
        self.assertTrue(layout.exists())
