"""
LaTeX rendering helpers for pyaota.
"""

import re

import logging

logger = logging.getLogger(__name__)

# ---------- Normalization helpers ----------

def normalize_punctuation(s: str) -> str:
    """Normalize Word-style Unicode punctuation to ASCII/TeX-friendly equivalents."""
    replacements = {
        "…": "...",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "--",
        "\u2011": "-",  # non-breaking hyphen
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s

def tex_escape(s: str) -> str:
    s = normalize_punctuation(s)
    return tex_escape_plain(s)

def tex_escape_plain(s: str) -> str:
    """
    Escape LaTeX special characters in *normal text* context.
    Also convert runs of 4+ underscores to \\blank{}.
    """
    # convert "____" etc to placeholder first
    s = re.sub(r'_{4,}', '<<BLANK>>', s)
    s = re.sub(r'_{2,}', '<<SMALLBLANK>>', s)  # optional: smaller blank for 2-3 underscores

    replacements = {
        '\\': r'\textbackslash{}',
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    out = []
    for ch in s:
        out.append(replacements.get(ch, ch))
    esc = ''.join(out)

    # turn placeholder back into \blank{}
    esc = esc.replace('<<BLANK>>', r'\blank{}')
    esc = esc.replace('<<SMALLBLANK>>', r'\smallblank{}')
    return esc

def tex_escape_inline_code(s: str) -> str:
    """
    Escape content that will go inside \\inl{...}.
    We:
      - normalize punctuation
      - escape %, _, {, } so TeX doesn't get confused
    """
    s = normalize_punctuation(s)

    replacements = {
        '^^' : r'\^\^',
        '^' : r'\^',
        '%': r'\%',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
    }
    out = []
    for ch in s:
        out.append(replacements.get(ch, ch))
    return ''.join(out)

# ---------- Render helpers ----------

def render_text(s: str) -> str:
    """
    Render a text string that may contain ``inline code`` markers
    into LaTeX, using \\inl{...} for the code spans and escaping
    the rest as normal text.
    """
    s = normalize_punctuation(s)
    result_parts = []
    pos = 0
    pattern = re.compile(r'``(.*?)``')

    for m in pattern.finditer(s):
        before = s[pos:m.start()]
        code = m.group(1)

        if before:
            result_parts.append(tex_escape_plain(before))
        # print(f'inline code found: {code}, rendering...')
        # print(f'  -> escaped inline code: {tex_escape_inline_code(code)}')
        result_parts.append(f"\\inl{{{tex_escape_inline_code(code)}}}")

        pos = m.end()

    tail = s[pos:]
    if tail:
        result_parts.append(tex_escape_plain(tail))

    return ''.join(result_parts)

def render_code_block(text: str, style: str = "mypython", force_env: bool = True) -> tuple[str, str]:
    """
    Render code as either:
      - ("inline",  '\\inl{...}')    for a single nonblank line
      - ("block",  '\\begin{lstlisting}...\\end{lstlisting}') for multi-line

    Caller decides how to embed the result.
    """
    text = normalize_punctuation(text)
    code_lines = text.splitlines()

    # Strip leading/trailing blank lines
    while code_lines and not code_lines[0].strip():
        code_lines.pop(0)
    while code_lines and not code_lines[-1].strip():
        code_lines.pop()

    # No code at all → treat as empty block
    if not code_lines:
        return "block", (
            f"\\begin{{lstlisting}}[style={style}]\n"
            "\\end{lstlisting}"
        )

    # Single line → inline
    if len(code_lines) == 1 and not force_env:
        single = code_lines[0]
        if style == "mypython":
            return "inline", f"\n\\inl{{{tex_escape_inline_code(single)}}}"
        elif style == "pseudocode":
            return "inline", f"\n\\texttt{{{tex_escape_inline_code(single)}}}"
    # Multi-line → block lstlisting
    code = "\n".join(code_lines)
    return "block", (
        f"\\begin{{lstlisting}}[style={style}]\n"
        + code +
        "\n\\end{lstlisting}"
    )


def render_stem_block(block: dict) -> str:
    """
    Render a single stem block (text or code) to LaTeX.
    """
    btype = block.get("type", "text")
    if btype == "text":
        txt = block.get("text", "")
        return render_text(txt)
    elif btype == "code":
        text = block.get("text", "")
        style = block.get("style", "mypython")
        kind, tex = render_code_block(text, style)
        # For stems, just return whatever tex we got (inline or block)
        return tex
    else:
        return f"% [unhandled stem block type: {btype}]"

def render_choice(
    choice: dict,
    correct_key: str | None = None,
    highlight_correct: bool = False,
) -> str:
    """
    Render a single choice dict to LaTeX.

    - type: "text"  -> \\choice[<label>]{<text>}
    - type: "code"  -> inline or block via render_code_block
    - highlight_correct: if True, the correct choice's LABEL is wrapped
      in \\correctlabel{...}, leaving the body (including \\inl) untouched.
    """
    key = choice["key"]
    raw_text = str(choice.get("text", ""))
    ctype = choice.get("type", "text")
    style = choice.get("style", "mypython")

    is_correct = (correct_key is not None) and (key == correct_key)

    if highlight_correct and is_correct:
        label = rf"\correctlabel{{{key}}}"
        # label = rf"\textbf{{{key}}}."
    else:
        # label = rf"\circledletter{{{key}}}"
        label = f"{key}."

    # --- Code choices ---
    if ctype == "code":
        kind, tex = render_code_block(raw_text, style, force_env=False)

        if kind == "inline":
            # Single-line code as inline body (\inl{...})
            body = tex
            return rf"  \choice[{label}]{{{body}}}"

        # Multi-line code block: empty body, listing follows
        lines = []
        lines.append(rf"  \choice[{label}]{{}}")
        lines.append(tex)
        lines.append("")  # blank line between code choices
        return "\n".join(lines)

    # --- Text choices ---
    body = render_text(raw_text)
    return rf"  \choice[{label}]{{{body}}}"

def render_question(
    q: dict,
    **kwargs) -> str:
    """
    Render a single question dict to LaTeX, dispatching
    to the appropriate renderer based on question type.
    """
    logger.debug(f"Rendering question ID={q.get('id','')} type={q.get('type','mcq')} kwargs={kwargs}")
    qtype = q.get("type", "mcq").lower()
    if qtype == "mcq":
        return render_mcq(q, **kwargs)
    elif qtype == "tf":
        return render_tf(q, **kwargs)

def render_mcq(
    q: dict,
    show_id: bool = False,
    highlight_correct: bool = False,
    scramble_choices: bool = False,
) -> str:
    """
    Render a single multiple-choice question to LaTeX.

    - show_id: if True, prefix the first text stem block with "(ID) ".
    - highlight_correct: if True, visually mark the correct answer.
    """
    qid = q.get("id", "")
    points = q.get("points", 1)
    correct_key = q.get("correct", "").strip()
    topic = q.get("topic", "")
    choices = q.get("choices", [])
    choices_text = [choice.get("text", "") for choice in choices]
    choices_keys = [choice.get("key", "") for choice in choices]
    correct_text = None
    # Save the text of the correct answer for later use
    for choice_text, choice_key in zip(choices_text, choices_keys):
        if choice_key == correct_key:
            correct_text = choice_text
            break
    if scramble_choices:
        import random
        random.shuffle(choices_text)
        for choice, text in choices, choices_text:
            choice["text"] = text
            if text == correct_text:
                correct_key = choice.get("key")
                break
    # Make a shallow copy of stem blocks so we don't mutate the original
    stem_blocks = [dict(block) for block in q.get("stem", [])]

    if show_id:
        # Prepend "(ID)" to the *first* text block
        for block in stem_blocks:
            if block.get("type") == "text":
                orig = block.get("text", "")
                block["text"] = f"({qid}) " + orig
                break

    # Render stem
    stem_lines: list[str] = []
    for block in stem_blocks:
        stem_lines.append(render_stem_block(block))
        stem_lines.append("")  # blank line between blocks
    stem_tex = "\n".join(stem_lines).rstrip()

    # Render choices
    choice_lines: list[str] = []
    choice_lines.append(r"\begin{choices}")
    for choice in q.get("choices", []):
        choice_lines.append(
            render_choice(
                choice,
                correct_key=correct_key,
                highlight_correct=highlight_correct,
            )
        )
    choice_lines.append(r"\end{choices}")
    choices_tex = "\n".join(choice_lines)

    # Wrap in mcq environment; third arg is still the correct key
    mcq_lines = [
        rf"\begin{{mcq}}{{{qid}}}{{{points}}}{{{correct_key}}}",
        stem_tex,
        "",
        choices_tex,
        r"\end{mcq}",
    ]
    return "\n".join(mcq_lines)

def render_tf(
    q: dict,
    show_id: bool = False,
    highlight_correct: bool = False,
) -> str:
    """
    Render a single true/false question to LaTeX.

    - show_id: if True, prefix the first text stem block with "(ID) ".
    - highlight_correct: if True, visually mark the correct answer.
    """
    qid = q.get("id", "")
    points = q.get("points", 1)
    answer = q.get("correct")
    correct_key = "T" if answer else "F"
    topic = q.get("topic", "")

    # Make a shallow copy of stem blocks so we don't mutate the original
    stem_blocks = [dict(block) for block in q.get("stem", [])]

    if show_id:
        # Prepend "(ID)" to the *first* text block
        for block in stem_blocks:
            if block.get("type") == "text":
                orig = block.get("text", "")
                block["text"] = f"({qid}) " + orig
                break

    # Render stem
    stem_lines: list[str] = []
    for block in stem_blocks:
        stem_lines.append(render_stem_block(block))
        stem_lines.append("")  # blank line between blocks
    stem_tex = "\n".join(stem_lines).rstrip()

    # Render choices
    choice_lines: list[str] = []
    choice_lines.append(r"\begin{choices}")
    for tf_key, tf_text in [("T", "True"), ("F", "False")]:
        choice_dict = {"key": tf_key, "text": tf_text, "type": "text"}
        choice_lines.append(
            render_choice(
                choice_dict,
                correct_key=correct_key.upper(),
                highlight_correct=highlight_correct,
            )
        )
    choice_lines.append(r"\end{choices}")
    choices_tex = "\n".join(choice_lines)

    # Wrap in tf environment; third arg is still the correct key
    tf_lines = [
        rf"\begin{{tf}}{{{qid}}}{{{points}}}{{{correct_key}}}",
        stem_tex,
        "",
        choices_tex,
        r"\end{tf}",
    ]
    return "\n".join(tf_lines)
