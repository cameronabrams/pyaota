"""
CLI dispatch functions for pyaota exam generator and grader.
"""

import csv
import random
import yaml
import os
import shutil
import pickle
import numpy as np
import cv2
from pathlib import Path
from dataclasses import asdict
from pdf2image import convert_from_path

import re as _re
from .yaml2tex import render_question, tex_escape
from .questionset import QuestionSet
from .document import Document, ExamDocument
from .answersheet import AnswerSheetGenerator, LayoutConfig, _ureg
from .layout_config_serialization import save_layout_config, load_layout_config
from ..grader.answersheetreader import AnswerSheetReader
from ..grader.autograder import Autograder
from ..grader.returner import return_graded_exams
from ..latex.content import DEFAULT_EXAM_INSTRUCTIONS, DEFAULT_PAGESTYLES_TEMPLATE, QUESTION_BANK_DUMP_INSTRUCTIONS
from ..latex.latexcompiler import LatexCompiler
from ..util.collectors import on_rm_error
from ..util.qrcrypto import generate_key, encrypt_answers, generate_qr_png

import logging
logger = logging.getLogger(__name__)

def rasterize_pdf(pdf_path: Path, dpi: int = 300) -> None:
    """Replace a PDF with a rasterized version for improved printer compatibility.

    Converts each page to a raster image at *dpi* and re-encodes as a PDF.
    This eliminates complex vector/TikZ paths that can confuse some printer RIPs.
    """
    images = convert_from_path(str(pdf_path), dpi=dpi)
    if not images:
        raise ValueError(f"rasterize_pdf: could not convert {pdf_path}")
    images[0].save(str(pdf_path), save_all=True, append_images=images[1:])
    logger.info(f"Rasterized {pdf_path} at {dpi} DPI")

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

def build_answer_key_table_latex(
    records: list[tuple[str, list[str]]],
    institution: str = "",
    course: str = "",
    term: str = "",
    exam_name: str = "",
    max_versions_per_table: int = 10,
) -> str:
    """
    Build LaTeX code for answer key table(s).

    Creates a longtable with:
    - Columns: Question number + one column per exam version
    - Rows: One row per question

    If there are more versions than max_versions_per_table, splits into multiple tables.

    Args:
        records: list of (version_label, [ans1, ans2, ...])
        institution: Institution name for header
        course: Course name for header
        term: Term for header
        exam_name: Exam name for header
        max_versions_per_table: Maximum number of versions per table before splitting

    Returns:
        Complete LaTeX document as string
    """
    if not records:
        return ""

    # Determine number of questions
    num_questions = max(len(ans_list) for _, ans_list in records)
    num_versions = len(records)

    # Build header
    parts = []
    parts.append(r"\documentclass[10pt, landscape]{article}")
    parts.append(r"\usepackage[landscape, margin=0.5in]{geometry}")
    parts.append(r"\usepackage{longtable}")
    parts.append(r"\usepackage{array}")
    parts.append(r"\usepackage{xcolor}")
    parts.append(r"\usepackage[table]{xcolor}")
    parts.append(r"\usepackage{booktabs}")
    parts.append(r"\usepackage{fancyhdr}")
    parts.append(r"\usepackage[scaled]{helvet}")
    parts.append(r"\renewcommand\familydefault{\sfdefault}")

    parts.append(r"")

    # Page style
    parts.append(r"\pagestyle{fancy}")
    parts.append(r"\fancyhf{}")
    if institution or course or term:
        header_parts = [p for p in [institution, course, term] if p]
        parts.append(rf"\lhead{{{' -- '.join(header_parts)}}}")
    if exam_name:
        parts.append(rf"\rhead{{{exam_name} -- Answer Keys}}")
    else:
        parts.append(r"\rhead{Answer Keys}")
    parts.append(r"\cfoot{\thepage}")
    parts.append(r"")

    # Alternate row coloring
    parts.append(r"\definecolor{lightgray}{gray}{0.9}")
    parts.append(r"\newcommand{\rowcol}{\rowcolor{lightgray}}")
    parts.append(r"")

    parts.append(r"\begin{document}")
    parts.append(r"")

    # Split versions into chunks if needed
    version_chunks = []
    for i in range(0, num_versions, max_versions_per_table):
        chunk = records[i:i + max_versions_per_table]
        version_chunks.append(chunk)

    # Create a table for each chunk
    for chunk_idx, chunk in enumerate(version_chunks):
        if len(version_chunks) > 1:
            parts.append(rf"\section*{{Answer Keys (Versions {chunk_idx * max_versions_per_table + 1}--{chunk_idx * max_versions_per_table + len(chunk)})}}")
        else:
            parts.append(r"\section*{Answer Keys for All Exam Versions}")
        parts.append(r"")

        # Build column specification: question column + version columns
        num_cols_in_chunk = len(chunk)
        col_spec = "|c|" + "c|" * num_cols_in_chunk

        # Start longtable
        parts.append(rf"\begin{{longtable}}{{{col_spec}}}")
        parts.append(r"\hline")

        # Header row
        header_cells = [r"\textbf{Q}"]
        for version_label, _ in chunk:
            # Truncate version label if too long
            display_label = version_label[:8] if len(version_label) > 8 else version_label
            header_cells.append(rf"\textbf{{{display_label}}}")
        parts.append(" & ".join(header_cells) + r" \\")
        parts.append(r"\hline")
        parts.append(r"\endfirsthead")
        parts.append(r"")

        # Header for continuation pages
        parts.append(r"\multicolumn{" + str(num_cols_in_chunk + 1) + r"}{c}{\textit{(continued from previous page)}} \\")
        parts.append(r"\hline")
        parts.append(" & ".join(header_cells) + r" \\")
        parts.append(r"\hline")
        parts.append(r"\endhead")
        parts.append(r"")

        # Footer for continuation
        parts.append(r"\hline")
        parts.append(r"\multicolumn{" + str(num_cols_in_chunk + 1) + r"}{r}{\textit{(continued on next page)}} \\")
        parts.append(r"\endfoot")
        parts.append(r"")

        # Final footer
        parts.append(r"\hline")
        parts.append(r"\endlastfoot")
        parts.append(r"")

        # Data rows - one per question
        for q_num in range(1, num_questions + 1):
            # Alternate row colors every 5 rows for easier reading
            if (q_num - 1) % 5 == 0 and q_num > 1:
                row_cells = [rf"\rowcol {q_num}"]
            else:
                row_cells = [str(q_num)]

            # Get answer for this question from each version in chunk
            for version_label, ans_list in chunk:
                if q_num <= len(ans_list):
                    answer = ans_list[q_num - 1]
                    row_cells.append(answer)
                else:
                    row_cells.append("--")

            parts.append(" & ".join(row_cells) + r" \\")

        parts.append(r"\hline")
        parts.append(r"\end{longtable}")
        parts.append(r"")

        # Add page break between chunks (except after last chunk)
        if chunk_idx < len(version_chunks) - 1:
            parts.append(r"\clearpage")
            parts.append(r"")

    parts.append(r"\end{document}")

    return "\n".join(parts)

def write_version_keys_pdf(
    records: list[tuple[str, list[str]]],
    output_dir: Path,
    institution: str = "",
    course: str = "",
    term: str = "",
    exam_name: str = "",
    max_versions_per_table: int = 10,
) -> None:
    """
    Generate a PDF with nicely formatted answer keys table.

    Args:
        records: list of (version_label, [ans1, ans2, ...])
        output_dir: Directory where PDF should be created
        institution: Institution name for header
        course: Course name for header
        term: Term for header
        exam_name: Exam name for header
        max_versions_per_table: Maximum number of versions per table before splitting
    """
    if not records:
        logger.warning("No answer key records to generate PDF from.")
        return

    logger.info(f"Generating answer keys PDF with {len(records)} exam versions...")

    # Build the LaTeX content
    latex_content = build_answer_key_table_latex(
        records=records,
        institution=institution,
        course=course,
        term=term,
        exam_name=exam_name,
        max_versions_per_table=max_versions_per_table,
    )

    # Create a temporary document object to hold the LaTeX
    from .document import Document

    # Write LaTeX to a temporary file and compile
    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'latex-engine': 'xelatex',
            'build-dir': str(output_dir),
        },
        'job-name': 'answer_keys',
    })

    doc = Document(content=latex_content)
    doc.version = "AnswerKeys"
    latex_compiler.build_document(doc, cleanup=True)

    output_pdf = output_dir / "answer_keys.pdf"
    logger.info(f"Answer keys PDF generated: {output_pdf}")

_PSEUDOCODE_STYLE = r"""\lstdefinestyle{pseudocode}{
    basicstyle=\ttfamily,
    keywordstyle=\bfseries,
    keywords={if,then,else,elseif,while,for,return,end,endif,endwhile,endfor,print},
    columns=fullflexible,
    frame=single,
    mathescape=true,
    escapechar=§
}"""

def _build_listings_extra_preamble(style_file: str) -> tuple[str, str]:
    """Parse *style_file* for the first \\lstdefinestyle name and build an
    extra-preamble block that loads listings, the pseudocode style, the user
    style, and defines \\inl.

    Returns (style_name, preamble_str).
    """
    with open(style_file, 'r', encoding='utf-8') as f:
        style_content = f.read()
    m = _re.search(r'\\lstdefinestyle\{(\w+)\}', style_content)
    if not m:
        raise ValueError(
            f"--use-listings-from: no \\lstdefinestyle{{...}} found in {style_file}"
        )
    style_name = m.group(1)
    preamble = (
        "\\usepackage{listings}\n"
        + _PSEUDOCODE_STYLE + "\n"
        + style_content + "\n"
        + f"\\newcommand{{\\inl}}[1]{{\\lstinline[style={style_name},breaklines=false]|#1|}}\n"
    )
    return style_name, preamble


def compile_dump_subcommand(args):
    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'latex-engine': 'xelatex',
            'build-dir': args.output_dir,
        },
        'job-name': 'banks_full_dump',
    })
    yaml_paths = args.question_banks
    output_dir = Path(args.output_dir)

    question_set = QuestionSet(question_banks=yaml_paths)
    question_set.copy_images_to(Path.cwd())

    version_label = "0"
    bankfiles = tex_escape(", ".join(yaml_paths))
    logger.debug(f"Preparing full compile of all questions in {bankfiles}")

    selected_questions = question_set.raw_question_list

    # Load custom instructions if provided, otherwise use default
    if args.instructions_file is not None:
        logger.info(f'Loading custom dump instructions from {args.instructions_file}')
        with open(args.instructions_file, 'r', encoding='utf-8') as f:
            dump_instructions = f.read()
    else:
        dump_instructions = QUESTION_BANK_DUMP_INSTRUCTIONS

    pagestyles_file = getattr(args, 'pagestyles_file', None)
    if pagestyles_file is not None:
        logger.info(f'Loading custom page styles from {pagestyles_file}')
        with open(pagestyles_file, 'r', encoding='utf-8') as f:
            dump_pagestyles = f.read()
    else:
        dump_pagestyles = DEFAULT_PAGESTYLES_TEMPLATE

    default_style = None
    extra_preamble = ''
    use_listings_from = getattr(args, 'use_listings_from', None)
    if use_listings_from:
        default_style, extra_preamble = _build_listings_extra_preamble(use_listings_from)

    exam_doc_specs = dict(
        institution=args.institution,
        course=args.course,
        term=args.term,
        examname=f"{len(selected_questions)}-question dump",
        version=version_label,
        instructions=dump_instructions,
        pagestyles=dump_pagestyles,
        question_renderer=lambda q: render_question(q, show_id=True, highlight_correct=True, default_style=default_style),
        question_list=selected_questions,
        fontsize=getattr(args, 'font_size', '12pt'),
        questionspacing=getattr(args, 'question_spacing', '24pt'),
        endmessage="End of Exam\n\\clearpage",
        extra_preamble=extra_preamble,
    )

    exam_doc = ExamDocument(document_specs=exam_doc_specs)
    cleanup = not getattr(args, 'keep_latex', False)
    latex_compiler.build_document(exam_doc, cleanup=cleanup)


def make_exams_subcommand(args):
    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'latex-engine': 'xelatex',
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
    question_set.copy_images_to(Path.cwd())
    version_answer_records: list[tuple[str, list[str]]] = []

    # Load custom instructions if provided, otherwise use default
    if args.instructions_file is not None:
        logger.info(f'Loading custom exam instructions from {args.instructions_file}')
        with open(args.instructions_file, 'r', encoding='utf-8') as f:
            exam_instructions = f.read()
    else:
        exam_instructions = DEFAULT_EXAM_INSTRUCTIONS

    pagestyles_file = getattr(args, 'pagestyles_file', None)
    if pagestyles_file is not None:
        logger.info(f'Loading custom page styles from {pagestyles_file}')
        with open(pagestyles_file, 'r', encoding='utf-8') as f:
            exam_pagestyles = f.read()
    else:
        exam_pagestyles = DEFAULT_PAGESTYLES_TEMPLATE

    default_style = None
    extra_preamble = ''
    use_listings_from = getattr(args, 'use_listings_from', None)
    if use_listings_from:
        default_style, extra_preamble = _build_listings_extra_preamble(use_listings_from)

    encode_answers = getattr(args, 'encode_answers_in_qr', False)
    qr_key = generate_key() if encode_answers else None

    answer_sheet_layout = LayoutConfig(
        bubble_field_num_cols = args.num_cols,
        num_questions = args.num_questions,
        bubble_font_size_pt = getattr(args, 'bubble_font_size', 8.0),
        force_odd_page = getattr(args, 'odd_page_answersheet', False),
        qr_answer_key = qr_key,
    )
    json_answersheet_layout_path = output_dir/"answersheet_layout.json"
    save_layout_config(answer_sheet_layout, json_answersheet_layout_path, _ureg)
    logger.info(f'Wrote JSON answer sheet layout config to {json_answersheet_layout_path}')
    if encode_answers:
        logger.info('Answer encoding enabled: correct answers will be encrypted in each QR code')
    # write_answer_sheet_layout_yaml(answer_sheet_layout, output_path=output_dir/"answer_sheet_layout.yaml")
    # generate the list of version numbers as 8-byte hexadecimal strings

    for version_label in hex_strings:
        # generate an 8-digit version as an integer and then zero-pad to string
        version_rng_seed = int(version_label, 16)

        selected_questions = question_set.get_random_selection(num_questions=args.num_questions,
                                                               topics_order=args.topics,
                                                               seed=version_rng_seed,
                                                               shuffle=args.shuffle_questions,
                                                               shuffle_choices=args.shuffle_choices,
                                                               balance_difficulty=getattr(args, 'balance_difficulty', False))
        logger.debug(f'Generated exam version {version_label} with {len(selected_questions)} questions.')
        answers = [
            str(q["correct"] if "correct" in q else q.get("answer", "")).strip()
            for q in selected_questions
        ]
        version_answer_records.append((version_label, answers))

        if encode_answers:
            # Normalise to single characters (same as autograder CSV loading)
            normalised = [
                'a' if a == 'True' else 'b' if a == 'False' else a.lower()
                for a in answers
            ]
            qr_content = f"{version_label}:{encrypt_answers(qr_key, normalised)}"
        else:
            qr_content = version_label

        qr_image_filename = f"qr_{version_label}.png"
        generate_qr_png(qr_content, output_dir / qr_image_filename,
                        display_size_cm=answer_sheet_layout.qr_size.to('cm').magnitude)
        logger.debug(f"Generated QR image {qr_image_filename}")

        answersheet_generator = AnswerSheetGenerator(
            layout_config=answer_sheet_layout,
            question_list=selected_questions,
        )

        answersheet_tex = answersheet_generator.generate_tex(version_label=version_label, qr_image_filename=qr_image_filename)

        exam_doc_specs = dict(
            institution=args.institution,
            course=args.course,
            term=args.term,
            examname=args.exam_name,
            version=version_label,
            instructions=exam_instructions,
            pagestyles=exam_pagestyles,
            question_renderer=lambda q: render_question(q, default_style=default_style),
            question_list=selected_questions,
            answersheet_tex=answersheet_tex,
            fontsize=getattr(args, 'font_size', '12pt'),
            questionspacing=getattr(args, 'question_spacing', '24pt'),
            endmessage="End of Exam\n\\clearpage",
            extra_preamble=extra_preamble,
        )

        exam_doc = ExamDocument(document_specs=exam_doc_specs)
        latex_compiler.build_document(exam_doc, cleanup=args.cleanup)
        if getattr(args, 'rasterize', False):
            pdf_path = output_dir / f"exam-{version_label}.pdf"
            rasterize_pdf(pdf_path)

    write_version_keys_csv(version_answer_records, output_path=output_dir/"exam_version_keys.csv")

    # Generate PDF version of answer keys
    write_version_keys_pdf(
        records=version_answer_records,
        output_dir=output_dir,
        institution=args.institution,
        course=args.course,
        term=args.term,
        exam_name=args.exam_name,
        max_versions_per_table=10,
    )

def make_answersheet_subcommand(args):
    layout_config = LayoutConfig(
        bubble_field_num_cols = args.num_cols,
        num_questions = args.num_questions,
        student_id_num_digits=args.student_id_num_digits,
        bubble_font_size_pt = getattr(args, 'bubble_font_size', 8.0),
        force_odd_page = getattr(args, 'odd_page_answersheet', False),
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
    qr_image_filename = "qr_SAMPLE.png"
    generate_qr_png("SAMPLE", Path(args.output_dir) / qr_image_filename,
                    display_size_cm=layout_config.qr_size.to('cm').magnitude)
    answersheet_tex = answersheet_generator.generate_tex(version_label="SAMPLE", qr_image_filename=qr_image_filename)

    latex_compiler = LatexCompiler(build_specs={
        'paths': {
            'latex-engine': 'xelatex',
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
    if getattr(args, 'rasterize', False):
        pdf_path = Path(args.output_dir) / f"{args.output_pdf}-SAMPLE.pdf"
        rasterize_pdf(pdf_path)

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
    # global _ureg
    pdf = args.input_pdf
    keyfiles = args.keyfiles
    answersheetlayoutjson = args.answersheet_layout_json
    output_dir_path = Path(args.output_dir)
    debug_output_dir_path = Path(args.debug_output_dir)
    failed_pages_dir_path = Path(args.failed_pages_dir) if args.failed_pages_dir else None
    gradebook_paths = args.gradebooks
    question_tally_path = Path(args.question_tally) if args.question_tally else None
    if not output_dir_path.exists():
        output_dir_path.mkdir(parents=True, exist_ok=True)
    if not debug_output_dir_path.exists():
        debug_output_dir_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Autograding PDF {pdf} using keyfiles {keyfiles} and layout {answersheetlayoutjson}")

    layout_config = load_layout_config(answersheetlayoutjson, LayoutConfig, _ureg)

    autograder = Autograder(layout_config=layout_config)
    for keyfile in (keyfiles or []):
        autograder.load_version_keys_csv(keyfile)

    autograder.grade_pdf(pdf, output_dir_path=output_dir_path,
        failed_pages_dir_path=failed_pages_dir_path,
        debug_output_dir_path=debug_output_dir_path,
        gradebook_paths=gradebook_paths,
        score_column=args.score_column,
        column_id=args.column_id,
        num_counted=args.num_counted,
        question_tally_path=question_tally_path,
        interactive=args.interactive)

def return_subcommand(args):
    gradebook_paths = args.gradebooks
    if not gradebook_paths:
        print("Error: at least one gradebook is required (--gradebooks)")
        return 1
    return_graded_exams(
        gradebook_paths=gradebook_paths,
        graded_dir=Path(args.graded_dir),
        exams_dir=Path(args.exams_dir),
        email_column=args.email_column,
        email_suffix=args.email_suffix,
        subject=args.subject,
        body=args.body,
        dry_run=args.dry_run,
        sleep_seconds=args.sleep_seconds,
    )