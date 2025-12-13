"""
Given a bank of questions in YAML format, and specifications on
    - which topics to include
    - how many questions per topic
    - how many unique versions of the exam to generate
generate the specified number of unique exam versions in LaTeX format.  Also generate answer keys for each version.
Uses the yaml2tex.py module.
"""

import csv
import random
import yaml
import os
from ..latex.content import *
from .yaml2tex import render_mcq, tex_escape

def generate_version_label(rng: random.Random) -> str:
    """
    Generate an 8-digit zero-padded integer label, e.g. '03749218'.
    Deterministic as long as rng is seeded consistently.
    """
    return f"{rng.randint(0, 99999999):08d}"

def headmatter_for_version(version_label: str, instructions: str = DEFAULT_EXAM_INSTRUCTIONS) -> str:
    """
    Fill in HEADMATTER placeholders for a given version label.
    We use the label itself as the QR text, but you could add
    more info (course, term, etc.) if desired.
    """
    return (
        HEADMATTER
        .replace("<<VERSION_LABEL>>", version_label)
        .replace("<<VERSION_QR_TEXT>>", version_label)
        + make_qr_header_instructions(instructions)
    )

def select_questions_by_topic(
    questions_by_topic: dict,
    q_count_dict: dict,
    topics_order: list[str] | None = None,
    seed: int | None = None,
) -> list[dict]:
    """
    Select questions per topic based on q_count_dict.

    - questions_by_topic: {topic: [question_dict, ...]}
    - q_count_dict: {topic: desired_count}
    - topics_order: optional list of topics to define output ordering
      (if None, topics come in the order of q_count_dict.keys()).
    - seed: RNG seed for reproducible sampling.

    Returns a flat list of question dicts.
    """
    rng = random.Random(seed)

    # Determine the order in which we traverse topics
    if topics_order is None:
        ordered_topics = list(q_count_dict.keys())
    else:
        # Only include topics that actually appear in q_count_dict
        ordered_topics = [t for t in topics_order if t in q_count_dict]

    selected_questions: list[dict] = []

    for topic in ordered_topics:
        desired = q_count_dict.get(topic, 0)
        if desired <= 0:
            continue

        pool = questions_by_topic.get(topic, [])
        available = len(pool)

        if desired > available:
            raise ValueError(
                f"Requested {desired} questions for topic '{topic}' "
                f"but only {available} available."
            )

        if desired == available:
            # No need to sample, but we still want deterministic behavior
            chosen = list(pool)
        else:
            # Sample without replacement
            chosen = rng.sample(pool, desired)

        selected_questions.extend(chosen)

    return selected_questions

def build_exam_tex(
    selected_questions: list[dict],
    headmatter: str,
    tailmatter: str,
    render_question,
    extra_content: str = "",
) -> str:
    """
    Build a complete LaTeX document from selected questions.
    `render_question` is a callable that takes a question dict and returns
    LaTeX source (string) for that question.

    If `extra_content` is non-empty, it is inserted before tailmatter. This
    is a good place to put an answer sheet, instructions, etc.
    """
    parts: list[str] = []

    parts.append(headmatter.rstrip())
    parts.append("")  # blank line after head

    for q in selected_questions:
        parts.append(render_question(q).rstrip())
        parts.append("")  # blank line between questions

    parts.append(ENDMESSAGE.rstrip())

    if extra_content:
        parts.append(extra_content.rstrip())
        parts.append("")

    parts.append(tailmatter.lstrip())

    return "\n".join(parts)


def get_data(yaml_paths: list[str] = []):
    data = {}
    for yaml_file in yaml_paths:
        with open(yaml_file, "r", encoding="utf-8") as f:
            file_data = yaml.safe_load(f)
            if not data:
                data = file_data
            else:
                # Merge questions from multiple files
                data["questions"].extend(file_data.get("questions", []))
                for topic in file_data.get("topics", []):
                    if topic not in data.get("topics", []):
                        data.setdefault("topics", []).append(topic)
    return data

def build_answer_sheet(
    num_questions: int,
    choice_keys: list[str] | None = None,
) -> str:
    """
    Build a LaTeX answer sheet using \circledletter for each choice.

    - num_questions: total number of questions in the exam
    - choice_keys: list of choice labels (e.g., ["a","b","c","d"]).
    """
    if choice_keys is None or not choice_keys:
        choice_keys = ["a", "b", "c", "d"]

    choice_keys = sorted(choice_keys)

    lines: list[str] = []
    lines.append(r"\newpage")
    lines.append(r"\newgeometry{top=2in}")
    lines.append(r"\thispagestyle{answersheet}")
    # Fiducial markers in four corners (slightly inset)
    lines.append(r"\begin{tikzpicture}[remember picture,overlay]")
    lines.append(
        r"\node[fill=black,circle,inner sep=1.5pt,"
        r"xshift=0.5cm,yshift=-3.04cm] at (current page.north west) {};"
    )
    lines.append(
        r"\node[fill=black,circle,inner sep=1.5pt,"
        r"xshift=-0.5cm,yshift=-3.04cm] at (current page.north east) {};"
    )
    lines.append(
        r"\node[fill=black,circle,inner sep=1.5pt,"
        r"xshift=0.5cm,yshift=0.5cm] at (current page.south west) {};"
    )
    lines.append(
        r"\node[fill=black,circle,inner sep=1.5pt,"
        r"xshift=-0.5cm,yshift=0.5cm] at (current page.south east) {};"
    )
    lines.append(r"\end{tikzpicture}")

    lines.append("")
    # Version + QR again on answer sheet page:
    lines.extend(make_qr_header_instructions(DEFAULT_ANSWER_SHEET_INSTRUCTIONS).splitlines())
    # Compact table settings
    lines.append(r"\begin{small}")                # or \footnotesize if needed
    lines.append(r"\setlength{\tabcolsep}{4pt}")  # horizontal padding
    lines.append(r"\renewcommand{\arraystretch}{0.8}")  # vertical tightness
    lines.append(r"\begin{center}")
    # Two columns: aligned Q#, then bubbles
    num_cols = 3
    rows = (num_questions + num_cols - 1) // num_cols
    col_spec = " @{\\hspace{2em}} ".join(["r l"] * num_cols)
    lines.append(rf"\begin{{tabular}}{{{col_spec}}}")

    for r in range(rows):
        cell_tex_parts = []

        for c in range(num_cols):
            qnum = r + c * rows + 1
            if qnum <= num_questions:
                bubbles = " ".join(rf"\circledletter{{{k}}}" for k in choice_keys)
                # Fixed-width box so 1., 10., etc align
                num_tex = rf"\makebox[2em][r]{{\textbf{{{qnum}}}.}}"
                cell_tex_parts.append(f"{num_tex} & {bubbles}")
            else:
                # Empty cell pair for padding
                cell_tex_parts.append(r"")

        # Join all logical cells with &
        row_tex = " & ".join(cell_tex_parts)

        # Extra vertical space after every 5th *row* (blocks of 5 vertically)
        if (r + 1) % 5 == 0 and (r + 1) < rows:
            row_tex += r" \\[2em]"
        else:
            row_tex += r" \\[0.5em]"

        lines.append(row_tex)

    lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")
    lines.append(r"\end{small}")
    lines.append(r"\restoregeometry")
    lines.append("")

    return "\n".join(lines)

def build_answer_key_tex(
    selected_questions: list[dict],
    head: str = HEADMATTER,
    tail: str = TAILMATTER,
    version_label: str = "00000000",
) -> str:
    """
    Build a complete LaTeX answer key document with a simple
    two-column list of answers:
        Q1  a     Q2  c
        Q3  d     Q4  b
    etc.
    """
    # Collect (question_number, correct_letter)
    answers = [
        (i + 1, str(q.get("correct", "")).strip())
        for i, q in enumerate(selected_questions)
    ]

    parts: list[str] = []
    parts.append(head.rstrip())
    parts.append("")
    parts.append(r"\section*{Answer Key}")
    parts.append("")

    parts.append(r"\begin{center}")
    # left: (Q, Ans)   right: (Q, Ans)
    parts.append(r"\begin{tabular}{r c @{\hspace{1.5cm}} r c}")
    parts.append(r"\textbf{Q} & \textbf{Ans} & \textbf{Q} & \textbf{Ans} \\")
    parts.append(r"\hline")

    # Emit rows with up to two Q/A pairs
    for i in range(0, len(answers), 2):
        (q1, a1) = answers[i]
        if i + 1 < len(answers):
            (q2, a2) = answers[i + 1]
        else:
            q2, a2 = "", ""
        parts.append(rf"{q1} & {a1} & {q2} & {a2} \\")
    parts.append(r"\end{tabular}")
    parts.append(r"\end{center}")
    parts.append("")

    parts.append(tail.lstrip())
    return "\n".join(parts)

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


def make_exams(args):

    yaml_paths = args.question_banks

    output_dir = args.output_dir

    data = get_data(yaml_paths)

    topics_from_yaml = data.get("topics", [])
    raw_question_list = data.get("questions", [])
    questions_by_topic = {}
    for q in raw_question_list:
        topic = q.get("topic", "General")
        if topic not in questions_by_topic:
            questions_by_topic[topic] = []
        questions_by_topic[topic].append(q)

    apparent_topics = list(questions_by_topic.keys())
    for topic in apparent_topics:
        print(f"Topic '{topic}': {len(questions_by_topic[topic])} questions available.")
    if not args.topics:
        selected_topics = apparent_topics
    else:
        selected_topics = args.topics
    q_count_dict = {topic: args.questions_per_topic for topic in selected_topics}

    if args.full_dump:
        # Use a dummy version label for full dump
        version_label = "00000000"
        bankfiles = tex_escape(", ".join(yaml_paths))
        hm = headmatter_for_version(version_label, instructions=f"Full dump of all questions in \n{bankfiles}")

        selected_questions = raw_question_list
        exam_tex = build_exam_tex(
            selected_questions,
            hm,
            TAILMATTER,
            render_question=lambda q: render_mcq(
                q,
                show_id=True,
                highlight_correct=True,
            ),
            extra_content="",  # no answer sheet for full dump
        )
        with open("exam_full_dump.tex", "w", encoding="utf-8") as f:
            f.write(exam_tex)

    else:
        # create the output dir if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        # Generate multiple versions
        master_rng = random.Random(args.seed)
        version_answer_records: list[tuple[str, list[str]]] = []
        for v_index in range(1, args.num_versions + 1):
            # Version-specific seed for question selection
            v_seed = master_rng.randint(0, 2**31 - 1)
            version_label = generate_version_label(master_rng)

            hm = headmatter_for_version(version_label)

            selected_questions = select_questions_by_topic(
                questions_by_topic=questions_by_topic,
                q_count_dict=q_count_dict,
                topics_order=topics_from_yaml,
                seed=v_seed,
            )

            # Optional: shuffle question order within this version
            rng_v = random.Random(v_seed)
            rng_v.shuffle(selected_questions)

            # Determine choice keys used across questions
            all_keys = {
                str(c.get("key", "")).strip()
                for q in selected_questions
                for c in q.get("choices", [])
                if c.get("key", "") not in (None, "")
            }
            if not all_keys:
                all_keys = {"a", "b", "c", "d"}
            choice_keys = sorted(all_keys)

            # Build answer sheet for this version
            answer_sheet_tex = build_answer_sheet(
                num_questions=len(selected_questions),
                choice_keys=choice_keys,
            )

            # Exam + attached answer sheet
            exam_tex = build_exam_tex(
                selected_questions,
                headmatter_for_version(version_label, instructions=DEFAULT_EXAM_INSTRUCTIONS),
                TAILMATTER,
                render_question=lambda q: render_mcq(
                    q,
                    show_id=False,
                    highlight_correct=False,
                ),
                extra_content=answer_sheet_tex,
            )

            exam_filename = output_dir / f"exam_v{v_index}.tex"
            with open(exam_filename, "w", encoding="utf-8") as f:
                f.write(exam_tex)

            # Answer key document for this version
            key_tex = build_answer_key_tex(
                selected_questions,
                headmatter_for_version(version_label, instructions="Answer Key"),
                TAILMATTER,
                version_label=f"{version_label}",
            )
            key_filename = output_dir / f"exam_v{v_index}_key.tex"
            with open(key_filename, "w", encoding="utf-8") as f:
                f.write(key_tex)

            # If you are NOT shuffling choices, and the correct option is just
            # stored as q["correct"] (like 'a', 'b', 'c', 'd'), then:
            answers_in_order = [
                str(q.get("correct", "")).strip()
                for q in selected_questions
            ]

            # If you ARE shuffling choices and remapping letters, you would compute
            # the *displayed* correct letter here instead (using your mapping).

            version_answer_records.append((version_label, answers_in_order))

        write_version_keys_csv(version_answer_records, output_path=output_dir/"exam_version_keys.csv")
