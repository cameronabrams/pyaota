from pathlib import Path
from ..generator.answersheet import LayoutConfig, _ureg
# from ..ocr.digit_ocr import ocr_digit_nn, load_digit_model
from ..image.warper import warp
from typing import Any, Dict, Tuple, List, Optional
import numpy as np
import cv2
import logging
import sys
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

def x_marks_the_spot(image, x_px, y_px):
    cv2.line(
        image,
        (x_px - 10, y_px - 10),
        (x_px + 10, y_px + 10),
        (0, 0, 255),
        2
    )
    cv2.line(
        image,
        (x_px - 10, y_px + 10),
        (x_px + 10, y_px - 10),
        (0, 0, 255),
        2
    )

# def get_centered_padded_digit(img_gray: np.ndarray, pad: int = 10) -> np.ndarray:
#     """
#     Takes a grayscale digit image, finds the ink bounding box,
#     centers the digit in a new image, and adds uniform padding.
    
#     Returns a new grayscale image.
#     """

#     # Ensure grayscale
#     if img_gray.ndim == 3:
#         img_gray = cv2.cvtColor(img_gray, cv2.COLOR_BGR2GRAY)

#     # Threshold to get binary ink mask (digit in black or white)
#     _, th = cv2.threshold(
#         img_gray, 0, 255,
#         cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
#     )
#     # Now digit strokes are white (255), background black (0)

#     # Find bounding box of the white pixels
#     ys, xs = np.where(th > 0)  # coordinates where ink exists
#     if len(xs) == 0 or len(ys) == 0:
#         # no ink found ― return padded blank image
#         h, w = img_gray.shape
#         return 255 * np.ones((h + 2*pad, w + 2*pad), dtype=np.uint8)

#     x_min, x_max = xs.min(), xs.max()
#     y_min, y_max = ys.min(), ys.max()

#     # Crop to bounding box
#     cropped = img_gray[y_min:y_max+1, x_min:x_max+1]

#     # Create padded new image
#     new_h = (y_max - y_min + 1) + 2 * pad
#     new_w = (x_max - x_min + 1) + 2 * pad

#     canvas = 255 * np.ones((new_h, new_w), dtype=np.uint8)  # white background

#     # Paste the Cropped digit in the center
#     canvas[pad:pad + cropped.shape[0], pad:pad + cropped.shape[1]] = cropped

#     return canvas

# # Optionally load global model once if you like
# _DIGIT_MODEL = None

# def get_digit_model():
#     global _DIGIT_MODEL
#     if _DIGIT_MODEL is None:
#         _DIGIT_MODEL = load_digit_model()
#     return _DIGIT_MODEL

class AnswerSheetReader:
    def __init__(self, img: np.ndarray, layout_config: LayoutConfig, debug_output_dir: Path = Path("debug"), interactive: bool = False):
        self.rawimg = img.copy()
        self.img_original = img.copy()
        self.working_image = None
        self.original_size = img.shape[:2]  # (height, width)
        self.layout_config = layout_config
        self.debug_output_path = debug_output_dir
        self.interactive = interactive
        self.results = {}
        self.diagnostics = {'original_size': img.shape[:2]}  # (height, width)
        self.diagnostics['debug_image'] = None # we'll save the warped image here
        self.diagnostics['indicial_search_image'] = img.copy()
        if not self.debug_output_path.exists():
            self.debug_output_path.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, Any]:
        self.img_original = self.rawimg.copy()
        self.working_image = self.rawimg.copy()

        steps = [
            ("find_indicials", self._right_size, self._find_indicials),
            ("warp", None, self._warp_to_canonical),
            ("read_qr", None, self._read_qr),
            ("read_student_id", None, self._read_student_id),
            ("read_bubblefield", None, self._read_bubblefield),
        ]

        for step_name, pre, action in steps:
            try:
                if pre is not None:
                    pre()
                action()
            except Exception as exc:
                self.results["read_status"] = f"failed_{step_name}"
                self.results["read_error"] = str(exc)
                logger.warning(f"AnswerSheetReader: step '{step_name}' failed — {exc}")
                break
        else:
            self.results["read_status"] = "success"

        if self.diagnostics.get('debug_image') is not None:
            debug_img_path = self.debug_output_path / f"debug_overlay_warped.png"
            cv2.imwrite(str(debug_img_path), self.diagnostics['debug_image'])
        return self.results

    def _right_size(self):
        """
        resize the working image to the canonical page size
        """
        config = self.layout_config
        CANONICAL_PAGE_WIDTH = int(config.canonical_width.to('pxl').magnitude)
        CANONICAL_PAGE_HEIGHT = int(config.canonical_height.to('pxl').magnitude)
        self.working_image = cv2.resize(
            self.working_image,
            (CANONICAL_PAGE_WIDTH, CANONICAL_PAGE_HEIGHT),
            interpolation=cv2.INTER_LINEAR
        )
        # write this resized image
        diag_img_path = self.debug_output_path / "resized_page.png"
        cv2.imwrite(str(diag_img_path), self.working_image)
        
    def _find_indicials(self) -> Dict[str, Tuple[int, int]]:
        """
        Detect indicial markers in the four corners of the answer sheet image.

        Returns a dictionary mapping corner names ('nw', 'ne', 'sw', 'se') to
        (x, y) pixel coordinates of the detected indicials.

        Raises RuntimeError if any indicial cannot be found.
        """
        config = self.layout_config
        img = self.working_image.copy()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Light background, dark dots/text → invert for contour detection
        _, bin_inv = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        h, w = img.shape[:2]
        logger.debug(f"Image size for indicial detection: width={w}, height={h}")
        
        # Expected indicial radius in pixels (approximate, for validation)
        expected_radius_px = config.indicial_sep.to('pxl').magnitude
        min_radius = expected_radius_px * 0.5  # Allow 50% smaller
        max_radius = expected_radius_px * 2.0  # Allow 2x larger
        min_area = np.pi * min_radius**2
        max_area = np.pi * max_radius**2
        
        search_regions = config.get_indicial_search_regions(img.shape[:2])
        self.diagnostics['indicial_search_regions'] = search_regions
        
        logger.debug(f'Indicial search regions (pixels): {search_regions}')

        indicials = {}
        
        self.diagnostics['debug_image'] = img.copy()
        for corner, (x1, y1, x2, y2) in search_regions.items():
            # draw the search region on diagnostic image
            if self.diagnostics.get('debug_image') is not None:
                cv2.rectangle(self.diagnostics['debug_image'], (x1, y1), (x2, y2), (255, 0, 0), 2)
        diag_img_path = self.debug_output_path / "indicial_search_regions.png"
        cv2.imwrite(str(diag_img_path), self.diagnostics['debug_image'])

        for corner, (x1, y1, x2, y2) in search_regions.items():
            logger.debug(f"Indicial search region {corner}: ({x1}, {y1}) to ({x2}, {y2})")
            # Extract search region
            sub = bin_inv[y1:y2, x1:x2]
            
            # Find contours
            contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find the best circular blob
            best_blob = None
            best_circularity = 0
            
            for cnt in contours:
                area = cv2.contourArea(cnt)
                
                # Filter by area
                if area < min_area or area > max_area:
                    continue
                
                # Check circularity
                perimeter = cv2.arcLength(cnt, True)
                if perimeter == 0:
                    continue
                
                circularity = 4 * np.pi * area / (perimeter ** 2)
                
                # Good circles have circularity close to 1.0
                if circularity > 0.7 and circularity > best_circularity:
                    best_circularity = circularity
                    best_blob = cnt
            
            if best_blob is None:
                raise RuntimeError(f"Could not find indicial in {corner} corner")
            
            # Get centroid of the blob
            M = cv2.moments(best_blob)
            if M['m00'] == 0:
                raise RuntimeError(f"Invalid indicial detected in {corner} corner")
            
            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])
            
            # Convert to global image coordinates
            global_x = x1 + cx
            global_y = y1 + cy
            
            indicials[corner] = (global_x, global_y)
            logger.debug(f"Found {corner} indicial at ({global_x}, {global_y}), circularity={best_circularity:.3f}")
            
            # Optional: draw on diagnostic image
            if self.diagnostics.get('indicial_search_image') is not None:
                cv2.circle(self.diagnostics['indicial_search_image'], (global_x, global_y), 
                        int(expected_radius_px*2), (0, 255, 0), 4)
            # save the indicial search image
        diag_img_path = self.debug_output_path / "indicials_detected.png"
        cv2.imwrite(str(diag_img_path), self.diagnostics['indicial_search_image'])

        self.diagnostics['indicials'] = indicials
        return indicials

    def _warp_to_canonical(self):
        img = self.working_image.copy()
        indicials = self.diagnostics['indicials']

        # Source points: detected indicials in image coordinates
        (nw, ne, sw, se) = indicials['nw'], indicials['ne'], indicials['sw'], indicials['se']
        corner_indicials = np.float32([nw, ne, sw, se])
        logger.debug(f'WARP TO CANONICAL: source indicials = {corner_indicials}')
        # Destination points: known indicial positions in page coordinates (pixels)
        config = self.layout_config
        
        # Convert indicial positions from physical units to pixels
        nw_page = (
            config.indicial_nw_location[0].to('pxl').magnitude,
            config.indicial_nw_location[1].to('pxl').magnitude
        )
        ne_page = (
            config.indicial_ne_location[0].to('pxl').magnitude,
            config.indicial_ne_location[1].to('pxl').magnitude
        )
        sw_page = (
            config.indicial_sw_location[0].to('pxl').magnitude,
            config.indicial_sw_location[1].to('pxl').magnitude
        )
        se_page = (
            config.indicial_se_location[0].to('pxl').magnitude,
            config.indicial_se_location[1].to('pxl').magnitude
        )
        
        canonical_corners = np.float32([nw_page, ne_page, sw_page, se_page])

        warped = warp(
            raw_img=img,
            corner_indicials=corner_indicials,
            canonical_corners=canonical_corners,
            canonical_page_dimensions=(
                config.canonical_width.to('pxl').magnitude,
                config.canonical_height.to('pxl').magnitude
            )
        )

        self.working_image = warped
        self.diagnostics['debug_image'] = warped.copy()



        # logger.debug(f' Selected bubbles canonical positions: {selected_bubbles_canonical_positions}')

        # logger.debug(f'WARP TO CANONICAL: dest indicials = {canonical_corners}')
        # # Output size: full page dimensions in pixels
        # page_width_px = int(config.canonical_width.to('pxl').magnitude)
        # page_height_px = int(config.canonical_height.to('pxl').magnitude)
        # logger.debug(f'WARP TO CANONICAL: page size = {page_width_px} x {page_height_px} px')
        # out_w = page_width_px
        # out_h = page_height_px

        # # Compute transformation
        # M = cv2.getPerspectiveTransform(corner_indicials, canonical_corners)
        # M_inv = cv2.getPerspectiveTransform(canonical_corners, corner_indicials)
        
        # # Apply warp
        # warped = cv2.warpPerspective(img, M, (out_w, out_h))
        
        # self.img = warped
        debug_img_path = self.debug_output_path / "warped_page.png"
        cv2.imwrite(str(debug_img_path), self.working_image)
        # warp the debug image as well, if present
        # if self.diagnostics.get('debug_image') is not None:
        #     debug_warped = cv2.warpPerspective(
        #         self.diagnostics['debug_image'], M, (out_w, out_h)
        #     )
        #     self.diagnostics['debug_image'] = debug_warped
        #     debug_img_path = self.debug_output_path / "indicials_warped.png"
        #     cv2.imwrite(str(debug_img_path), self.diagnostics['debug_image'])
        # self.diagnostics['warp_matrix'] = M
        # self.diagnostics['warp_matrix_inv'] = M_inv
        # self.diagnostics['warped_size'] = (out_h, out_w)

    def write_graded_annotations(self,
                    per_question_results: List[Dict[str, Any]],
                    score_fraction: float,
                    overlay_path: [Path | str],
                ):
        """
        Write an annotated overlay image showing correct/incorrect bubbles.

        Parameters
        ----------
        per_question_results : List[Dict[str, Any]]
            List of per-question result dictionaries as produced in read().
        score_fraction : float
            Overall score fraction (0.0 to 1.0).
        overlay_path : Path or str
            Path to write the overlay image to.
        """
        config = self.layout_config
        # the overlay will stay warped
        overlay_img = self.working_image.copy()
        bubble_radius_px = int(config.bubble_radius.to('pxl').magnitude*1.05)
        centers = self.diagnostics['bubbles']
        center_coords = list(centers.values())
        pts_array = np.array(center_coords, dtype=np.float32).reshape(-1, 1, 2)
        # unwrapped_center_coords = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
        bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in pts_array]
        bubble_keys = list(centers.keys())
        ambiguous_bubbles = self.diagnostics.get('ambiguous_bubbles', {})
        max_y = 0
        sum_x = 0
        for qnum in range(1, config.num_questions+1):
            q_info = per_question_results[qnum]
            correct_bubble_label = q_info["correct"]
            detected_filled_bubble_label = q_info["detected"]
            is_correct = q_info["is_correct"]
            row_centers = []
            for key in 'abcd':
                bubble_idx = bubble_keys.index((qnum, key))
                bubble_center = bubble_result_tuples[bubble_idx]
                x, y = bubble_center
                max_y = max(max_y, y)
                sum_x += x
                row_centers.append((x, y))
                if key == correct_bubble_label:
                    cv2.circle(overlay_img, (x, y), bubble_radius_px, (0, 255, 0), 3)
                elif key == detected_filled_bubble_label and not is_correct:
                    cv2.circle(overlay_img, (x, y), bubble_radius_px, (0, 0, 255), 3)
            if detected_filled_bubble_label == "?":
                xs = [c[0] for c in row_centers]
                row_y = row_centers[0][1]
                if qnum in ambiguous_bubbles:
                    # Multiple fill: red circle on each detected-filled bubble that
                    # isn't the correct answer (correct one is already green above).
                    for choice, bx, by in ambiguous_bubbles[qnum]:
                        if choice != correct_bubble_label:
                            cv2.circle(overlay_img, (bx, by), bubble_radius_px, (0, 0, 255), 3)
                # Red horizontal line for both blank and multiple-fill.
                cv2.line(
                    overlay_img,
                    (min(xs) - bubble_radius_px, row_y),
                    (max(xs) + bubble_radius_px, row_y),
                    (0, 0, 255),
                    2,
                )
        avg_x = int(sum_x / config.num_questions / 4)

        id_bubble_region = self.diagnostics.get('id_bubble_region', None)
        id_detected = self.results['student_id_bubbles'] if id_bubble_region is not None else None
        qr_crop = self.diagnostics.get('qr_crop_coords', None)
        version_detected = self.results.get('version') if qr_crop is not None else None

        # write to the path as a single-page PDF
        overlay_rgb = cv2.cvtColor(overlay_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(overlay_rgb)
        draw = ImageDraw.Draw(pil_img)

        # Load system fonts (shared across all annotations)
        large_font = small_font = None
        for fp in [
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/verdana.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        ]:
            try:
                large_font = ImageFont.truetype(fp, 90)
                small_font = ImageFont.truetype(fp, 45)
                break
            except (IOError, OSError):
                continue
        if large_font is None:
            large_font = small_font = ImageFont.load_default()

        def draw_boxed_text(text, pos, color, font, pad=10, border_width=3):
            """Draw text with a padded rectangle, anchored at pos (top-left of glyphs)."""
            bb = draw.textbbox((0, 0), text, font=font)
            tx = pos[0] - bb[0]
            ty = pos[1] - bb[1]
            draw.rectangle(
                [(tx + bb[0] - pad, ty + bb[1] - pad),
                 (tx + bb[2] + pad, ty + bb[3] + pad)],
                outline=color,
                width=border_width,
            )
            draw.text((tx, ty), text, fill=color, font=font)

        # Score box (large, centered on bubble field)
        logger.debug(f' Writing score annotation: score_fraction={score_fraction}')
        if score_fraction is not None:
            score_text = f"Score: {(score_fraction * 100):.1f}%"
            score_color = (75, 0, 130)  # dark purple
            bb = draw.textbbox((0, 0), score_text, font=large_font)
            pad = 15
            text_x = avg_x - (bb[0] + bb[2]) // 2
            text_y = max_y + 3 * bubble_radius_px - bb[1]
            draw.rectangle(
                [(text_x + bb[0] - pad, text_y + bb[1] - pad),
                 (text_x + bb[2] + pad, text_y + bb[3] + pad)],
                outline=score_color,
                width=4,
            )
            draw.text((text_x, text_y), score_text, fill=score_color, font=large_font)

        # ID box — just to the right of the digit boxes, vertically centered on those boxes
        if id_detected is not None:
            logger.debug(f' Writing ID annotation: id_detected={id_detected}')
            id_text = f"ID: {id_detected}"
            id_bb = draw.textbbox((0, 0), id_text, font=small_font)
            text_h = id_bb[3] - id_bb[1]
            box_height_px = int(config.student_id_digit_boxes_box_size[1].to('pxl').magnitude)
            box_mid_y = id_bubble_region['y0'] + box_height_px // 2
            id_x = id_bubble_region['x1'] + 20
            id_y = box_mid_y - text_h // 2
            draw_boxed_text(id_text, (id_x, id_y), (130, 130, 0), small_font)

        # Version box — centered horizontally below the QR code with padding
        if version_detected is not None:
            logger.debug(f' Writing version annotation: version_detected={version_detected}')
            ver_text = f"v {version_detected}"
            ver_bb = draw.textbbox((0, 0), ver_text, font=small_font)
            text_w = ver_bb[2] - ver_bb[0]
            text_h = ver_bb[3] - ver_bb[1]
            qr_cx = (qr_crop['x0'] + qr_crop['x1']) // 2
            ver_x = qr_cx - text_w // 2
            ver_y = qr_crop['y1'] + 60 + text_h
            draw_boxed_text(ver_text, (ver_x, ver_y), (0, 0, 139), small_font)

        pil_img.save(str(overlay_path), "PDF", resolution=300.0)
        logger.info(f'Wrote graded overlay PDF to {overlay_path}')

    def _locate_bubbles(self):
        config = self.layout_config
        
        # Convert layout positions to pixels
        field_ul_px = (
            int(config.bubble_field_ul[0].to('pxl').magnitude),
            int(config.bubble_field_ul[1].to('pxl').magnitude)
        )
        
        blocksize = config.bubble_field_num_questions_per_block
        block_gap_px = (
            int(config.bubble_field_block_gap[0].to('pxl').magnitude),
            int(config.bubble_field_block_gap[1].to('pxl').magnitude)
        )
        num_cols = config.bubble_field_num_cols
        block_row_gap_px = int(config.intrablock_row_gap.to('pxl').magnitude)
        block_choice_gap_px = int(config.intrablock_choice_gap.to('pxl').magnitude)
        block_numbering_gap_px = int(config.intrablock_numbering_gap.to('pxl').magnitude)
        bubble_radius_px = int(config.bubble_radius.to('pxl').magnitude)
        
        num_questions = config.num_questions
        choice_keys = {'mcq': ["a", "b", "c", "d"], 'tf': ["T", "F"]}
        
        # Calculate block/column layout (matches placement logic)
        n_whole_blocks = num_questions // blocksize
        n_partial_block = 1 if (num_questions % blocksize) > 0 else 0
        total_blocks = n_whole_blocks + n_partial_block
        
        n_blocks_per_column = total_blocks // num_cols
        total_columns = total_blocks // n_blocks_per_column + (1 if (total_blocks % num_cols) > 0 else 0)
        
        max_len_choice_keys = max(len(v) for v in choice_keys.values())
        
        qnum = 1
        
        debug_image = self.diagnostics.get('debug_image', None)

        centers: Dict[Tuple[int, str], Tuple[int, int]] = {} 

        for col in range(total_columns):
            # Calculate column x position (matches placement)
            x_col_px = field_ul_px[0] + col * (
                block_numbering_gap_px + 
                (bubble_radius_px * 2 + block_choice_gap_px) * max_len_choice_keys + 
                block_gap_px[0]
            )
            
            for block in range(n_blocks_per_column):
                # Calculate block start y position
                y_block_start_px = field_ul_px[1] + block * (
                    block_row_gap_px * blocksize + block_gap_px[1]
                )
                # write an X at the block origin for debugging
                if debug_image is not None:
                    x_marks_the_spot(debug_image, x_col_px, y_block_start_px)

                for row in range(blocksize):
                    if qnum > num_questions:
                        break
                    
                    # Get question type from question list if available
                    if hasattr(config, 'question_list') and config.question_list:
                        q = config.question_list[qnum - 1]
                        qtyp = q.get("type", "mcq").lower()
                    else:
                        qtyp = "mcq"  # Default
                    
                    choices = choice_keys[qtyp]
                    
                    # Calculate row y position
                    y_base_px = y_block_start_px + row * block_row_gap_px
                    
                    # Starting x for choices
                    x_choices_px = x_col_px + block_numbering_gap_px
                    
                    # draw an X in the debug image at the center of the first choice bubble
                    if debug_image is not None:
                        x_marks_the_spot(debug_image, x_choices_px, y_base_px)
                    
                    for i, key in enumerate(choices):
                        # Calculate bubble center position
                        x_bubble_px = x_choices_px + i * (block_choice_gap_px + bubble_radius_px * 2)
                        y_bubble_px = y_base_px
                        centers[(qnum, key)] = (x_bubble_px, y_bubble_px)
                    qnum += 1
        self.diagnostics['bubbles'] = centers
        return centers

    def _compute_bubble_fills(self, img_gray, centers, bubble_radius_px, pixel_threshold):
        """
        Compute fill ratios for every bubble at the given *pixel_threshold*.

        Returns ``{qnum: {choice_key: (fill_pct, x_px, y_px), ...}, ...}``
        """
        bubble_fills: Dict[int, Dict[str, Tuple[float, int, int]]] = {}
        for (qnum, choice_key), (x_px, y_px) in centers.items():
            if qnum not in bubble_fills:
                bubble_fills[qnum] = {}

            x1 = x_px - bubble_radius_px
            x2 = x_px + bubble_radius_px
            y1 = y_px - bubble_radius_px
            y2 = y_px + bubble_radius_px

            if x1 < 0 or y1 < 0 or x2 >= img_gray.shape[1] or y2 >= img_gray.shape[0]:
                continue

            bubble_roi = img_gray[y1:y2, x1:x2]

            mask = np.zeros_like(bubble_roi, dtype=np.uint8)
            cv2.circle(mask, (bubble_radius_px, bubble_radius_px), bubble_radius_px, 255, -1)

            masked_pixels = bubble_roi[mask > 0]
            if len(masked_pixels) == 0:
                continue

            _, binary = cv2.threshold(masked_pixels, pixel_threshold, 255, cv2.THRESH_BINARY_INV)
            fill_pct = np.sum(binary > 0) / len(masked_pixels)
            bubble_fills[qnum][choice_key] = (fill_pct, x_px, y_px)
        return bubble_fills

    def _interactive_resolve(self, qnum: int, centers: dict, answers: dict, answer_coords: dict):
        """
        Show the bubble row for *qnum* in a matplotlib window and prompt the
        user to type the answer.  Updates *answers* and *answer_coords* in place.
        Does nothing if not running in an interactive TTY.
        """
        import matplotlib.pyplot as plt

        # Gather all bubble centers for this question
        q_centers = {k: v for (q, k), v in centers.items() if q == qnum}
        if not q_centers:
            return

        valid_choices = list(q_centers.keys())
        xs = [x for x, y in q_centers.values()]
        ys = [y for x, y in q_centers.values()]

        pad = int(self.layout_config.bubble_radius.to('pxl').magnitude * 4)
        x1 = max(0, min(xs) - pad)
        x2 = min(self.working_image.shape[1], max(xs) + pad)
        y1 = max(0, min(ys) - pad)
        y2 = min(self.working_image.shape[0], max(ys) + pad)

        crop_bgr = self.working_image[y1:y2, x1:x2]
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)

        fig, ax = plt.subplots(figsize=(max(4, (x2 - x1) / 60), 2))
        ax.imshow(crop_rgb)
        student_id = self.results.get('student_id_bubbles') or '?'
        ax.set_title(f"Student {student_id} — Q{qnum} — no fill detected  (choices: {', '.join(valid_choices)})")
        ax.axis('off')
        plt.tight_layout()
        plt.show(block=False)
        plt.pause(0.1)

        try:
            while True:
                raw = input(f"  Q{qnum}: enter answer ({'/'.join(valid_choices)}) or '-' to leave blank: ").strip()
                if raw == '-':
                    break
                if raw in valid_choices:
                    answers[qnum] = raw
                    answer_coords[qnum] = q_centers[raw]
                    logger.info(f"Q{qnum}: manually resolved as '{raw}'")
                    break
                print(f"  Invalid choice '{raw}'. Valid options: {', '.join(valid_choices)}")
        except EOFError:
            logger.warning(f"Q{qnum}: stdin not readable — skipping interactive prompt")

        plt.close(fig)

    def _read_bubblefield(self):
        """
        Read all question answers from the bubble field.

        Uses an adaptive pixel threshold: starts strict (127) and
        progressively relaxes (160, 190) for any question where no
        bubble exceeds the fill-ratio threshold, catching lighter
        pencil marks.
        """
        debug_image = self.diagnostics.get('debug_image', None)

        if not 'bubbles' in self.diagnostics:
            centers = self._locate_bubbles()
        else:
            centers = self.diagnostics['bubbles']

        config = self.layout_config
        for key in centers.keys():
            x, y = centers[key]
            if self.diagnostics.get('debug_image') is not None:
                cv2.circle(
                    self.diagnostics['debug_image'],
                    (x, y),
                    int(config.bubble_radius.to('pxl').magnitude),
                    (255, 0, 255),
                    2
                )
        img_gray = cv2.cvtColor(self.working_image, cv2.COLOR_BGR2GRAY)
        bubble_radius_px = int(config.bubble_radius.to('pxl').magnitude)

        fill_threshold = config.fill_ratio_threshold
        pixel_thresholds = [127, 160, 190]

        answers: Dict[int, str] = {}
        answer_coords: Dict[int, Tuple[int, int]] = {}
        # qnum -> [(choice, x, y)] for questions rejected by runner_up_margin
        ambiguous_bubbles: Dict[int, List[Tuple[str, int, int]]] = {}

        for pixel_thresh in pixel_thresholds:
            # Only recompute for questions still unresolved
            unresolved = [q for q in range(1, config.num_questions + 1)
                          if answers.get(q, "?") == "?"]
            if not unresolved:
                break

            bubble_fills = self._compute_bubble_fills(
                img_gray, centers, bubble_radius_px, pixel_thresh)

            for qnum in unresolved:
                q_fills = bubble_fills.get(qnum, {})
                filled = [(choice, pct, x, y)
                          for choice, (pct, x, y)
                          in q_fills.items()
                          if pct >= fill_threshold]

                if len(filled) == 0:
                    answers[qnum] = "?"
                elif len(filled) > 1:
                    # More than one bubble above fill threshold.
                    filled.sort(key=lambda f: f[1], reverse=True)
                    top_choice, top_fill, top_x, top_y = filled[0]
                    second_fill = filled[1][1]
                    logger.debug(
                        f"Q{qnum}: multiple fills at pixel_threshold={pixel_thresh} "
                        f"({[(c, round(f, 3)) for c, f, _, _ in filled]})"
                    )
                    if top_fill - second_fill >= config.runner_up_margin:
                        # One bubble clearly dominates — accept it.
                        answers[qnum] = top_choice
                        answer_coords[qnum] = (top_x, top_y)
                        ambiguous_bubbles.pop(qnum, None)
                        logger.debug(
                            f"Q{qnum}: dominant fill accepted "
                            f"(answer={top_choice}, fill={top_fill:.3f}, "
                            f"margin={top_fill - second_fill:.3f})"
                        )
                    else:
                        answers[qnum] = "?"
                        ambiguous_bubbles[qnum] = [(c, x, y) for c, _, x, y in filled]
                else:
                    # Exactly one bubble above fill threshold.
                    top_choice, top_fill, top_x, top_y = filled[0]
                    # Also require it to stand out from all other choices by at least
                    # runner_up_margin — catches circle-outline false positives.
                    second_fill = max(
                        (pct for k, (pct, _, _) in q_fills.items() if k != top_choice),
                        default=0.0,
                    )
                    if top_fill - second_fill < config.runner_up_margin:
                        logger.debug(
                            f"Q{qnum}: rejected at pixel_threshold={pixel_thresh} "
                            f"(top={top_choice}:{top_fill:.3f}, "
                            f"second_best:{second_fill:.3f}, "
                            f"margin={top_fill - second_fill:.3f} < {config.runner_up_margin})"
                        )
                        answers[qnum] = "?"
                        ambiguous_bubbles[qnum] = [(c, x, y) for c, _, x, y in filled]
                    else:
                        answers[qnum] = top_choice
                        answer_coords[qnum] = (top_x, top_y)
                        ambiguous_bubbles.pop(qnum, None)
                        if pixel_thresh > pixel_thresholds[0]:
                            logger.debug(
                                f"Q{qnum}: resolved at pixel_threshold={pixel_thresh} "
                                f"(answer={top_choice}, fill={top_fill:.3f}, "
                                f"margin={top_fill - second_fill:.3f})"
                            )

        # Draw debug circles for all resolved answers
        if debug_image is not None:
            for qnum, (x, y) in answer_coords.items():
                cv2.circle(
                    debug_image,
                    (x, y),
                    int(bubble_radius_px * 1.05),
                    (190, 25, 25),
                    3,
                )

        self.diagnostics['bubbles'] = centers
        self.diagnostics['ambiguous_bubbles'] = ambiguous_bubbles

        blank_qs = [q for q, a in answers.items() if a == "?" and q not in ambiguous_bubbles]
        ambig_qs = [q for q in ambiguous_bubbles]
        if self.interactive:
            for qnum in blank_qs + ambig_qs:
                self._interactive_resolve(qnum, centers, answers, answer_coords)
            blank_qs = [q for q in blank_qs if answers.get(q) == "?"]
            ambig_qs = [q for q in ambig_qs if answers.get(q) == "?"]

        self.results['answers'] = answers

        if blank_qs:
            logger.warning(
                f"No fill detected for question(s) {blank_qs} "
                f"— treating as unanswered (will be scored wrong)"
            )
        if ambig_qs:
            logger.warning(
                f"Ambiguous/multiple fill detected for question(s) {ambig_qs} "
                f"— treating as unanswered (will be scored wrong)"
            )


    def _read_qr(self):
        """
        Read the QR code from the warped answer-sheet image.
        """
        config = self.layout_config
        detector = cv2.QRCodeDetector()
        gray = cv2.cvtColor(self.working_image, cv2.COLOR_BGR2GRAY)
        # gray = cv2.resize(gray, None, fx=0.5, fy=0.5)

        h, w = gray.shape[:2]
        qr_ul_pxl = (
            int(config.qr_ul[0].to('pxl').magnitude),
            int(config.qr_ul[1].to('pxl').magnitude),
        )
        qr_lr = qr_ul_pxl[0] + int(config.qr_size.to('pxl').magnitude), qr_ul_pxl[1] + int(config.qr_size.to('pxl').magnitude)
        # shift qr_lr so that aspect ratio is 1:1
        x0, x1 = qr_ul_pxl[0], qr_lr[0]
        y0, y1 = qr_ul_pxl[1], qr_lr[1]
        # readjust x1, y1 to ensure square region
        side_len = min(x1 - x0, y1 - y0)
        x1 = x0 + side_len
        y1 = y0 + side_len

        logger.debug(f"QR crop region: ({x0}, {y0}) to ({x1}, {y1}) in warped image of size ({w}, {h})")

        # draw the crop region on the debug image for diagnostics
        debug_image = self.diagnostics.get('debug_image', None)
        if debug_image is not None:
            cv2.rectangle(
                debug_image,
                (x0, y0),
                (x1, y1),
                (255, 0, 99),
                3,
            )
        self.diagnostics['qr_crop_coords'] = {
            'x0': x0,
            'y0': y0,
            'x1': x1,
            'y1': y1,
        }
        # write the debug image
        if self.diagnostics.get('debug_image') is not None:
            debug_img_path = self.debug_output_path / f"qr.png"
            cv2.imwrite(str(debug_img_path), self.diagnostics['debug_image'])
        # self.diagnostics['qr_crop_region'] = {
        #     'upper_left': (x0, y0),
        #     'lower_right': (x1, y1),
        # }

        roi = gray[y0:y1, x0:x1]
        debug_roi_path = self.debug_output_path / f"qr_roi.png"
        cv2.imwrite(str(debug_roi_path), roi)

        # Adaptive QR reading: try full image and cropped ROI at native
        # resolution first, then retry both at 50% scale.
        attempts = [
            ("full image", gray),
            ("cropped ROI", roi),
            ("full image 50%", cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)),
            ("cropped ROI 50%", cv2.resize(roi, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)),
        ]

        data = None
        points = None
        for label, img in attempts:
            try:
                data, points, _ = detector.detectAndDecode(img)
            except Exception as e:
                logger.debug(f"QR attempt '{label}' raised: {e}")
                continue
            if data:
                raw = data.strip()
                if ':' in raw and self.layout_config.qr_answer_key:
                    version_part, payload = raw.split(':', 1)
                    self.results['version'] = version_part
                    try:
                        from ..util.qrcrypto import decrypt_answers
                        self.results['embedded_answers'] = decrypt_answers(
                            self.layout_config.qr_answer_key, payload
                        )
                        logger.debug(f"QR code decoded with embedded answers via '{label}': version={version_part}")
                    except ValueError as exc:
                        raise RuntimeError(f"QR answer decryption failed: {exc}") from exc
                else:
                    self.results['version'] = raw
                    logger.debug(f"QR code detected via '{label}': {self.results['version']}")
                break
        else:
            raise RuntimeError("Failed to read QR code from answer sheet.")
        if debug_image is not None and points is not None:
            # echo the qr value
            cv2.putText(
                debug_image,
                f"v{self.results['version']}",
                (x0, y0 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (139, 0, 0),
                2,
                cv2.LINE_AA,
            )

    def _compute_id_column_fills(self, img_gray, col_center_x, bubble_centers_y,
                                   bubble_radius_px, pixel_threshold):
        """
        Compute fill ratios for the 10 bubbles in one student-ID column
        at the given *pixel_threshold*.

        Returns ``[(digit, fill_pct, x, y), ...]``
        """
        fills: list[Tuple[int, float, int, int]] = []
        for j, bubble_center_y in enumerate(bubble_centers_y):
            x1 = col_center_x - bubble_radius_px
            x2 = col_center_x + bubble_radius_px
            y1 = bubble_center_y - bubble_radius_px
            y2 = bubble_center_y + bubble_radius_px

            if x1 < 0 or y1 < 0 or x2 >= img_gray.shape[1] or y2 >= img_gray.shape[0]:
                continue

            bubble_roi = img_gray[y1:y2, x1:x2]

            mask = np.zeros_like(bubble_roi, dtype=np.uint8)
            cv2.circle(mask, (bubble_radius_px, bubble_radius_px), bubble_radius_px, 255, -1)

            masked_pixels = bubble_roi[mask > 0]
            if len(masked_pixels) == 0:
                continue

            _, binary = cv2.threshold(masked_pixels, pixel_threshold, 255, cv2.THRESH_BINARY_INV)
            fill_pct = np.sum(binary > 0) / len(masked_pixels)
            fills.append((j, fill_pct, col_center_x, bubble_center_y))
        return fills

    def _read_student_id_bubbles(self):
        config = self.layout_config
        num_digits = config.student_id_num_digits

        img_gray = cv2.cvtColor(self.working_image, cv2.COLOR_BGR2GRAY)

        ul_x_px = int(config.student_id_digit_boxes_ul[0].to('pxl').magnitude)
        ul_y_px = int(config.student_id_digit_boxes_ul[1].to('pxl').magnitude)
        box_width_px = int(config.student_id_digit_boxes_box_size[0].to('pxl').magnitude)
        box_height_px = int(config.student_id_digit_boxes_box_size[1].to('pxl').magnitude)
        gap_px = int(config.student_id_digit_boxes_horiz_gap.to('pxl').magnitude)
        vgap_px = int(config.bubble_column_vert_gap.to('pxl').magnitude)
        bubble_radius_px = int(config.bubble_radius.to('pxl').magnitude)
        debug_image = self.diagnostics.get('debug_image', None)

        spacing_px = 2 * bubble_radius_px + vgap_px

        id_digits: list[str] = ["?"] * num_digits
        digit_coords: Dict[int, Tuple[int, int]] = {}
        id_bubble_centers_px: Dict[Tuple[int, int], Tuple[int, int]] = {}
        self.diagnostics['id_bubble_region'] = {
            'x0': ul_x_px,
            'y0': ul_y_px,
            'x1': ul_x_px + num_digits * (box_width_px + gap_px) - gap_px,
            'y1': ul_y_px + box_height_px + vgap_px + spacing_px * 10,
        }

        # Pre-compute column geometry (centres + per-column bubble y positions)
        col_geometry: list[Tuple[int, list[int]]] = []  # (col_center_x, [bubble_y_0..9])
        for i in range(1, num_digits + 1):
            col_center_x = ul_x_px + int(round((i - 1) * (gap_px + box_width_px))) + int(np.round(0.5 * box_width_px))
            bubble_ys = []
            for j in range(10):
                bubble_center_y = ul_y_px + box_height_px + vgap_px + bubble_radius_px + spacing_px * j
                bubble_ys.append(bubble_center_y)
                id_bubble_centers_px[(i, j)] = (col_center_x, bubble_center_y)
                if debug_image is not None:
                    cv2.circle(debug_image, (col_center_x, bubble_center_y),
                               bubble_radius_px, (0, 255, 0), 2)
            col_geometry.append((col_center_x, bubble_ys))

        threshold = config.fill_ratio_threshold
        pixel_thresholds = [127, 160, 190, 210]

        for pixel_thresh in pixel_thresholds:
            unresolved = [idx for idx in range(num_digits) if id_digits[idx] == "?"]
            if not unresolved:
                break

            for idx in unresolved:
                col_center_x, bubble_ys = col_geometry[idx]
                bubble_fills = self._compute_id_column_fills(
                    img_gray, col_center_x, bubble_ys, bubble_radius_px, pixel_thresh)

                logger.debug(f"ID column {idx+1} (pixel_thresh={pixel_thresh}): "
                             f"bubble fills = {bubble_fills}, threshold={threshold}")

                if not bubble_fills:
                    continue

                # Relative contrast: filled bubble must stand out above column baseline
                all_fills = [f for _, f, _, _ in bubble_fills]
                median_fill = float(np.median(all_fills))
                effective_threshold = max(threshold, median_fill * 2.0)
                logger.debug(f"ID column {idx+1}: median_fill={median_fill:.3f}, "
                             f"effective_threshold={effective_threshold:.3f}")

                filled = [(d, f, x, y) for d, f, x, y in bubble_fills
                          if f >= effective_threshold]

                if len(filled) == 1:
                    id_digits[idx] = str(filled[0][0])
                    digit_coords[idx] = (filled[0][2], filled[0][3])
                    if pixel_thresh > pixel_thresholds[0]:
                        logger.debug(
                            f"ID column {idx+1}: resolved at pixel_threshold={pixel_thresh} "
                            f"(digit={filled[0][0]}, fill={filled[0][1]:.3f})")
                elif len(filled) > 1:
                    filled.sort(key=lambda f: f[1], reverse=True)
                    id_digits[idx] = str(filled[0][0])
                    digit_coords[idx] = (filled[0][2], filled[0][3])
                    if pixel_thresh > pixel_thresholds[0]:
                        logger.debug(
                            f"ID column {idx+1}: resolved at pixel_threshold={pixel_thresh} "
                            f"(digit={filled[0][0]}, fill={filled[0][1]:.3f})")

        # Draw debug circles for resolved digits
        if debug_image is not None:
            for idx, (x, y) in digit_coords.items():
                cv2.circle(debug_image, (x, y),
                           int(bubble_radius_px * 1.05), (195, 25, 25), 3)

        # If any blanks, treat as no ID
        if any(d == "?" for d in id_digits):
            self.results['student_id_bubbles'] = None
            uncertain = [i for i, d in enumerate(id_digits) if d == "?"]
            raise RuntimeError(
                f"Could not determine student ID: uncertain digit(s) at position(s) {uncertain} "
                f"(partial read: {''.join(id_digits)})"
            )
        else:
            self.results['student_id_bubbles'] = "".join(id_digits)

        self.diagnostics['id_bubble_centers'] = id_bubble_centers_px

    # def _read_student_id_ocr(self):
    #     config = self.layout_config
    #     num_digits = config.student_id_num_digits
    #     model = get_digit_model()
        
    #     # Image is already warped to canonical page coordinates
    #     img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
    #     confidence_threshold = config.student_id_ocr_confidence_threshold

    #     # Convert layout positions from physical units to pixels
    #     id_box_ul_px = (
    #         int(config.student_id_digit_boxes_ul[0].to('pxl').magnitude),
    #         int(config.student_id_digit_boxes_ul[1].to('pxl').magnitude)
    #     )
    #     # write an X at the upper-left corner for diagnostics
    #     debug_image = self.diagnostics.get('debug_image', None)
    #     if debug_image is not None:
    #         cv2.line(
    #             debug_image,
    #             (id_box_ul_px[0] - 10, id_box_ul_px[1] - 10),
    #             (id_box_ul_px[0] + 10, id_box_ul_px[1] + 10),
    #             (34, 122, 255),
    #             3,
    #         )
    #         cv2.line(
    #             debug_image,
    #             (id_box_ul_px[0] - 10, id_box_ul_px[1] + 10),
    #             (id_box_ul_px[0] + 10, id_box_ul_px[1] - 10),
    #             (34, 122, 255),
    #             3,
    #         )
    #     box_width_px = int(config.student_id_digit_boxes_box_size[0].to('pxl').magnitude)
    #     box_height_px = int(config.student_id_digit_boxes_box_size[1].to('pxl').magnitude)
    #     gap_px = int(config.student_id_digit_boxes_horiz_gap.to('pxl').magnitude)
        
    #     x0, y0 = id_box_ul_px
        
    #     digits: list[str] = []

    #     outer_boxes = []
    #     inner_boxes = []

    #     for i in range(num_digits):
    #         # Calculate this box's position
    #         box_x0 = x0 + i * (box_width_px + gap_px)
    #         box_x1 = box_x0 + box_width_px
    #         box_y0 = y0
    #         box_y1 = y0 + box_height_px
    #         # draw this box for diagnostics
    #         debug_image = self.diagnostics.get('debug_image', None)
    #         if debug_image is not None:
    #             cv2.rectangle(
    #                 debug_image,
    #                 (box_x0, box_y0),
    #                 (box_x1, box_y1),
    #                 (255, 0, 0),
    #                 3,
    #             )
    #         outer_boxes.append((box_x0, box_y0, box_x1, box_y1))
    #         # Extract cell
    #         cell = img_gray[box_y0:box_y1, box_x0:box_x1]
            
    #         ch, cw = cell.shape
    #         if ch <= 0 or cw <= 0:
    #             digits.append("")
    #             continue

    #         # Inner crop to avoid borders
    #         margin_y = int(config.student_id_digits_cell_margin_frac * ch)
    #         margin_x = int(config.student_id_digits_cell_margin_frac * cw)
    #         iy0 = box_y0 + margin_y
    #         iy1 = box_y0 + ch - margin_y
    #         ix0 = box_x0 + margin_x
    #         ix1 = box_x0 + cw - margin_x

    #         if iy1 <= iy0 or ix1 <= ix0:
    #             digits.append("")
    #             continue

    #         inner = img_gray[iy0:iy1, ix0:ix1]
    #         inner_boxes.append((ix0, iy0, ix1, iy1))
    #         debug_image = self.diagnostics.get('debug_image', None)
    #         if debug_image is not None:
    #             logger.debug(f'ID OCR: digit {i+1}, outer box=({box_x0},{box_y0})-({box_x1},{box_y1}), inner box=({ix0},{iy0})-({ix1},{iy1})')
    #             cv2.rectangle(
    #                 debug_image,
    #                 (ix0, iy0),
    #                 (ix1, iy1),
    #                 (0, 0, 255),
    #                 3,
    #             )
    #         inner = get_centered_padded_digit(inner, pad=5)

    #         # Run CNN OCR
    #         digit, conf = ocr_digit_nn(inner, model=model)
            
    #         if conf < confidence_threshold:
    #             digits.append("?")
    #             if digit == '7':
    #                 # Check if it's actually a 9 written upside down
    #                 rotated_inner = cv2.rotate(inner, cv2.ROTATE_180)
    #                 digit_rot, conf_rot = ocr_digit_nn(rotated_inner, model=model)
    #                 if conf_rot >= confidence_threshold and digit_rot == '6':
    #                     digits[-1] = '9'
    #         else:
    #             if digit == '3':
    #                 # Might be an 8 with gaps
    #                 flipped_inner = cv2.flip(inner, 1)
    #                 digit_flp, conf_flp = ocr_digit_nn(flipped_inner, model=model)
    #                 if conf_flp >= confidence_threshold and digit_flp == '8':
    #                     digit = '8'
    #             digits.append(digit)

    #     # If all blanks, treat as no ID
    #     if all(d == "" for d in digits):
    #         self.results['student_id_ocr'] = None
    #     else:
    #         self.results['student_id_ocr'] = "".join(d if d else "?" for d in digits)

    #     self.diagnostics['id_digit_outer_boxes'] = outer_boxes
    #     self.diagnostics['id_digit_inner_boxes'] = inner_boxes

    def _read_student_id(self):
        """
        Read the student ID from the warped answer-sheet image,
        using both bubble detection and OCR methods.
        """
        self._read_student_id_bubbles()
        # self._read_student_id_ocr()