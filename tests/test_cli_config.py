import os
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pyaota import cli


def _run(argv):
    seen = {}
    with patch.object(cli, 'make_exams_subcommand', side_effect=lambda a: seen.setdefault('args', a) and 0):
        cli.main(argv)
    return seen['args']


class TestConfig(TestCase):

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = TemporaryDirectory()
        os.chdir(self._tmp.name)  # main() writes its diagnostic log to the cwd

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_saved_config_reproduces_run_and_cli_wins(self):
        _run(['--save-config', 'c.yaml', 'build', '-q', 'bank.yaml', '-nq', '30', '-n', '3',
              '-en', 'Final', '--no-shuffle-choices', '-od', 'out'])
        args = _run(['--config', 'c.yaml', 'build', '-nq', '10', '--shuffle-choices'])
        self.assertEqual(args.num_questions, 10)        # given on the command line
        self.assertTrue(args.shuffle_choices)           # explicit flag beats config
        self.assertEqual(args.num_exams, 3)             # non-None default: came from config
        self.assertEqual(args.exam_name, 'Final')
        self.assertEqual(args.output_dir, 'out')

    def test_explicit_dests(self):
        parser = cli.ap.ArgumentParser()
        parser.add_argument('-nq', '--num-questions', type=int)
        parser.add_argument('--flag', action=cli.ap.BooleanOptionalAction, default=False)
        self.assertEqual(cli.explicit_dests([parser], ['--num-questions=5', '--no-flag']), {'num_questions', 'flag'})
        self.assertEqual(cli.explicit_dests([parser], ['-nq', '5']), {'num_questions'})
