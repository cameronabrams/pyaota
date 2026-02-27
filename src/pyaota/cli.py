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
    autograde_subcommand,
    return_subcommand,
)
from .generator.wordexport2rawyaml import convert_subcommand
from .util.bundle import bundle_subcommand
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
        'bundle': dict(
            func = bundle_subcommand,
            help = 'bundle PDFs from a directory into uniform-sized bundles',
        ),
        'return': dict(
            func = return_subcommand,
            help = 'email graded answer sheets and exam PDFs to students via Outlook',
        ),
        'convert': dict(
            func = convert_subcommand,
            help = 'convert a ZyBooks-exported zip (QTI XML or Word) into a YAML question bank',
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
        default=1,
        help="Number of exams to generate (default: 1)",
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
        default=3,
        help="Number of columns in the answer sheet (default: 3)",
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
    command_parsers["build"].add_argument(
        "-if",
        "--instructions-file",
        type=str,
        default=None,
        help="Path to file containing custom exam instructions in LaTeX format (if not provided, default instructions will be used)",
    )
    command_parsers["build"].add_argument(
        "--font-size",
        type=str,
        default="12pt",
        choices=["10pt", "11pt", "12pt"],
        help="Font size for the generated PDF (default: 12pt)",
    )
    command_parsers["build"].add_argument(
        "--question-spacing",
        type=str,
        default="24pt",
        metavar="LENGTH",
        help="Vertical space between questions as a LaTeX length (default: 24pt)",
    )
    command_parsers["build"].add_argument(
        "--bubble-font-size",
        type=float,
        default=8.0,
        metavar="PT",
        help="Font size in points for text inside answer bubbles (default: 8.0)",
    )
    command_parsers["build"].add_argument(
        "--odd-page-answersheet",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Force the answer sheet to start on an odd-numbered page (for double-sided printing)",
    )
    command_parsers["build"].add_argument(
        "--rasterize",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Rasterize output PDFs at 300 DPI for improved printer compatibility",
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
    command_parsers["compile-dump"].add_argument(
        "-if",
        "--instructions-file",
        type=str,
        default=None,
        help="Path to file containing custom instructions in LaTeX format (if not provided, default instructions will be used)",
    )
    command_parsers["compile-dump"].add_argument(
        "--font-size",
        type=str,
        default="12pt",
        choices=["10pt", "11pt", "12pt"],
        help="Font size for the generated PDF (default: 12pt)",
    )
    command_parsers["compile-dump"].add_argument(
        "--question-spacing",
        type=str,
        default="24pt",
        metavar="LENGTH",
        help="Vertical space between questions as a LaTeX length (default: 24pt)",
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
        "-fp",
        "--failed-pages-dir",
        default=None,
        help="Directory for failed/unreadable page PDFs and report (default: same as --output-dir)",
    )
    command_parsers["grade"].add_argument(
        "-gb",
        "--gradebooks",
        nargs="+",
        help="One or more gradebook CSV files (must contain a 'Student ID' column)",
    )
    command_parsers["grade"].add_argument(
        "-sc",
        "--score-column",
        default="score",
        help="Column name in the gradebook(s) for the score (default: 'score')",
    )
    command_parsers["grade"].add_argument(
        "-nc",
        "--num-counted",
        type=int,
        default=None,
        help="Number of questions counted toward the score (default: all questions). Must be <= total questions.",
    )
    command_parsers["grade"].add_argument(
        "-qt",
        "--question-tally",
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
    command_parsers["make-answersheet"].add_argument(
        "--bubble-font-size",
        type=float,
        default=8.0,
        metavar="PT",
        help="Font size in points for text inside answer bubbles (default: 8.0)",
    )
    command_parsers["make-answersheet"].add_argument(
        "--odd-page-answersheet",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Force the answer sheet to start on an odd-numbered page (for double-sided printing)",
    )
    command_parsers["make-answersheet"].add_argument(
        "--rasterize",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Rasterize output PDF at 300 DPI for improved printer compatibility",
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

    command_parsers["bundle"].add_argument(
        "-i",
        "--input-dir",
        required=True,
        help="Directory containing PDF files to bundle",
    )
    command_parsers["bundle"].add_argument(
        "-od",
        "--output-dir",
        default="bundles",
        help="Output directory for bundle PDFs (default: bundles/)",
    )
    command_parsers["bundle"].add_argument(
        "-n",
        "--bundle-size",
        type=int,
        required=True,
        help="Number of documents per bundle",
    )
    command_parsers["bundle"].add_argument(
        "--co-bundle",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Also generate a co-bundle PDF of the last page from each document",
    )

    command_parsers["return"].add_argument(
        "-gb",
        "--gradebooks",
        nargs="+",
        required=True,
        help="Gradebook CSV file(s) with 'Student ID' and email columns",
    )
    command_parsers["return"].add_argument(
        "-gd",
        "--graded-dir",
        required=True,
        help="Directory containing graded answer sheet PDFs (graded_<id>_<version>.pdf)",
    )
    command_parsers["return"].add_argument(
        "-ed",
        "--exams-dir",
        required=True,
        help="Directory containing exam version PDFs (exam-<version>.pdf)",
    )
    command_parsers["return"].add_argument(
        "--email-column",
        default="Username",
        help="Gradebook column containing email or email prefix (default: 'Username')",
    )
    command_parsers["return"].add_argument(
        "--email-suffix",
        default="@drexel.edu",
        help="Suffix appended to email column value (default: '@drexel.edu'). "
             "Set to '' if the column already has full addresses.",
    )
    command_parsers["return"].add_argument(
        "--subject",
        default="Your graded exam",
        help="Email subject line (default: 'Your graded exam')",
    )
    command_parsers["return"].add_argument(
        "--body",
        default=(
            "Attached are your graded answer sheet and a copy of the exam you took.\n"
            "If you have questions about your grade, please contact your instructor."
        ),
        help="Plain-text email body",
    )
    command_parsers["return"].add_argument(
        "--dry-run",
        default=False,
        action=ap.BooleanOptionalAction,
        help="Preview what would be sent without actually emailing",
    )
    command_parsers["return"].add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
        help="Number of seconds to sleep between sending emails (default: 0.5 seconds)",
    )
    command_parsers["convert"].add_argument(
        "-i",
        "--input-zip",
        required=True,
        help="Path to a ZyBooks-exported zip file containing Word documents",
    )
    command_parsers["convert"].add_argument(
        "-o",
        "--output-yaml",
        required=True,
        help="Path to the output YAML question bank file",
    )

    # ---- dispatch ------------------------------------------------
    args = parser.parse_args(argv)

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
    logger.debug(f'Command line: {" ".join(sys.argv)}')

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
