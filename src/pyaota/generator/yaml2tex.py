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

# Unicode superscript digits -> LaTeX.  Applied while escaping (not during
# normalization), so the generated command is not itself escaped; verbatim
# and listings code keeps the Unicode character.
SUPERSCRIPT_DIGITS = {
    ch: rf"\textsuperscript{{{d}}}"
    for ch, d in zip("\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079", "0123456789")
}

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
        **SUPERSCRIPT_DIGITS,
    }
    out = []
    for ch in s:
        out.append(replacements.get(ch, ch))
    esc = ''.join(out)

    # turn placeholder back into \blank{}
    esc = esc.replace('<<BLANK>>', r'\blank{}')
    esc = esc.replace('<<SMALLBLANK>>', r'\smallblank{}')
    return esc

def tex_escape_texttt(s: str) -> str:
    """
    Escape content for use inside \\texttt{...} (non-verbatim monospace).

    Unlike tex_escape_inline_code, this must escape \\ because \\texttt
    processes its argument as normal LaTeX, so \\n would be an undefined
    control sequence.
    """
    replacements = {
        '\\': r'\textbackslash{}',
        '$': r'\$',
        '%': r'\%',
        '#': r'\#',
        '&': r'\&',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        **SUPERSCRIPT_DIGITS,
    }
    out = []
    for ch in s:
        out.append(replacements.get(ch, ch))
    return ''.join(out)


def tex_escape_inline_code(s: str) -> str:
    """
    Escape content that will go inside \\inl{...}.

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

def render_text(s: str, default_style: str | None = None) -> str:
    """
    Render a text string that may contain ``inline code`` and
    ``@@inline math@@`` markers into LaTeX.

    - ``code`` regions use \\verb|...| (verbatim mode, default_style=None)
      or \\inl{...} (listings mode, default_style set)
    - ``@@math@@`` regions are passed through as ``$...$``
    - Everything else is escaped for normal text.
    """
    s = normalize_punctuation(s)
    result_parts = []
    pos = 0
    # Match @@...@@ (math) or ``...`` (code) in a single pass
    pattern = re.compile(r'@@(.*?)@@|``(.*?)``')

    for m in pattern.finditer(s):
        before = s[pos:m.start()]
        if before:
            result_parts.append(tex_escape_plain(before))

        if m.group(1) is not None:
            # @@...@@ → inline math, pass through raw
            result_parts.append(f"${m.group(1)}$")
        else:
            # ``...`` → inline code
            # \verb cannot be used inside command arguments (e.g. \choice{...}),
            # so always use \texttt with escaping for text-embedded inline code.
            code = m.group(2)
            if default_style:
                result_parts.append(f"\\inl{{{tex_escape_inline_code(code)}}}")
            else:
                result_parts.append(f"\\texttt{{{tex_escape_texttt(code)}}}")

        pos = m.end()

    tail = s[pos:]
    if tail:
        result_parts.append(tex_escape_plain(tail))

    return ''.join(result_parts)

_VERB_DELIMITERS = '|@!~+'

def _choose_verb_delimiter(code: str) -> str | None:
    for c in _VERB_DELIMITERS:
        if c not in code:
            return c
    return None


def render_code_block(text: str, style: str | None = None, force_env: bool = True) -> tuple[str, str]:
    """
    Render code as either an inline or block snippet.

    When *style* is None (the default) the output uses plain LaTeX verbatim:
      - ("inline",  '\\verb|...|')          for a single nonblank line
      - ("block",   '\\begin{verbatim}...') for multi-line

    When *style* is a listings style name the output uses listings:
      - ("inline",  '\\inl{...}')                          single line
      - ("block",   '\\begin{lstlisting}[style=...]...')   multi-line

    Caller decides how to embed the result.
    """
    text = normalize_punctuation(text)
    code_lines = text.splitlines()

    # Strip leading/trailing blank lines
    while code_lines and not code_lines[0].strip():
        code_lines.pop(0)
    while code_lines and not code_lines[-1].strip():
        code_lines.pop()

    # No code at all → empty block
    if not code_lines:
        if style:
            return "block", f"\\begin{{lstlisting}}[style={style}]\n\\end{{lstlisting}}"
        else:
            return "block", "\\begin{verbatim}\n\\end{verbatim}"

    # Single line → inline (only when force_env is False)
    if len(code_lines) == 1 and not force_env:
        single = code_lines[0]
        if style:
            return "inline", f"\n\\inl{{{tex_escape_inline_code(single)}}}"
        else:
            delim = _choose_verb_delimiter(single)
            if delim:
                return "inline", f"\n\\verb{delim}{single}{delim}"
            # Fallback: escape and use \texttt when no safe delimiter exists
            return "inline", f"\n\\texttt{{{tex_escape_texttt(single)}}}"

    # Multi-line → block
    code = "\n".join(code_lines)
    if style:
        return "block", (
            f"\\begin{{lstlisting}}[style={style}]\n"
            + code +
            "\n\\end{lstlisting}"
        )
    else:
        return "block", (
            "\\begin{verbatim}\n"
            + code +
            "\n\\end{verbatim}"
        )


def render_stem_block(block: dict, default_style: str | None = None) -> str:
    """
    Render a single stem block (text, code, or image) to LaTeX.
    """
    btype = block.get("type", "text")
    if btype == "text":
        txt = block.get("text", "")
        return render_text(txt, default_style=default_style)
    elif btype == "code":
        text = block.get("text", "")
        # Only use the block's style override when listings mode is active;
        # in verbatim mode (default_style is None) always use None.
        style = block.get("style", default_style) if default_style is not None else None
        kind, tex = render_code_block(text, style)
        # For stems, just return whatever tex we got (inline or block)
        return tex
    elif btype == "image":
        src = block.get("src", "")
        width = block.get("width", "")
        # Convert pixel width to a fraction of linewidth (assume ~500px ≈ full width)
        lw_frac = 0.5
        if width:
            try:
                px = int(re.sub(r'[^0-9]', '', width))
                lw_frac = min(round(px / 500, 2), 1.0)
            except (ValueError, TypeError):
                pass
        return (
            f"\n\\begin{{center}}\n"
            f"\\includegraphics[width={lw_frac}\\linewidth]{{images/{src}}}\n"
            f"\\end{{center}}"
        )
    else:
        return f"% [unhandled stem block type: {btype}]"

def _visual_len(text: str) -> int:
    """Estimate the visual character width of a raw YAML choice text string.

    Strips ``...`` inline-code markers and @@...@@ math markers, which add
    character overhead relative to their rendered width.
    """
    s = re.sub(r'``(.*?)``', r'\1', text)
    s = re.sub(r'@@(.*?)@@', r'\1', s)
    return len(s)


# Page and font metrics for the choice-column fit check, in TeX points.
TEXTWIDTH_PT = 469.755        # letter paper with 1in margins (6.5in)
CHOICE_INDENT_EM = 2.0        # enumerate leftmargin in the choices environment
CHOICE_COLUMN_SEP_PT = 10.0   # \columnsep inside the choices environment
CHOICE_FIT_SLACK_PT = 2.0
MONO_EM_PER_CHAR = 0.525      # Latin Modern Mono, the \ttfamily font: exact
# Text choices wrap within their column, so this need not be exact. It is set
# so that a full-width question keeps its old 2-column limit of 40 characters.
TEXT_EM_PER_CHAR = 0.42

_TEX_UNITS_PT = {'pt': 1.0, 'bp': 72.27 / 72, 'in': 72.27, 'cm': 72.27 / 2.54,
                 'mm': 72.27 / 25.4, 'pc': 12.0}


def length_to_pt(length: str, font_pt: float = 12.0) -> float:
    """Convert a LaTeX length such as ``2em``, ``18pt`` or ``0.5cm`` to points."""
    m = re.fullmatch(r'\s*([0-9]*\.?[0-9]+)\s*(pt|bp|in|cm|mm|pc|em)\s*', str(length))
    if not m:
        raise ValueError(f"cannot read LaTeX length {length!r}; use a number with pt, bp, in, cm, mm, pc or em")
    value, unit = float(m.group(1)), m.group(2)
    return value * (font_pt if unit == 'em' else _TEX_UNITS_PT[unit])


def _choice_width_pt(choice: dict, font_pt: float) -> float:
    """Estimated natural width of a choice's text, in points."""
    raw = str(choice.get("text", ""))
    if choice.get("type", "text") == "code":
        lines = [l for l in raw.splitlines() if l.strip()]
        return max((len(l) for l in lines), default=0) * MONO_EM_PER_CHAR * font_pt
    return _visual_len(raw) * TEXT_EM_PER_CHAR * font_pt


def _choices_columns(choices: list[dict], column_width_pt: float = TEXTWIDTH_PT,
                     font_pt: float = 12.0) -> int:
    """Return 4, 2 or 1: the most columns in which every choice fits.

    *column_width_pt* is the width the question is set in: the text width, or
    one question column's width when questions are set in columns.
    """
    widest = max((_choice_width_pt(c, font_pt) for c in choices), default=0.0)
    for ncols in (4, 2):
        col = (column_width_pt - (ncols - 1) * CHOICE_COLUMN_SEP_PT) / ncols
        if widest + CHOICE_INDENT_EM * font_pt + CHOICE_FIT_SLACK_PT <= col:
            return ncols
    return 1


def render_choice(
    choice: dict,
    correct_key: str | None = None,
    highlight_correct: bool = False,
    default_style: str | None = None,
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
    # Only use the choice's style override when listings mode is active.
    style = choice.get("style", default_style) if default_style is not None else None

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

        # Emit code after empty choice body so \lstinline is not nested inside
        # a command argument — pre-tokenized args break \lstinline's verbatim
        # space handling, causing spaces inside string literals (e.g. " ") to
        # disappear in the rendered output.
        lines = []
        lines.append(rf"  \choice[{label}]{{}}%")
        lines.append(tex.lstrip('\n'))
        lines.append("")  # blank line between code choices
        return "\n".join(lines)

    # --- Text choices ---
    body = render_text(raw_text, default_style=default_style)
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
    default_style: str | None = None,
    column_width_pt: float = TEXTWIDTH_PT,
    font_pt: float = 12.0,
) -> str:
    """
    Render a single multiple-choice question to LaTeX.

    - show_id: if True, prefix the first text stem block with "(ID) ".
    - highlight_correct: if True, visually mark the correct answer.
    - column_width_pt, font_pt: the width the question is set in and the
      document font size; they decide how many columns the choices use.
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
        stem_lines.append(render_stem_block(block, default_style=default_style))
        stem_lines.append("")  # blank line between blocks
    stem_tex = "\n".join(stem_lines).rstrip()

    # Render choices
    ncols = _choices_columns(q.get("choices", []), column_width_pt=column_width_pt, font_pt=font_pt)
    choice_lines: list[str] = []
    choice_lines.append(rf"\begin{{choices}}[{ncols}]")
    for choice in q.get("choices", []):
        choice_lines.append(
            render_choice(
                choice,
                correct_key=correct_key,
                highlight_correct=highlight_correct,
                default_style=default_style,
            )
        )
    choice_lines.append(r"\end{choices}")
    choices_tex = "\n".join(choice_lines)

    # If the stem ends with a lstlisting block, cancel its belowskip so the
    # choices don't have excess space above them.
    last_stem_block = stem_blocks[-1] if stem_blocks else None
    if last_stem_block is not None and last_stem_block.get("type") == "code":
        choices_tex = r"\vspace{-\medskipamount}" + "\n" + choices_tex

    # Wrap in mcq environment; third arg is still the correct key
    mcq_lines = [
        rf"\begin{{mcq}}{{{qid}}}{{{points}}}{{{correct_key}}}",
        stem_tex,
        choices_tex,
        r"\end{mcq}",
    ]
    return "\n".join(mcq_lines)

def render_tf(
    q: dict,
    show_id: bool = False,
    highlight_correct: bool = False,
    default_style: str | None = None,
    column_width_pt: float = TEXTWIDTH_PT,
    font_pt: float = 12.0,
) -> str:
    """
    Render a single true/false question to LaTeX.

    - show_id: if True, prefix the first text stem block with "(ID) ".
    - highlight_correct: if True, visually mark the correct answer.
    """
    qid = q.get("id", "")
    points = q.get("points", 1)
    # QuestionSet normalizes ``correct`` to a bool; fall back to ``answer``
    # for questions rendered without it
    answer = q.get("correct", q.get("answer"))
    if isinstance(answer, str):
        answer = answer.strip().lower() in ("true", "t", "yes", "y")
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

    # Build the T/F prefix label
    if highlight_correct:
        if correct_key == "T":
            tf_label = r"\correctlabel{T}\,True\,/\,False\,(F)\enspace "
        else:
            tf_label = r"True\,(T)\,/\,\correctlabel{F}\,False\enspace "
    else:
        tf_label = r"\textbf{True\,(T)\,/\,False\,(F)}\enspace "

    # Render stem, prepending the T/F label
    stem_lines: list[str] = []
    for i, block in enumerate(stem_blocks):
        rendered = render_stem_block(block, default_style=default_style)
        if i == 0 and block.get("type") == "text":
            rendered = tf_label + rendered
        stem_lines.append(rendered)
        stem_lines.append("")  # blank line between blocks
    stem_tex = "\n".join(stem_lines).rstrip()

    # Wrap in tf environment; third arg is still the correct key
    tf_lines = [
        rf"\begin{{tf}}{{{qid}}}{{{points}}}{{{correct_key}}}",
        stem_tex,
        r"\end{tf}",
    ]
    return "\n".join(tf_lines)
