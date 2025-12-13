from __future__ import annotations

import argparse
import sys

from pyaota.generator.make_exams import make_exams

def main(argv: list[str] | None = None) -> int:
    """
    Entry point for the pyaota command-line interface.
    """
    parser = argparse.ArgumentParser(
        prog="pyaota",
        description="pyaota: exam generation and grading toolkit",
    )

    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="command",
        metavar="<command>",
        required=True,
    )

    # ---- generate -------------------------------------------------
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate one or more exams",
    )
    gen_parser.add_argument(
        "-od",
        "--output-dir",
        required=True,
        help="Output directory",
    )
    gen_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible generation",
    )
    gen_parser.add_argument(
        "-n",
        "--num-exams",
        type=int,
        default=1,
        help="Number of exams to generate",
    )
    gen_parser.add_argument(
        "-t",
        "--topics",
        nargs="+",
        default=[],
        help="Topics to include in the exam",
    )
    gen_parser.add_argument(
        "-qpt",
        "--questions-per-topic",
        type=int,
        default=5,
        help="Number of questions per topic",
    )
    gen_parser.add_argument(
        "-q",
        "--question-banks",
        nargs="+",
        default=[],
        help="Paths to question banks (YAML/JSON)",
    )
    gen_parser.add_argument(
        "-f",
        "--full-dump",
        action="store_true",
        help="Generate all questions without selection",
    )
    gen_parser.set_defaults(func=_cmd_generate)

    # # ---- ocr ------------------------------------------------------
    # ocr_parser = subparsers.add_parser(
    #     "ocr",
    #     help="Run OCR on an exam scan",
    # )
    # ocr_parser.add_argument(
    #     "image",
    #     help="Path to scanned exam image",
    # )
    # ocr_parser.add_argument(
    #     "--model",
    #     default=None,
    #     help="Path to OCR model (overrides default)",
    # )
    # ocr_parser.add_argument(
    #     "--debug",
    #     action="store_true",
    #     help="Save intermediate OCR artifacts",
    # )
    # ocr_parser.set_defaults(func=_cmd_ocr)

    # ---- grade ----------------------------------------------------
    grade_parser = subparsers.add_parser(
        "grade",
        help="Grade exams",
    )
    grade_parser.add_argument(
        "pdf",
        help="PDF containing one or more answer sheets (scantron-like)",
    )
    grade_parser.add_argument(
        "keyfile",
        help="CSV file containing answer keys for each exam version",
    )
    grade_parser.add_argument(
        "-o",
        "--output",
        required=True,
        default="grades.csv",
        help="Output grade report",
    )
    grade_parser.set_defaults(func=_cmd_grade)

    # ---- dispatch ------------------------------------------------
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except Exception as exc:
        parser.error(str(exc))
        return 1


# =================================================================
# Subcommand implementations (stubs for now)
# =================================================================

def _cmd_generate(args: argparse.Namespace) -> int:
    make_exams(args)
    return 0


# def _cmd_ocr(args: argparse.Namespace) -> int:
#     print("[ocr]")
#     print(f"  image = {args.image}")
#     print(f"  model = {args.model}")
#     print(f"  debug = {args.debug}")
#     # TODO: hook into pyaota.ocr pipeline
#     return 0


def _cmd_grade(args: argparse.Namespace) -> int:
    print("[grade]")
    print(f"  ocr_results = {args.ocr_results}")
    print(f"  rubric      = {args.rubric}")
    print(f"  output      = {args.output}")
    # TODO: hook into pyaota.grading
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
