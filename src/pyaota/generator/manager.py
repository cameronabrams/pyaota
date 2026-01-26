"""
CLI dispatch functions for pyaota exam generator and grader.
"""

import csv
import random
import yaml
import os
import shutil
import numpy as np
import cv2
from pathlib import Path
from dataclasses import asdict
from pdf2image import convert_from_path

from .yaml2tex import render_question, tex_escape
from .questionset import QuestionSet
from .document import Document, ExamDocument
from .answersheet import AnswerSheetGenerator, LayoutConfig
from ..grader.answersheetreader import AnswerSheetReader
from ..grader.autograder import Autograder
from ..latex.content import DEFAULT_ANSWER_SHEET_INSTRUCTIONS, DEFAULT_EXAM_INSTRUCTIONS, QUESTION_BANK_DUMP_INSTRUCTIONS
from ..latex.latexcompiler import LatexCompiler
from ..util.collectors import on_rm_error

import logging
logger = logging.getLogger(__name__)

# def build_answer_key_tex(
#     selected_questions: list[dict],
#     head: str = HEADMATTER,
#     tail: str = TAILMATTER,
#     version_label: str = "00000000",
# ) -> str:
#     """
#     Build a complete LaTeX answer key document with a simple
#     two-column list of answers:
#         Q1  a     Q2  c
#         Q3  d     Q4  b
#     etc.
#     """
#     # Collect (question_number, correct_letter)
#     answers = [
#         (i + 1, str(q.get("correct", "")).strip())
#         for i, q in enumerate(selected_questions)
#     ]

#     parts: list[str] = []
#     parts.append(head.rstrip())
#     parts.append("")
#     parts.append(r"\section*{Answer Key}")
#     parts.append("")

#     parts.append(r"\begin{center}")
#     # left: (Q, Ans)   right: (Q, Ans)
#     parts.append(r"\begin{tabular}{r c @{\hspace{1.5cm}} r c}")
#     parts.append(r"\textbf{Q} & \textbf{Ans} & \textbf{Q} & \textbf{Ans} \\")
#     parts.append(r"\hline")

#     # Emit rows with up to two Q/A pairs
#     for i in range(0, len(answers), 2):
#         (q1, a1) = answers[i]
#         if i + 1 < len(answers):
#             (q2, a2) = answers[i + 1]
#         else:
#             q2, a2 = "", ""
#         parts.append(rf"{q1} & {a1} & {q2} & {a2} \\")
#     parts.append(r"\end{tabular}")
#     parts.append(r"\end{center}")
#     parts.append("")

#     parts.append(tail.lstrip())
#     return "\n".join(parts)

def write_version_keys_csv(
    records: list[tuple[str, list[str]]],
    output_path: str = "exam_version_keys.csv",
) -> None:
    """
    Write a CSV with one row per exam version.

    records: list of (version_label, [ans1, ans2, ...])

    CSV columns:
      version_label, Q1, Q2, Q3, ...
    """
    if not records:
        return

    # Determine max length in case different versions had different #questions
    max_q = max(len(ans_list) for _, ans_list in records)
    fieldnames = ["version_label"] + [f"Q{i}" for i in range(1, max_q + 1)]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for version_label, ans_list in records:
            row = {"version_label": version_label}
            for i, ans in enumerate(ans_list, start=1):
                row[f"Q{i}"] = ans
            writer.writerow(row)

def write_answer_sheet_layout_yaml(
    layout_config: LayoutConfig,
    output_path: str = "answer_sheet_layout.yaml",
) -> None:
    """
    Write the answer sheet layout configuration to a YAML file.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(asdict(layout_config), f, default_flow_style=False)

def read_answer_sheet_layout_yaml(
    input_path: str,
) -> LayoutConfig:
    """
    Read the answer sheet layout configuration from a YAML file.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = yaml.full_load(f)
        if 'id_echo_textbox' in data:
            data['id_echo_textbox'] = TextBoxConfig(**data['id_echo_textbox'])
        if 'score_textbox' in data:
            data['score_textbox'] = TextBoxConfig(**data['score_textbox'])
    config = LayoutConfig(**data)
    return config

def compile_dump_subcommand(args):
    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'pdflatex': 'pdflatex',
            'build-dir': args.output_dir,
        },
        'job-name': 'banks_full_dump',
    })
    yaml_paths = args.question_banks
    output_dir = Path(args.output_dir)

    question_set = QuestionSet(question_banks=yaml_paths)

    version_label = "0"
    bankfiles = tex_escape(", ".join(yaml_paths))
    logger.debug(f"Preparing full compile of all questions in {bankfiles}")

    selected_questions = question_set.raw_question_list

    exam_doc_specs = dict(
        institution=args.institution,
        course=args.course,
        term=args.term,
        examname="Banks: " + bankfiles,
        version=version_label,
        instructions=QUESTION_BANK_DUMP_INSTRUCTIONS,
        question_renderer=lambda q: render_question(q, show_id=True, highlight_correct=True),
        question_list=selected_questions,
        endmessage="End of Exam\n\\clearpage",)

    exam_doc = ExamDocument(document_specs=exam_doc_specs)
    latex_compiler.build_document(exam_doc, cleanup=True)


def make_exams_subcommand(args):
    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'pdflatex': 'pdflatex',
            'build-dir': args.output_dir,
        },
        'job-name': 'exam',
    })
    yaml_paths = args.question_banks
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        logger.warning(f"Output directory {output_dir} already exists.")
        if args.overwrite:
            logger.info(f"Overwriting contents of {output_dir}.")
            shutil.rmtree(output_dir, onerror=on_rm_error)

    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    default_seed = 0
    seed = args.seed if args.seed is not None else default_seed
    id_generator = random.Random(seed)
    # Generate until you have enough unique ones
    hex_strings = []
    seen = set()
    while len(hex_strings) < args.num_exams:
        hex_id = f"{id_generator.randint(0, 0xFFFFFFFF):08x}"
        if hex_id not in seen:
            seen.add(hex_id)
            hex_strings.append(hex_id)
    hex_strings.sort()
    logger.info(f'Using master seed {seed} for RNG that generates exam version numbers.')
    logger.info(f'Generating {args.num_exams} exam versions with version numbers: {", ".join(hex_strings)}')
    question_set = QuestionSet(question_banks=yaml_paths)
    version_answer_records: list[tuple[str, list[str]]] = []
    answer_sheet_layout = LayoutConfig(
        bubble_field_num_cols = args.num_cols,
        num_questions = args.num_questions,
    )
    write_answer_sheet_layout_yaml(answer_sheet_layout, output_path=output_dir/"answer_sheet_layout.yaml")
    # generate the list of version numbers as 8-byte hexadecimal strings

    for version_label in hex_strings:
        # generate an 8-digit version as an integer and then zero-pad to string
        version_rng_seed = int(version_label, 16)

        selected_questions = question_set.get_random_selection(num_questions=args.num_questions,
                                                               topics_order=args.topics,
                                                               seed=version_rng_seed, 
                                                               shuffle=args.shuffle_questions, 
                                                               shuffle_choices=args.shuffle_choices)
        logger.debug(f'Generated exam version {version_label} with {len(selected_questions)} questions.')
        answers = [str(q.get("correct", "")).strip() for q in selected_questions]
        version_answer_records.append((version_label, answers))
        answersheet_generator = AnswerSheetGenerator(
            layout_config=answer_sheet_layout,
            question_list=selected_questions,
        )

        answersheet_tex = answersheet_generator.generate_tex(version_label=version_label,)

        exam_doc_specs = dict(
            institution=args.institution,
            course=args.course,
            term=args.term,
            examname=args.exam_name,
            version=version_label,
            instructions=DEFAULT_EXAM_INSTRUCTIONS,
            question_renderer=render_question,
            question_list=selected_questions,
            answersheet_tex=answersheet_tex,
            endmessage="End of Exam\n\\clearpage",)

        exam_doc = ExamDocument(document_specs=exam_doc_specs)
        latex_compiler.build_document(exam_doc, cleanup=args.cleanup)

    write_version_keys_csv(version_answer_records, output_path=output_dir/"exam_version_keys.csv")
    write_answer_sheet_layout_yaml(answer_sheet_layout, output_path=output_dir/"answer_sheet_layout.yaml")

def make_answersheet_subcommand(args):
    layout_config = LayoutConfig(
        bubble_field_num_cols = args.num_cols,
        num_questions = args.num_questions,
        student_id_num_digits=args.student_id_num_digits
    )
    # let's gnerate a mock question list that only contains the type
    # of question, and let's make half of them 'mcq' and half 'tf'
    mock_question_list = []
    num_mcq = args.num_questions // 2
    num_tf = args.num_questions - num_mcq
    for i in range(num_mcq):
        mock_question_list.append({'type': 'mcq'})
    for i in range(num_tf):
        mock_question_list.append({'type': 'tf'})
    random.shuffle(mock_question_list)
    answersheet_generator = AnswerSheetGenerator(
        layout_config=layout_config,
        question_list=mock_question_list,
    )
    answersheet_tex = answersheet_generator.generate_tex(version_label="SAMPLE",)

    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'pdflatex': 'pdflatex',
            'build-dir': args.output_dir,
        },
        'job-name': args.output_pdf,
    })
    exam_doc_specs = dict(
        institution="",
        course="",
        term="",
        examname="Sample Answer Sheet",
        version="SAMPLE",
        instructions="",
        question_renderer=render_question,
        question_list=[],
        answersheet_tex=answersheet_tex,
        endmessage="End of Document\n\\clearpage",)

    exam_doc = ExamDocument(document_specs=exam_doc_specs)
    latex_compiler.build_document(exam_doc, cleanup=False)

def tune_answersheetreader_subcommand(args):
    pdf = args.sample_pdf
    # convert PDF to image
    images = convert_from_path(pdf, dpi=300, fmt='png')
    if not images:
        logger.error(f"Could not convert PDF {pdf} to image.")
        return

    img = np.array(images[-1])
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    answersheetreader = AnswerSheetReader(img=img, layout_config=LayoutConfig(
        bubble_field_num_cols=args.num_cols,
        num_questions = args.num_questions))

    answersheetreader._find_indicials()
    answersheetreader._warp_to_canonical()
    answersheetreader._read_student_id()
    # answersheetreader.diagnose_qr_detection()
    answersheetreader._read_qr()
    answersheetreader._read_bubblefield()
    img = answersheetreader._diagnostic_overlay()
    output_path = Path(args.output_image)
    cv2.imwrite(str(output_path), img)
    logger.info(f"Wrote diagnostic overlay image to {output_path}")

def autograde_subcommand(args):
    pdf = args.input_pdf
    keyfiles = args.keyfiles
    answersheetlayoutyaml = args.answersheet_layout_yaml
    output_dir_path = Path(args.output_dir)
    debug_output_dir_path = Path(args.debug_output_dir)
    gradesheet_output_csv_path = Path(args.gradesheet_output_csv)
    question_tally_csv_path = Path(args.question_tally_output_csv)
    if not output_dir_path.exists():
        output_dir_path.mkdir(parents=True, exist_ok=True)
    if not debug_output_dir_path.exists():
        debug_output_dir_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Autograding PDF {pdf} using keyfiles {keyfiles} and layout {answersheetlayoutyaml}")
    layout_config: LayoutConfig = read_answer_sheet_layout_yaml(answersheetlayoutyaml)

    autograder = Autograder(layout_config=layout_config)
    for keyfile in keyfiles:
        autograder.load_version_keys_csv(keyfile)
        
    autograder.grade_pdf(pdf, output_dir_path=output_dir_path, 
        debug_output_dir_path=debug_output_dir_path, 
        gradesheet_output_csv_path=gradesheet_output_csv_path,
        question_tally_csv_path=question_tally_csv_path)