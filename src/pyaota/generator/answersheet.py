# Author: Cameron F. Abrams, <cfa22@drexel.edu>

from typing import Dict, List, Tuple, Sequence, Optional, Any
import cv2
import numpy as np
import math
from pathlib import Path
import logging
from dataclasses import dataclass, field
import pint

_ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit = True)

# make a custom unit for pixel (300 per inch)
_ureg.define('pxl = inch / 300 = [length]')
# pixel quantities must be integers
# monkey-patch pint's Quantity to enforce integer pixels
@property
def pxls(self) -> int:
    if not self.check('[length]'):
        raise AttributeError("pixels property only valid for length quantities")
    px_value = self.to(_ureg.pxl).magnitude
    return int(round(px_value))

_ureg.Quantity.pxls = pxls

_ureg.define('texpt = inch / 72.27 = pt_tex')
def define_em(font_size_pt: int = 10) -> None:
    _ureg.define(f'em = {font_size_pt} * texpt')

define_em(11)  # default 11pt font size

logger = logging.getLogger(__name__)
# ---------------- Layout configuration ----------------

@dataclass
class LayoutConfig:
    num_questions: int  # must be provided
    student_id_num_digits: int = 8

    choice_keys: Sequence[str] = ("a", "b", "c", "d")
    tf_keys: Sequence[str] = ("T", "F")

    # Radius of sampling region as fraction of min(width, height)
    bubble_radius: pint.Quantity = 24 * _ureg.pxl
    bubble_text_height: pint.Quantity = 3.1 * _ureg.mm
    bubble_text_depth: pint.Quantity = 0.9 * _ureg.mm
    # must be the case that 2*radius >= text_height + text_depth for radius to matter

    # Darkness threshold to call a bubble filled
    fill_ratio_threshold: float = 0.20

    # runner up margin (relative) to call a bubble filled
    runner_up_margin: float = 0.09

    # latex lengths for margins
    page_top_margin: pint.Quantity = 1.0 * _ureg.inch
    page_bottom_margin: pint.Quantity = 1.0 * _ureg.inch
    page_left_margin: pint.Quantity = 1.0 * _ureg.inch
    page_right_margin: pint.Quantity = 1.0 * _ureg.inch

    canonical_width: pint.Quantity = 8.5 * _ureg.inch
    canonical_height: pint.Quantity = 11.0 * _ureg.inch

    # indicial shifts
    indicial_sep: pint.Quantity = 0.5 * _ureg.mm  # radius of indicial dots
    indicial_east_offset: pint.Quantity = -1.0 * _ureg.cm
    indicial_west_offset: pint.Quantity = 1.0 * _ureg.cm
    indicial_north_offset: pint.Quantity = -2.7 * _ureg.cm
    indicial_south_offset: pint.Quantity = 1.0 * _ureg.cm

    indicial_nw_location: Tuple[pint.Quantity, pint.Quantity] = (indicial_west_offset, -indicial_north_offset)
    indicial_ne_location: Tuple[pint.Quantity, pint.Quantity] = (canonical_width + indicial_east_offset, -indicial_north_offset)
    indicial_sw_location: Tuple[pint.Quantity, pint.Quantity] = (indicial_west_offset, canonical_height - indicial_south_offset)
    indicial_se_location: Tuple[pint.Quantity, pint.Quantity] = (canonical_width + indicial_east_offset, canonical_height - indicial_south_offset)

    # Search region specifications (as fractions of image dimensions from each corner)
    # Format: (width_fraction, height_fraction) - how far from corner to search
    indicial_search_nw: Tuple[float, float] = (0.12, 0.15)  # Search top-left 10% width, 10% height
    indicial_search_ne: Tuple[float, float] = (0.12, 0.15)  # Search top-right 10% width, 10% height
    indicial_search_sw: Tuple[float, float] = (0.12, 0.10)  # Search bottom-left 10% width, 10% height
    indicial_search_se: Tuple[float, float] = (0.12, 0.10)  # Search bottom-right 10% width, 10% height
    # Search region specifications (as fractions of image dimensions from each corner)
    def get_indicial_search_regions(self, img_shape):
        """
        Get pixel-based search regions for locating indicials in raw image.
        
        Args:
            img_shape: (height, width) of the image
            
        Returns:
            dict with keys 'nw', 'ne', 'sw', 'se', each containing (x1, y1, x2, y2)
        """
        h, w = img_shape[:2]
        
        # NW: top-left corner
        nw_w = int(w * self.indicial_search_nw[0])
        nw_h = int(h * self.indicial_search_nw[1])
        nw_region = (0, 0, nw_w, nw_h)
        
        # NE: top-right corner
        ne_w = int(w * self.indicial_search_ne[0])
        ne_h = int(h * self.indicial_search_ne[1])
        ne_region = (w - ne_w, 0, w, ne_h)
        
        # SW: bottom-left corner
        sw_w = int(w * self.indicial_search_sw[0])
        sw_h = int(h * self.indicial_search_sw[1])
        sw_region = (0, h - sw_h, sw_w, h)
        
        # SE: bottom-right corner
        se_w = int(w * self.indicial_search_se[0])
        se_h = int(h * self.indicial_search_se[1])
        se_region = (w - se_w, h - se_h, w, h)
        
        return {
            'nw': nw_region,
            'ne': ne_region,
            'sw': sw_region,
            'se': se_region
        }

    name_blank_ul: Tuple[pint.Quantity, pint.Quantity] = (1.75 * _ureg.inch, 1.25 * _ureg.inch)
    name_blank_size: Tuple[pint.Quantity, pint.Quantity] = (5.5 * _ureg.inch, 0.3 * _ureg.inch)

    student_id_digit_boxes_ul: Tuple[pint.Quantity, pint.Quantity] = (2.25 * _ureg.inch, 1.4 * _ureg.inch)
    student_id_digit_boxes_box_size: Tuple[pint.Quantity, pint.Quantity] = (100 * _ureg.pxl, 100 * _ureg.pxl)
    student_id_digit_boxes_horiz_gap: pint.Quantity = 33 * _ureg.pxl
    student_id_ocr_confidence_threshold: float = 0.7
    student_id_digits_cell_margin_frac: float = 0.06  # margin inside each cell for OCR crop
    bubble_column_vert_gap: pint.Quantity = 12 * _ureg.pxl  # vertical gap between bubble centers in a column

    qr_ul: Tuple[pint.Quantity, pint.Quantity] = (6.5 * _ureg.inch, 2.5 * _ureg.inch)
    qr_size: pint.Quantity = 1.5 * _ureg.cm

    warning_line_opacity: float = 0.75

    overlay_correct_choice_color: Tuple[int, int, int] = (0, 255, 0)  # green
    overlay_incorrect_choice_color: Tuple[int, int, int] = (0, 0, 255)  # red

    bubble_field_num_questions_per_block: int = 5 # number of questions per block (vertical)
    bubble_field_num_cols: int = 3

    bubble_field_ul: Tuple[pint.Quantity, pint.Quantity] = (2 * _ureg.inch, 4.6 * _ureg.inch)
    bubble_field_block_gap: Tuple[pint.Quantity, pint.Quantity] = (1.25 * _ureg.cm, 1 * _ureg.cm)
    intrablock_row_gap: pint.Quantity = 60 * _ureg.pxl
    intrablock_choice_gap: pint.Quantity = 10 * _ureg.pxl
    intrablock_numbering_gap: pint.Quantity = 30 * _ureg.pxl

class AnswerSheetGenerator:
    def __init__(self, layout_config: LayoutConfig, question_list: Optional[List[dict]] = None):
        self.layout_config = layout_config
        self.question_list = question_list

    def _place_indicials_tex(self) -> str:
        config = self.layout_config
        sep = config.indicial_sep.to(_ureg.pt_tex).magnitude
        east_shift = config.indicial_east_offset.to(_ureg.pt_tex).magnitude
        west_shift = config.indicial_west_offset.to(_ureg.pt_tex).magnitude
        north_shift = config.indicial_north_offset.to(_ureg.pt_tex).magnitude
        south_shift = config.indicial_south_offset.to(_ureg.pt_tex).magnitude
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

    def _place_name_blank(self) -> str:
        # use tikz to draw a line for the name blank, with a "Name: " label
        # the tikz picture is overlayed on the page at absolute positions
        config = self.layout_config
        ul_x = config.name_blank_ul[0].to(_ureg.inch).magnitude
        ul_y = -config.name_blank_ul[1].to(_ureg.inch).magnitude
        width = config.name_blank_size[0].to(_ureg.inch).magnitude
        lines: list[str] = []
        lines.append(r"\begin{tikzpicture}[remember picture,overlay,shift={(current page.north west)}]")
        lines.append(
            rf"\draw[line width=0.4pt] "
            f"({ul_x}in, {ul_y}in) -- ({ul_x + width}in, {ul_y}in);"
        )
        label_x = ul_x - 0.1
        label_y = ul_y + 0.075
        lines.append(
            rf"\node[anchor=east] at ({label_x}in, {label_y}in) "
            r" {\textbf{Name:}};"
        )
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)

    def _place_student_id_boxes(self) -> str:
        config = self.layout_config
        ul_x = config.student_id_digit_boxes_ul[0].to(_ureg.cm).magnitude
        ul_y = -config.student_id_digit_boxes_ul[1].to(_ureg.cm).magnitude
        box_width = config.student_id_digit_boxes_box_size[0].to(_ureg.cm).magnitude
        box_height = config.student_id_digit_boxes_box_size[1].to(_ureg.cm).magnitude
        gap = config.student_id_digit_boxes_horiz_gap.to(_ureg.cm).magnitude
        vgap = config.bubble_column_vert_gap.to(_ureg.cm).magnitude
        bubble_radius = config.bubble_radius.to(_ureg.cm).magnitude
        bubble_text_height = config.bubble_text_height.to(_ureg.cm).magnitude
        bubble_text_depth = config.bubble_text_depth.to(_ureg.cm).magnitude

        lines: list[str] = []
        lines.append(r"\begin{tikzpicture}[remember picture,overlay,shift={(current page.north west)}]")
        lines.append(rf'\pgfmathsetmacro{{\radius}}{{{bubble_radius}}}')
        lines.append(r'\foreach \i in {1,...,'+f'{config.student_id_num_digits}'+r'} {')
        lines.append(rf'    \pgfmathsetmacro{{\xpos}}{{{ul_x} + (\i - 1)*({gap}+{box_width})}}')
        lines.append(rf'    \pgfmathsetmacro{{\ypos}}{{{ul_y}}}')
        logger.debug(f'Debug: ul_x={(ul_x*_ureg.cm).to("pxl")}, ul_y={(ul_y*_ureg.cm).to("pxl")}, box_width={(box_width*_ureg.cm).to("pxl")}, box_height={(box_height*_ureg.cm).to("pxl")}, gap={(gap*_ureg.cm).to("pxl")}, vgap={(vgap*_ureg.cm).to("pxl")}, bubble_radius={(bubble_radius*_ureg.cm).to("pxl")}')
        lines.append(rf'  \node[draw, anchor=north west, minimum width={box_width}cm, minimum height={box_height}cm] (box) at (\xpos cm, \ypos cm) {{}};')
        lines.append(r'}')
        lines.append(r'\foreach \i in {1,...,'+f'{config.student_id_num_digits}'+r'} {')
        lines.append(rf' \pgfmathsetmacro{{\xpos}}{{{ul_x} + (\i - 1)*({gap}+{box_width}) + 0.5*{box_width}}}')
        lines.append(r'  \foreach \j in {0,...,9} {')
        lines.append(rf'    \pgfmathsetmacro{{\spacing}}{{2*\radius + {vgap}}}')
        lines.append(rf'    \pgfmathsetmacro{{\ypos}}{{{ul_y} - {box_height} - {vgap} - {bubble_radius} - \spacing * \j}}')
        lines.append(rf'    \node[circle,draw,inner sep=0pt,minimum size=2*\radius cm,font=\footnotesize,text height={bubble_text_height}cm,text depth={bubble_text_depth}cm,anchor=center] at (\xpos cm, \ypos cm) {{\textcolor{{bubblegray}}{{\j}}}};')
        lines.append(r'  }')
        lines.append(r'}')
        # place the label "Student ID:" to the left of the boxes
        main_label_x = ul_x - (0.1*_ureg.inch).to(_ureg.cm).magnitude
        main_label_y = ul_y - box_height / 2
        sub_label_x = main_label_x + 0.25
        sub_label_y = main_label_y - 4.5 * (2*bubble_radius + vgap)
        lines.append(r'\node[anchor=east] at ('+f'{main_label_x}cm, {main_label_y}cm'+r') {\textbf{Student ID:}};')
        # place the label "Fill in bubbles for each digit" to the left of the bubbles
        lines.append(r'\node[anchor=east,font=\footnotesize] at ('+f'{sub_label_x}cm, {sub_label_y}cm'+r') {Fill in the bubble};')
        lines.append(r'\node[anchor=east,font=\footnotesize] at ('+f'{sub_label_x}cm, {sub_label_y-0.4}cm'+r') {for each digit};')
        lines.append(r'\node[anchor=east,font=\footnotesize] at ('+f'{sub_label_x}cm, {sub_label_y-0.8}cm'+r') {of your ID:};')
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)

    def _place_qr_code(self, version_label: str = "") -> str:
        config = self.layout_config
        opacity = config.warning_line_opacity
        ul_x = config.qr_ul[0].to(_ureg.cm).magnitude
        ul_y = -config.qr_ul[1].to(_ureg.cm).magnitude
        size = config.qr_size.to(_ureg.cm).magnitude
        bb_ul_x = ul_x - 0.2
        bb_ul_y = ul_y + 0.2
        bb_w = size + 0.4
        bb_h = size + 0.4

        lines: list[str] = []
        lines.append(r"\begin{tikzpicture}[remember picture,overlay,shift={(current page.north west)}]")
        # draw bounding box
        lines.append(
            rf"\draw[line width=0.4pt,opacity={opacity}] "
            f"({bb_ul_x}cm, {bb_ul_y}cm) rectangle ({bb_ul_x + bb_w}cm, {bb_ul_y - bb_h}cm);"
        )
        lines.append(
            rf"\node at ({ul_x + size/2}cm, {ul_y - size/2}cm) "
            rf"{{\qrcode[height={size}cm]{{{version_label}}}}};"
        )
        # add warning text below the QR code
        lines.append(
            rf"\node[anchor=north,opacity={opacity}] at ({ul_x + size/2}cm, {ul_y + 0.6}cm) "
            r" {\footnotesize \textit{Make no marks}};"
            rf"\node[anchor=north,opacity={opacity}] at ({ul_x + size/2}cm, {ul_y - size - 0.1}cm) "
            r" {\footnotesize \textit{in this box}};"
        )
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)

    def _place_bubblefield(self) -> str:
        config = self.layout_config
        field_ul = config.bubble_field_ul[0].to(_ureg.cm).magnitude, config.bubble_field_ul[1].to(_ureg.cm).magnitude
        logger.debug(f'field_ul={(field_ul[0]*_ureg.cm).to("pxl")}, {(field_ul[1]*_ureg.cm).to("pxl")}')
        blocksize = config.bubble_field_num_questions_per_block
        block_gap = config.bubble_field_block_gap[0].to(_ureg.cm).magnitude, config.bubble_field_block_gap[1].to(_ureg.cm).magnitude
        num_cols = config.bubble_field_num_cols
        block_row_gap = config.intrablock_row_gap.to(_ureg.cm).magnitude
        block_choice_gap = config.intrablock_choice_gap.to(_ureg.cm).magnitude
        block_numbering_gap = config.intrablock_numbering_gap.to(_ureg.cm).magnitude
        bubble_radius = config.bubble_radius.to(_ureg.cm).magnitude
        bubble_text_height = config.bubble_text_height.to(_ureg.cm).magnitude
        bubble_text_depth = config.bubble_text_depth.to(_ureg.cm).magnitude

        num_questions = config.num_questions
        assert num_questions == len(self.question_list) if self.question_list is not None else True, f'num_questions {num_questions} != len(question_list) {len(self.question_list) if self.question_list is not None else "None"}'
        choice_keys = {'mcq': ["a", "b", "c", "d"], 'tf': ["T", "F"]}

        lines: list[str] = []
        opacity = config.warning_line_opacity

        n_whole_blocks = num_questions // blocksize
        n_partial_block = 1 if (num_questions % blocksize) > 0 else 0
        size_partial_block = num_questions % blocksize if n_partial_block == 1 else 0
        total_blocks = n_whole_blocks + n_partial_block

        logger.debug(f'num_questions={num_questions}, n_whole_blocks={n_whole_blocks}, n_partial_block={n_partial_block}, size_partial_block={size_partial_block}, total_blocks={total_blocks}')

        # 60 questions = 12 blocks, 3 columns = 4 blocks per column

        n_blocks_per_column = total_blocks // num_cols
        remainder_blocks = total_blocks % num_cols
        total_columns = total_blocks // n_blocks_per_column + (1 if remainder_blocks > 0 else 0)
        logger.debug(f'num_cols={num_cols}, n_blocks_per_column={n_blocks_per_column}, total_columns={total_columns}')
        size_partial_column = remainder_blocks
        assert total_columns == num_cols, f' total_columns {total_columns} != num_cols {num_cols} '

        max_len_choice_keys = max(len(v) for v in choice_keys.values())

        lines.append(r"\begin{tikzpicture}[remember picture,overlay,shift={(current page.north west)}]")
        lines.append(rf'\pgfmathsetmacro{{\radius}}{{{bubble_radius}}}')
        qidx = 0
        for col in range(total_columns):
            x_col = field_ul[0] + col * (block_numbering_gap + (block_choice_gap + bubble_radius * 2) * max_len_choice_keys + block_gap[0])
            for block in range(n_blocks_per_column):
                y_block_start = field_ul[1] + block * (block_row_gap * blocksize + block_gap[1])
                for row in range(blocksize):
                    q = self.question_list[qidx]
                    qtyp = q.get("type", "mcq").lower()
                    # choice_keys[qtyp] = sorted(choice_keys.get(qtyp, ["a", "b", "c", "d"]))
                    qnum = qidx + 1
                    # compute south west corner of the question's bubble row
                    y_base = y_block_start + row * block_row_gap
                    logger.debug(f'qidx={qidx}, qnum={qnum}, qtyp={qtyp}, x_col={(x_col*_ureg.cm).to("pxl")}, y_base={(y_base*_ureg.cm).to("pxl")}')
                    lines.append(rf'\node[anchor=east] at ({x_col}cm, -{y_base}cm){{\textbf{{{qnum}.}}}};')
                    # place bubbles for this question
                    x_choices = x_col + config.intrablock_numbering_gap.to(_ureg.cm).magnitude
                    for i, key in enumerate(choice_keys[qtyp]):
                        x_bubble = x_choices + (i) * ((block_choice_gap + bubble_radius * 2))
                        lines.append(rf'\node[circle,draw,inner sep=0pt,minimum size=2*\radius cm,font=\footnotesize,text height={bubble_text_height}cm,text depth={bubble_text_depth}cm,anchor=center] at ({x_bubble}cm, -{y_base}cm) {{\textcolor{{bubblegray}}{{{key}}}}};')
                    qidx += 1
                    if qidx >= num_questions:
                        break
        lines.append(r"\end{tikzpicture}")

        return "\n".join(lines)

    def _place_boundary_warnings(self) -> str:
        # vertical line just to right of western indicials
        config = self.layout_config
        opacity = config.warning_line_opacity
        lines: list[str] = []
        west_x = config.indicial_west_offset + config.indicial_sep + 0.5 * _ureg.cm
        east_x = config.canonical_width + config.indicial_east_offset - config.indicial_sep - 0.5 * _ureg.cm
        top_y = config.indicial_north_offset + 0.75 * _ureg.cm
        bottom_y = -config.canonical_height + config.indicial_south_offset + config.indicial_sep + 0.5 * _ureg.cm
        lines.append(r"\begin{tikzpicture}[remember picture,overlay,shift={(current page.north west)}]")
        # left vertical line
        lines.append(
            rf"\draw[line width=0.4pt,opacity={opacity}] "
            f"({west_x.to(_ureg.cm).magnitude}cm, {top_y.to(_ureg.cm).magnitude}cm) -- "
            f"({west_x.to(_ureg.cm).magnitude}cm, {bottom_y.to(_ureg.cm).magnitude}cm);"
        )
        # right vertical line
        lines.append(
            rf"\draw[line width=0.4pt,opacity={opacity}] "
            f"({east_x.to(_ureg.cm).magnitude}cm, {top_y.to(_ureg.cm).magnitude}cm) -- "
            f"({east_x.to(_ureg.cm).magnitude}cm, {bottom_y.to(_ureg.cm).magnitude}cm);"
        )
        # top horizontal line
        lines.append(
            rf"\draw[line width=0.4pt,opacity={opacity}] "
            f"({west_x.to(_ureg.cm).magnitude}cm, {top_y.to(_ureg.cm).magnitude}cm) -- "
            f"({east_x.to(_ureg.cm).magnitude}cm, {top_y.to(_ureg.cm).magnitude}cm);"
        )
        # bottom horizontal line
        lines.append(
            rf"\draw[line width=0.4pt,opacity={opacity}] "
            f"({west_x.to(_ureg.cm).magnitude}cm, {bottom_y.to(_ureg.cm).magnitude}cm) -- "
            f"({east_x.to(_ureg.cm).magnitude}cm, {bottom_y.to(_ureg.cm).magnitude}cm);"
        )
        # write messages near each line
        lines.append(
            rf"\node[anchor=east,font=\footnotesize,rotate=90,opacity={opacity}] at "
            f"({west_x.to(_ureg.cm).magnitude - 0.4}cm, "
            f"{(0.5*(top_y+bottom_y)).to(_ureg.cm).magnitude}cm) "
            r" {Make no marks in the margins};"
        )
        lines.append(
            rf"\node[anchor=west,font=\footnotesize,rotate=270,opacity={opacity}] at "
            f"({east_x.to(_ureg.cm).magnitude + 0.4}cm, "
            f"{(0.5*(top_y+bottom_y)).to(_ureg.cm).magnitude}cm) "
            r" {Make no marks in the margins};"
        )
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)

    def generate_tex_full(self):
        pass

    def generate_tex(self,
        version_label: str = "",
    ) -> str:
        config = self.layout_config
        top = config.page_top_margin.to(_ureg.inch).magnitude
        bottom = config.page_bottom_margin.to(_ureg.inch).magnitude
        left = config.page_left_margin.to(_ureg.inch).magnitude
        right = config.page_right_margin.to(_ureg.inch).magnitude

        lines: list[str] = []
        lines.append(r"\thispagestyle{answersheet}")
        lines.append(rf"\newgeometry{{top={top}in,bottom={bottom}in,left={left}in,right={right}in}}")

        lines.append(self._place_indicials_tex())
        lines.append(self._place_name_blank())
        lines.append(self._place_student_id_boxes())
        lines.append(self._place_qr_code(version_label=version_label))
        lines.append(self._place_bubblefield())
        lines.append(self._place_boundary_warnings())

        return "\n".join(lines)
