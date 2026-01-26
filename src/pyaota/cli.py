"""
Command-line interface for pyaota: build and grade multiple-choice exams.
"""

from __future__ import annotations

import argparse as ap
import sys, os, shutil
import yaml

from .generator.manager import (
    make_exams_subcommand, 
    make_answersheet_subcommand,
    compile_dump_subcommand, 
    tune_answersheetreader_subcommand, 
    autograde_subcommand
)
from .util.text import banner, oxford

import logging
logger = logging.getLogger(__name__)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

def setup_logging(args):    
    loglevel_numeric = getattr(logging, args.logging_level.upper())
    if args.log:
        if os.path.exists(args.log):
            shutil.copyfile(args.log, args.log+'.bak')
        logging.basicConfig(filename=args.log,
                            filemode='w',
                            format='%(asctime)s %(name)s %(message)s',
                            level=loglevel_numeric
        )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s> %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

def save_args(args, filepath):
    """
    Save argparse namespace including subcommand to YAML
    
    Parameters
    ----------
    args : argparse.Namespace
        The argparse namespace to save.
    filepath : str
        The path to the YAML file to save the args to.
    """
    args_dict = vars(args).copy()
    args_dict.pop('func', None)
    args_dict.pop('save_config', None)
    args_dict.pop('config', None)
    with open(filepath, 'w') as f:
        yaml.dump(args_dict, f, default_flow_style=False)

def load_args_from_yaml(filepath):
    """
    Load args from YAML
    
    Parameters
    ----------
    filepath : str
        The path to the YAML file to load the args from.
    """
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)

def main(argv: list[str] | None = None) -> int:
    """
    Entry point for the pyaota command-line interface.
    """
    subcommands = {
        'build': dict(
            func = make_exams_subcommand,
            help = 'build documents',
            ),
        'compile-dump': dict(
            func = compile_dump_subcommand,
            help = 'compile full dump of questions into a document',
        ),
        'grade': dict(
            func = autograde_subcommand,
            help = 'grade exams from scanned answer sheets',
        ),
        'make-answersheet': dict(
            func = make_answersheet_subcommand,
            help = 'make a blank answer sheet PDF',
        ),
        'tune-answersheetreader': dict(
            func = tune_answersheetreader_subcommand,
            help = 'tune the answer sheet reader parameters',
        ),
    }
    parser = ap.ArgumentParser(
        prog='pyaota',
        description='pyaota: build and grade multiple-choice/true-false exams',
        epilog='(c) 2025-2026 Cameron F. Abrams <cfa22@drexel.edu>'
    )
    parser.add_argument('--config', type=str, help='Load config from YAML')
    parser.add_argument('--save-config', type=str, help='Save full config to YAML')

    parser.add_argument(
        '-b',
        '--banner',
        default=False,
        action=ap.BooleanOptionalAction,
        help='toggle banner message'
    )
    parser.add_argument(
        '--logging-level',
        type=str,
        default='debug',
        choices=[None, 'info', 'debug', 'warning'],
        help='Logging level for messages written to diagnostic log'
    )
    parser.add_argument(
        '-l',
        '--log',
        type=str,
        default='pyaota-diagnostics.log',
        help='File to which diagnostic log messages are written'
    )
    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="subcommand",
        metavar="<subcommand>",
        required=True,
    )
    command_parsers={}
    for k, specs in subcommands.items():
        command_parsers[k] = subparsers.add_parser(
            k,
            help=specs['help'],
            formatter_class=ap.RawDescriptionHelpFormatter
        )
        # command_parsers[k].set_defaults(func=specs['func'])
    
    command_parsers["build"].add_argument(
        "-od",
        "--output-dir",
        help="Output directory",
    )
    command_parsers["build"].add_argument(
        "--institution",
        type=str,
        help="Institution name",
        default="Drexel University"
    )
    command_parsers["build"].add_argument(
        "--course",
        type=str,
        help="Course name",
        default="ENGR-131"
    )
    command_parsers["build"].add_argument(
        "--term",
        type=str,
        help="Term name",
        default="202526"
    )
    command_parsers["build"].add_argument(
        "--cleanup",
        action=ap.BooleanOptionalAction,
        help="Cleanup intermediate files after LaTeX compilation",
    )
    command_parsers["build"].add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducible generation",
    )
    command_parsers["build"].add_argument(
        "-n",
        "--num-exams",
        type=int,
        help="Number of exams to generate",
    )
    command_parsers["build"].add_argument(
        "-t",
        "--topics",
        nargs="+",
        help="Topics to include in the exam (questions will be drawn from these topics and distributed evenly)",
    )
    command_parsers["build"].add_argument(
        "-nq",
        "--num-questions",
        type=int,
        help="Number of questions on each exam",
    )
    command_parsers["build"].add_argument(
        "-q",
        "--question-banks",
        nargs="+",
        help="Paths to question banks (YAML/JSON)",
    )
    command_parsers["build"].add_argument(
        "-nc",
        "--num-cols",
        type=int,
        help="Number of columns in the answer sheet",
    )
    command_parsers["build"].add_argument(
        "-sq",
        "--shuffle-questions",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Shuffle question order on each exam",
    )
    command_parsers["build"].add_argument(
        "-sc",
        "--shuffle-choices",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Shuffle answer choice order on each exam",
    )
    command_parsers["build"].add_argument(
        "-en",
        "--exam-name",
        type=str,
        default="Exam",
        help="Name of the exam (used in header)",
    )
    command_parsers["build"].add_argument(
        "-ow",
        "--overwrite",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Overwrite output directory if it exists",
    )
    command_parsers["compile-dump"].add_argument(
        "-od",
        "--output-dir",
        default=".",
        help="Output directory",
    )
    command_parsers["compile-dump"].add_argument(
        "-q",
        "--question-banks",
        nargs="+",
        default=[],
        help="Paths to question banks (YAML/JSON)",
    )
    command_parsers["compile-dump"].add_argument(
        "--institution",
        type=str,
        help="Institution name",
        default="Drexel University"
    )
    command_parsers["compile-dump"].add_argument(
        "--course",
        type=str,
        help="Course name",
        default="ENGR-131"
    )
    command_parsers["compile-dump"].add_argument(
        "--term",
        type=str,
        help="Term name",
        default="202526"
    )

    command_parsers["grade"].add_argument(
        "-i",
        "--input-pdf",
        help="PDF containing one or more answer sheets (scantron-like)",
    )
    command_parsers["grade"].add_argument(
        # can handle multiple files
        "-k",
        "--keyfiles",
        nargs="+",
        help="CSV file(s) containing answer keys for each exam version",
    )
    command_parsers["grade"].add_argument(
        "-alj",
        "--answersheet-layout-json",
        help="JSON file specifying the answer sheet layout configuration",
    )
    command_parsers["grade"].add_argument(
        "-od",
        "--output-dir",
        default=".",
        help="Path to output directory for graded results",
    )
    command_parsers["grade"].add_argument(
        "--debug-output-dir",
        default = "debug-autograder",
        help="Path to output directory for debug images",
    )
    command_parsers["grade"].add_argument(
        "-og",
        "--gradesheet-output-csv",
        default="graded_results.csv",
        help="Path to output CSV file summarizing results",
    )
    command_parsers["grade"].add_argument(
        "-oq",
        "--question-tally-output-csv",
        default="question_tally.csv",
        help="Path to output CSV file summarizing question tallies",
    )

    command_parsers["make-answersheet"].add_argument(
        "-o",
        "--output-pdf",
        default="answersheet",
        help="Path to output answer sheet PDF",
    )
    command_parsers["make-answersheet"].add_argument(
        "-nc",
        "--num-cols",
        type=int,
        default=3,
        help="Number of columns in the answer sheet",
    )
    command_parsers["make-answersheet"].add_argument(
        "-nq",
        "--num-questions",
        type=int,
        default=50,
        help="Number of questions on the answer sheet",
    )
    command_parsers["make-answersheet"].add_argument(
        "-od",
        "--output-dir",
        default=".",
        help="Output directory",
    )
    command_parsers["make-answersheet"].add_argument(
        "-idl",
        "--student-id-num-digits",
        type=int,
        default=8,
        help="Number of digits in the student ID field",
    )

    command_parsers["tune-answersheetreader"].add_argument(
        "-i",
        "--sample-pdf",
        help="Sample PDF for tuning results",
    )
    command_parsers["tune-answersheetreader"].add_argument(
        "-nc",
        "--num-cols",
        type=int,
        default=3,
        help="Number of columns in the answer sheet",
    )
    command_parsers["tune-answersheetreader"].add_argument(
        "-nq",
        "--num-questions",
        type=int,
        default=50,
        help="Number of questions on the answer sheet",
    )
    command_parsers["tune-answersheetreader"].add_argument(
        "-o",
        "--output-image",
        default="answersheetreader_tuning_overlay.png",
        help="Path to output image file showing tuning overlay",
    )

    # ---- dispatch ------------------------------------------------
    args = parser.parse_args()

    # If config specified, load and override
    if args.config:
        config_dict = load_args_from_yaml(args.config)
        logger.debug(f'Loaded config from {args.config}')
        logger.debug(f'Config contents: {config_dict}')
        # Only override if not set on command line
        for key, value in config_dict.items():
            if not hasattr(args, key) or getattr(args, key) is None or isinstance(getattr(args, key), bool):
                setattr(args, key, value)
        logger.debug(f'Args after loading config: {args}')

    # Save if requested
    if args.save_config:
        save_args(args, args.save_config)

    setup_logging(args)

    if args.banner:
        banner(print)
    func = subcommands.get(args.subcommand, {}).get('func', None)
    if func:
        return func(args)
    else:
        logger.debug(f'{args}')
        my_list = oxford(list(subcommands.keys()))
        print(f'No subcommand found. Expected one of {my_list}')
        return 1
    logger.info('Thanks for using pyaota!')

if __name__ == "__main__":
    raise SystemExit(main())
