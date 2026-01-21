# Author: Cameron F. Abrams, <cfa22@drexel.edu>

from typing import Dict, List, Tuple, Sequence, Optional, Any
import cv2
import numpy as np
import math
from pathlib import Path
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
# ---------------- Layout configuration ----------------

@dataclass
class TextBoxConfig:
    box_origin_x_frac: float = 0.2  # normalized coords
    box_origin_y_frac: float = 0.6
    background_color: Tuple[int, int, int] = (77, 41, 7)  # black
    background_alpha: float = 0.25  # semi-transparent
    text_color: Tuple[int, int, int] = (255, 230, 25)  # yellow
    text_scale: float = 2.5
    text_thickness: int = 4
    box_margin_frac: float = 0.04  # margin inside box

@dataclass
class LayoutConfig:
    ### bubble field layout parameters ###
    num_questions: int  # must be provided
    num_cols: int = 3
    rows_per_block: int = 5

    choice_keys: Sequence[str] = ("a", "b", "c", "d")
    tf_keys: Sequence[str] = ("T", "F")

    # latex lengths for margins
    page_top_margin_in: float = 1.0
    page_bottom_margin_in: float = 1.0
    page_left_margin_in: float = 1.0
    page_right_margin_in: float = 1.0

    canonical_width_px: int = 1700

    # indicial shifts
    indicial_sep: str = "0.5mm"
    indicial_east_shift: str = "-1.0cm"
    indicial_west_shift: str = "1.0cm"
    indicial_north_shift: str = "-2.7cm"
    indicial_south_shift: str = "1.0cm"

    # indicial regions
    indicial_top_vertical_margin_frac: float = 0.06
    indicial_bottom_vertical_margin_frac: float = 0.05
    indicial_horizontal_margin_frac: float = 0.05
    indicial_horizontal_size_frac: float = 0.05
    indicial_vertical_size_frac: float = 0.05

    # bubble array for answer grid
    # --- Vertical structure ---
    tabcolsep: str = '4pt'  # horizontal padding
    arraystretch: float = 0.8  # vertical tightness
    majorcolsep: str = '2em'  # space between columns
    majorrowsep: str = '2em'  # space between blocks
    intrarowsep: str = '0.5em'  # space between rows

    # qr location
    qr_upper_left_fracs: Tuple[float, float] = (0.214, 0.1)  # (x_frac, y_frac)
    qr_size_frac: float = 0.075  # size of QR square

    # parameters used by the reader

    # y-coordinate of the first row's bubbles in *normalized* coordinates
    first_row_top: float = 0.327

    # Vertical spacing between consecutive question rows *within a block*
    row_spacing: float = 0.026  # tune

    # Extra vertical gap *between* blocks (on top of row_spacing steps)
    block_gap: float = 0.0226   # tune

    # --- Horizontal structure ---

    # x-coordinate of the first column's 'a' bubble (Q1) in normalized coords
    first_col_left: float = 0.203

    # Horizontal spacing between columns (distance from col c to col c+1
    # for the 'a' bubble of the same row)
    col_spacing: float = 0.1899   # tune

    # Horizontal spacing between choices (a->b, b->c, etc.), normalized
    choice_spacing: float = 0.0263

    # --- Bubble reading parameters ---

    # Radius of sampling region as fraction of min(width, height)
    bubble_radius_frac: float = 0.015

    # Darkness threshold to call a bubble filled
    fill_ratio_threshold: float = 0.10

    # runner up margin (relative) to call a bubble filled
    runner_up_margin: float = 0.09

    # --- Student ID reading parameters ---
    id_num_digits: int = 8
    id_bubbles_ul_frac: Tuple[float, float] = (0.41, 0.047) 
    id_bubbles_lr_frac: Tuple[float, float] = (0.784, 0.274)
    id_bubbles_internal_margin_frac: Tuple[float, float] = (0.02, 0.01)  # margin inside the bubble area box

    id_digits_ul_frac: Tuple[float, float] = (0.428, 0.0265)
    id_digits_lr_frac: Tuple[float, float] = (0.772, 0.0514)
    id_digits_gap_size_frac: float = 0.0300  # gap between cells as fraction of box width
    id_digits_cell_margin_frac: float = 0.06  # margin inside each cell for OCR crop
    id_ocr_upsample_factor: float = 3.0   # scale factor for resizing
    id_ocr_dilate: bool = True            # whether to dilate strokes a bit
    id_ocr_confidence_threshold: float = 0.7  # min confidence to accept OCR result
    # --- Bubble overlay parameters ---
    overlay_correct_choice_color: Tuple[int, int, int] = (0, 255, 0)  # green
    overlay_incorrect_choice_color: Tuple[int, int, int] = (0, 0, 255)  # red

    # --- Student ID echo overlay parameters ---
    id_echo_textbox: TextBoxConfig = field(default_factory=lambda: TextBoxConfig(
        box_origin_x_frac=0.2,
        box_origin_y_frac=0.69,
        background_color=(77, 41, 7),  # black
        background_alpha=0.25,  # semi-transparent
        text_color=(25, 230, 255),  # yellow
        text_scale=2.5,
        text_thickness=4,
        box_margin_frac=0.04,  # margin inside box
    ))

    score_textbox: TextBoxConfig = field(default_factory=lambda: TextBoxConfig(
        box_origin_x_frac=0.2,
        box_origin_y_frac=0.75,
        background_color=(77, 41, 7),  # black
        background_alpha=0.25,  # semi-transparent
        text_color=(255, 255, 255),  # white
        text_scale=2.5,
        text_thickness=4,
        box_margin_frac=0.04,  # margin inside box
    ))

class AnswerSheetGenerator:
    def __init__(self, layout_config: LayoutConfig, question_list: Optional[List[dict]] = None):
        self.layout_config = layout_config
        self.question_list = question_list

    def _place_indicials_tex(self) -> str:
        config = self.layout_config
        sep = config.indicial_sep
        east_shift = config.indicial_east_shift
        west_shift = config.indicial_west_shift
        north_shift = config.indicial_north_shift
        south_shift = config.indicial_south_shift
        lines: list[str] = []
        lines.append(r"\begin{tikzpicture}[remember picture,overlay]")
        lines.append(
            rf"\node[fill=black,circle,inner sep={sep},"
            f"xshift={west_shift},yshift={north_shift}] at (current page.north west)"
            r" {};"
        )

        lines.append(
            rf"\node[fill=black,circle,inner sep={sep},"
            f"xshift={east_shift},yshift={north_shift}] at (current page.north east)"
            r" {};"
        )
        lines.append(
            rf"\node[fill=black,circle,inner sep={sep},"
            f"xshift={west_shift},yshift={south_shift}] at (current page.south west)"
            r" {};"
        )
        lines.append(
            rf"\node[fill=black,circle,inner sep={sep},"
            f"xshift={east_shift},yshift={south_shift}] at (current page.south east)"
            r" {};"
        )
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)

    def _place_bubbles_tex(self) -> str:
        config = self.layout_config
        num_questions = config.num_questions
        num_cols = config.num_cols
        rows_per_block = config.rows_per_block
        tabcolsep = config.tabcolsep
        arraystretch = config.arraystretch
        choice_keys = list(config.choice_keys)
        if choice_keys is None or not choice_keys:
            choice_keys = ["a", "b", "c", "d"]

        choice_keys = sorted(choice_keys)

        lines: list[str] = []

        lines.append(r"\begin{small}")                # or \footnotesize if needed
        lines.append(rf"\setlength{{\tabcolsep}}{{{tabcolsep}}}")  # horizontal padding
        lines.append(rf"\renewcommand{{\arraystretch}}{{{arraystretch}}}")  # vertical tightness
        lines.append(r"\begin{center}")

        # questions are ordered column-wise and grouped into blocks of rows_per_block that cannot be broken except in the very last block of the very last column
        # so rows must be a multiple of rows_per_block, and there may be empty rows in the last column
        # padded number of questions is the smallest multiple of (num_cols * rows_per_block) >= num_questions
        total_rows = ((num_questions + num_cols * rows_per_block - 1) // (num_cols * rows_per_block)) * rows_per_block

        col_spec = rf" @{{\hspace{{{config.majorcolsep}}}}} ".join(["r l"] * num_cols)
        lines.append(rf"\begin{{tabular}}{{{col_spec}}}")

        for r in range(total_rows):
            cell_tex_parts = []

            for c in range(num_cols):
                qnum = r + c * total_rows + 1
                if qnum <= num_questions:
                    if self.question_list is not None:
                        question = self.question_list[qnum - 1]
                        # Render the question using the provided renderer
                        question_type = question.get("type", "mcq").lower()
                        if question_type == "mcq":
                            choice_keys = [str(choice.get("key", "")).strip() for choice in question.get("choices", []) if choice.get("key", "") not in (None, "")]
                            if not choice_keys:
                                choice_keys = ["a", "b", "c", "d"]
                            choice_keys = sorted(choice_keys)
                        elif question_type == "tf":
                            choice_keys = ["T", "F"]
                        else:
                            choice_keys = ["a", "b", "c", "d"]
                        logger.debug(f"Rendering bubbles for question {qnum} (id: {question.get('id', 'N/A')}): {question_type}")
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
            if (r + 1) % rows_per_block == 0 and (r + 1) < total_rows:
                row_tex += rf" \\[{config.majorrowsep}]"
            else:
                row_tex += rf" \\[{config.intrarowsep}]"

            lines.append(row_tex)

        lines.append(r"\end{tabular}")
        lines.append(r"\end{center}")
        lines.append(r"\end{small}")
        lines.append(r"\restoregeometry")

        return "\n".join(lines)

    def generate_tex_full(self):
        pass

    def generate_tex(self,
        instructions: str = "",
    ) -> str:
        """
        Build a LaTeX answer sheet using \\circledletter for each choice.

        - num_questions: total number of questions in the exam
        - choice_keys: list of choice labels (e.g., ["a","b","c","d"]).
        """
        config = self.layout_config
        choice_keys = list(config.choice_keys)
        if choice_keys is None or not choice_keys:
            choice_keys = ["a", "b", "c", "d"]

        choice_keys = sorted(choice_keys)

        lines: list[str] = []
        lines.append(r"\thispagestyle{answersheet}")        
        lines.append(rf"\newgeometry{{top={config.page_top_margin_in}in,bottom={config.page_bottom_margin_in}in,left={config.page_left_margin_in}in,right={config.page_right_margin_in}in}}")

        # indicial markers in four corners (slightly inset)
        lines.append(self._place_indicials_tex())
        # Version + QR again on answer sheet page:
        lines.extend((r"\noindent " + instructions).splitlines())
        # Compact table settings
        lines.append(self._place_bubbles_tex())
        lines.append("")

        return "\n".join(lines)
