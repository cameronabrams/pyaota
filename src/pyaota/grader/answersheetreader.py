from pathlib import Path
from ..generator.answersheet import LayoutConfig, TextBoxConfig
from ..ocr.digit_ocr import ocr_digit_nn, load_digit_model
from typing import Any, Dict, Tuple, List, Optional
import numpy as np
import cv2
import logging

logger = logging.getLogger(__name__)

def get_centered_padded_digit(img_gray: np.ndarray, pad: int = 10) -> np.ndarray:
    """
    Takes a grayscale digit image, finds the ink bounding box,
    centers the digit in a new image, and adds uniform padding.
    
    Returns a new grayscale image.
    """

    # Ensure grayscale
    if img_gray.ndim == 3:
        img_gray = cv2.cvtColor(img_gray, cv2.COLOR_BGR2GRAY)

    # Threshold to get binary ink mask (digit in black or white)
    _, th = cv2.threshold(
        img_gray, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    # Now digit strokes are white (255), background black (0)

    # Find bounding box of the white pixels
    ys, xs = np.where(th > 0)  # coordinates where ink exists
    if len(xs) == 0 or len(ys) == 0:
        # no ink found ― return padded blank image
        h, w = img_gray.shape
        return 255 * np.ones((h + 2*pad, w + 2*pad), dtype=np.uint8)

    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()

    # Crop to bounding box
    cropped = img_gray[y_min:y_max+1, x_min:x_max+1]

    # Create padded new image
    new_h = (y_max - y_min + 1) + 2 * pad
    new_w = (x_max - x_min + 1) + 2 * pad

    canvas = 255 * np.ones((new_h, new_w), dtype=np.uint8)  # white background

    # Paste the Cropped digit in the center
    canvas[pad:pad + cropped.shape[0], pad:pad + cropped.shape[1]] = cropped

    return canvas

# Optionally load global model once if you like
_DIGIT_MODEL = None

def get_digit_model():
    global _DIGIT_MODEL
    if _DIGIT_MODEL is None:
        _DIGIT_MODEL = load_digit_model()
    return _DIGIT_MODEL

class AnswerSheetReader:
    def __init__(self, img: np.ndarray, layout_config: LayoutConfig, debug_output_dir: Path = Path("debug")):
        self.rawimg = img.copy()
        self.img = img
        self.layout_config = layout_config
        self.debug_output_path = debug_output_dir
        self.results = {}
        self.diagnostics = {}
        if not self.debug_output_path.exists():
            self.debug_output_path.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, Any]:
        self._find_indicials()
        self._warp_to_canonical()
        self._read_bubbles()
        self._read_qr()
        self._read_student_id()
        return self.results
        
    def _find_indicials(self):

        """
        Detect indicial markers in the four corners of the answer sheet image.

        Returns a dictionary mapping corner names ('nw', 'ne', 'sw', 'se') to
        (x, y) pixel coordinates of the detected indicials.

        Raises RuntimeError if any indicial cannot be found.
        """
        img = self.img.copy()

        h, w = img.shape[:2]
        ftopvert = int(h*self.layout_config.indicial_top_vertical_margin_frac) # top of north indicials search regions
        fbotvert = int(h*self.layout_config.indicial_bottom_vertical_margin_frac) # top of south indicial search regions
        fhoriz = int(w*self.layout_config.indicial_horizontal_margin_frac) # width of indicial search regions, distance from respective edges
        region_y = int(self.layout_config.indicial_vertical_size_frac * h) # height of indicial search regions
        # Define small search windows near the *physical* page corners
        regions = {
            "nw": dict(
                upper_left = (0, ftopvert),
                lower_right = (fhoriz, ftopvert+region_y),
            ),
            "ne": dict(
                upper_left = (w - fhoriz, ftopvert),
                lower_right = (w, ftopvert+region_y),
            ),
            "sw": dict(
                upper_left = (0, h - region_y),
                lower_right = (fhoriz, h),
            ),
            "se": dict(
                upper_left = (w - fhoriz, h - region_y),
                lower_right = (w, h),
            ),
        }

        # write a debug image showing the search regions
        self.diagnostics['indicial_regions'] = regions
        debug_img = img.copy()

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Light background, dark dots/text → invert for contour detection
        _, bin_inv = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        centers: Dict[str, Tuple[int, int]] = {}

        for name, region in regions.items():
            upper_left = region["upper_left"]
            lower_right = region["lower_right"]
            sub = bin_inv[upper_left[1]:lower_right[1], upper_left[0]:lower_right[0]]
            contours, _ = cv2.findContours(
                sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                raise RuntimeError(f"No indicial candidate found in region {name}")

            best_center = None
            best_score = None

            # Heuristic expected area range for the dot, relative to page
            page_area = h * w
            min_area = 0.00001 * page_area
            max_area = 0.001 * page_area

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area <= 0:
                    continue

                # Filter out huge contours (likely text/graphics) when possible
                if not (min_area <= area <= max_area):
                    # We'll *allow* them as a fallback, but we prefer the area window
                    area_ok = False
                else:
                    area_ok = True

                M = cv2.moments(cnt)
                if M["m00"] == 0:
                    continue
                cx_sub = int(M["m10"] / M["m00"])
                cy_sub = int(M["m01"] / M["m00"])

                # Map back to full image coords
                upper_left = region["upper_left"]
                cx = upper_left[0] + cx_sub
                cy = upper_left[1] + cy_sub
                # Distance from the physical corner
                dx = cx 
                dy = cy 
                dist2 = dx * dx + dy * dy

                # Score: prioritize area in the expected range, then distance
                if area_ok:
                    score = dist2          # smaller is better
                else:
                    score = dist2 * 10.0   # penalize out-of-range areas

                if best_score is None or score < best_score:
                    best_score = score
                    best_center = (cx, cy)

            if best_center is None:
                raise RuntimeError(f"No valid indicial found in region {name}")

            centers[name] = best_center

        self.diagnostics['indicials']  = centers

        if set(centers.keys()) != {"nw", "ne", "sw", "se"}:
            raise RuntimeError("Failed to detect all four indicials.")

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
        out_img = self.img_original.copy()
        in_img = self.img.copy()
        bubble_radius = int(self.layout_config.bubble_radius_frac * min(in_img.shape[:2]) * 1.05)
        centers = self.diagnostics['bubbles']
        center_coords = list(centers.values())
        pts_array = np.array(center_coords, dtype=np.float32).reshape(-1, 1, 2)
        unwrapped_center_coords = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
        bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_center_coords]
        bubble_keys = list(centers.keys())
        for qnum in range(1, config.num_questions+1):
            q_info = per_question_results[qnum]
            correct_bubble_label = q_info["correct"]
            detected_filled_bubble_label = q_info["detected"]
            is_correct = q_info["is_correct"]
            for key in 'abcd':
                bubble_idx = bubble_keys.index((qnum, key))
                bubble_center = bubble_result_tuples[bubble_idx]
                x, y = bubble_center
                if key == correct_bubble_label:
                    cv2.circle(out_img, (x, y), bubble_radius, (0, 255, 0), 3)
                elif key == detected_filled_bubble_label and not is_correct:
                    cv2.circle(out_img, (x, y), bubble_radius, (0, 0, 255), 3)
        id_bubble_color = (0, 165, 255)  # dark orange
        id_bubble_region = self.diagnostics.get('id_bubble_region', None)
        if id_bubble_region is not None:
            id_detected = self.results['student_id_bubbles']
            ul = id_bubble_region['upper_left']
            lr = id_bubble_region['lower_right']
            ur = (lr[0], ul[1])
            ll = (ul[0], lr[1])
            pts_array = np.array([ul, ur, lr, ll], dtype=np.float32).reshape(-1, 1, 2)
            unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
            id_bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
            u_ul, u_ur, u_lr, u_ll = id_bubble_result_tuples
            cv2.putText(
                out_img,
                f"ID: {id_detected}",
                (u_ur[0]+10, int(0.5*(u_ur[1] + u_lr[1]))),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                id_bubble_color,
                2,
                cv2.LINE_AA,
            )
        qr_crop = self.diagnostics.get('qr_crop_region', None)
        if qr_crop is not None:
            version_detected = self.results.get('version', 'unknown')
            qr_color = (139, 0, 0) # navy blue
            ul = qr_crop['upper_left']
            lr = qr_crop['lower_right']
            ur = (lr[0], ul[1])
            ll = (ul[0], lr[1])
            pts_array = np.array([ul, ur, lr, ll], dtype=np.float32).reshape(-1, 1, 2)
            unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
            qr_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
            u_ul, u_ur, u_lr, u_ll = qr_result_tuples
            cv2.putText(
                out_img,
                f"Score: {(score_fraction*100):.1f}%",
                (u_ul[0] - 325, u_ll[1] + 200),
                cv2.FONT_HERSHEY_SIMPLEX,
                4.0,
                qr_color,
                4,
                cv2.LINE_AA,
            )
        logger.debug(f"Graded overlay written to {overlay_path}")
        cv2.imwrite(str(overlay_path), out_img)         


    def write_debug_output(self,
        version_label: str = None,
    ):
        overlay_path = self.debug_output_path / f"debug_page_{version_label}.png"
        overlay_img = self._diagnostic_overlay()
        cv2.imwrite(str(overlay_path), overlay_img)
        logger.debug(f"Debug overlay written to {overlay_path}")

    def _diagnostic_overlay(self, version_str: str = None):
        config = self.layout_config
        out_img = self.img_original.copy()
        in_img = self.img.copy()
        bubble_radius = int(self.layout_config.bubble_radius_frac * min(in_img.shape[:2]))

        local_version_str = version_str
        if local_version_str is None:
            local_version_str = self.results.get('version', None)
    
        # indicials are located in the unwarped image
        for name, region in self.diagnostics['indicial_regions'].items():
            upper_left = region["upper_left"]
            lower_right = region["lower_right"]
            cv2.rectangle(
                in_img,
                upper_left,
                lower_right,
                (255, 0, 0),
                2,
            )

        colors = {
            "nw": (0, 0, 255),   # red
            "ne": (0, 255, 0),   # green
            "se": (255, 0, 0),   # blue
            "sw": (0, 165, 200), # orange
        }

        for name, (x, y) in self.diagnostics['indicials'].items():
            color = colors.get(name, (255, 255, 255))
            cv2.circle(out_img, (x, y), 12, color, 3)
            cv2.putText(
                out_img,
                name.upper(),
                (x + 5, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

        # bubble grid located in warped image, so have to unwarp the centers
        centers = self.diagnostics['bubbles']
        center_coords = list(centers.values())
        pts_array = np.array(center_coords, dtype=np.float32).reshape(-1, 1, 2)
        unwrapped_center_coords = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
        bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_center_coords]
        for (qnum, key), (cx, cy) in zip(centers.keys(), bubble_result_tuples):
            ucx, ucy = cx, cy
            cv2.circle(out_img, (ucx, ucy), bubble_radius, (0, 255, 0), 2)
            cv2.putText(
                out_img,
                f"{qnum}{key}",
                (ucx + 10, ucy - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

        # qr region located in warped image, so have to unwarp the corners
        qr_crop = self.diagnostics.get('qr_crop_region', None)
        if qr_crop is not None:
            version_detected = self.results.get('version', 'unknown')
            qr_color = (139, 0, 0) # navy blue
            ul = qr_crop['upper_left']
            lr = qr_crop['lower_right']
            ur = (lr[0], ul[1])
            ll = (ul[0], lr[1])
            pts_array = np.array([ul, ur, lr, ll], dtype=np.float32).reshape(-1, 1, 2)
            unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
            qr_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
            u_ul, u_ur, u_lr, u_ll = qr_result_tuples
            cv2.line(out_img, tuple(u_ul), tuple(u_ur), qr_color, 2)
            cv2.line(out_img, tuple(u_ur), tuple(u_lr), qr_color, 2)
            cv2.line(out_img, tuple(u_lr), tuple(u_ll), qr_color, 2)
            cv2.line(out_img, tuple(u_ll), tuple(u_ul), qr_color, 2)
            cv2.putText(
                out_img,
                f"v{version_detected}",
                (u_ul[0], u_ul[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                qr_color,
                2,
                cv2.LINE_AA,
            )

        # student id bubble region located in warped image, so have to unwarp the corners
        id_bubble_color = (0, 165, 255)  # dark orange
        id_bubble_region = self.diagnostics.get('id_bubble_region', None)
        if id_bubble_region is not None:
            id_detected_digitstr = self.results.get('student_id_bubbles', 'unknown')
            id_detected = ''.join([str(d) if d is not None else '?' for d in id_detected_digitstr])
            ul = id_bubble_region['upper_left']
            lr = id_bubble_region['lower_right']
            ur = (lr[0], ul[1])
            ll = (ul[0], lr[1])
            pts_array = np.array([ul, ur, lr, ll], dtype=np.float32).reshape(-1, 1, 2)
            unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
            id_bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
            u_ul, u_ur, u_lr, u_ll = id_bubble_result_tuples
            cv2.line(out_img, tuple(u_ul), tuple(u_ur), id_bubble_color, 2)
            cv2.line(out_img, tuple(u_ur), tuple(u_lr), id_bubble_color, 2)
            cv2.line(out_img, tuple(u_lr), tuple(u_ll), id_bubble_color, 2)
            cv2.line(out_img, tuple(u_ll), tuple(u_ul), id_bubble_color, 2)
            cv2.putText(
                out_img,
                f"ID: {id_detected}",
                (u_ur[0]+10, int(0.5*(u_ur[1] + u_lr[1]))),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                id_bubble_color,
                2,
                cv2.LINE_AA,
            )   
        id_bubble_centers = self.diagnostics.get('id_bubble_centers', None)
        if id_bubble_centers is not None:
            center_coords = list(id_bubble_centers.values())
            pts_array = np.array(center_coords, dtype=np.float32).reshape(-1, 1, 2)
            unwrapped_center_coords = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
            id_bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_center_coords]
            for (pos, digit), (cx, cy) in zip(id_bubble_centers.keys(), id_bubble_result_tuples):
                u_cx, u_cy = cx, cy
                cv2.circle(out_img, (u_cx, u_cy), bubble_radius, id_bubble_color, 2)
                cv2.putText(
                    out_img,
                    f"{pos}{digit}",
                    (u_cx + 10, u_cy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    id_bubble_color,
                    1,
                    cv2.LINE_AA,
                )

        # student id digit boxes located in warped image, so have to unwarp the corners
        id_digit_boxes = self.diagnostics.get('id_digit_boxes', None)
        if id_digit_boxes is not None:
            id_digits_ocr = self.results.get('student_id_ocr', "")
            id_digits_color = (0, 0, 139)  # dark red
            for i, (cx0, cy0, cx1, cy1) in id_digit_boxes.items():
                pts_array = np.array(
                    [(cx0, cy0), (cx1, cy0), (cx1, cy1), (cx0, cy1)],
                    dtype=np.float32
                ).reshape(-1, 1, 2)
                unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
                id_digits_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
                u_ul, u_ur, u_lr, u_ll = id_digits_result_tuples
                cv2.line(out_img, tuple(u_ul), tuple(u_ur), id_digits_color, 2)
                cv2.line(out_img, tuple(u_ur), tuple(u_lr), id_digits_color, 2)
                cv2.line(out_img, tuple(u_lr), tuple(u_ll), id_digits_color, 2)
                cv2.line(out_img, tuple(u_ll), tuple(u_ul), id_digits_color, 2)
                # put text
                cv2.putText(
                    out_img,
                    f"{id_digits_ocr[i] if i < len(id_digits_ocr) else '?'}",
                    (u_ul[0] + 5, u_ul[1] + 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    id_digits_color,
                    1,
                    cv2.LINE_AA,
                )

        # bubble scores overlay in warped image, so unwarp the centers
        scores = self.diagnostics.get('bubble_scores', {})
        # print(f"Bubble scores: {scores}")
        all_vals = list(scores.values())
        if all_vals:
            vmin, vmax = min(all_vals), max(all_vals)
            if vmax == vmin:
                vmax = vmin + 1e-6
        else:
            vmin, vmax = 0.0, 1.0
        for (qnum, key), (cx, cy) in zip(centers.keys(), bubble_result_tuples):
            val = scores.get((qnum, key), 0.0)
            # logger.info(f"Bubble score Q{qnum}{key}: {val:.3f}")
            t = (val - vmin) / (vmax - vmin)
            # t=0 => green, t=1 => red
            r = 0
            g = int(255 * (1.0 - t))
            b = int(255 * t)
            color = (b, g, r)

            cv2.circle(out_img, (cx, cy), int(bubble_radius*1.05), color, 3)
            # label each first-choice bubble with qnum
            if key == config.choice_keys[0]:
                cv2.putText(
                    out_img, str(qnum), (cx - 15, cy - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA
                )

        return out_img
        # out_img_file = "overlay.png" if local_version_str is None else f"overlay-{local_version_str}.png"
        # out_path = self.debug_output_path / out_img_file
        # logger.debug(f"indicials overlay written to {out_path}")
        # cv2.imwrite(str(out_path), out_img)

    def _warp_to_canonical(self):
        base_width = self.layout_config.canonical_width_px
        img = self.img
        self.img_original = img.copy()
        self.original_size = img.shape[:2]  # (height, width)
        indicials = self.diagnostics['indicials']

        (nw, ne, sw, se) = indicials['nw'], indicials['ne'], indicials['sw'], indicials['se']
        pts_src = np.float32([nw, ne, sw, se])

        # approximate physical width/height from the indicials
        width_top  = np.linalg.norm(np.array(ne) - np.array(nw))
        width_bot  = np.linalg.norm(np.array(se) - np.array(sw))
        width      = max(width_top, width_bot)

        height_left  = np.linalg.norm(np.array(sw) - np.array(nw))
        height_right = np.linalg.norm(np.array(se) - np.array(ne))
        height       = max(height_left, height_right)

        aspect = height / width if width > 0 else 1.0

        out_w = base_width
        out_h = int(base_width * aspect)

        pts_dst = np.float32([
            [0,      0],
            [out_w-1, 0],
            [0,      out_h-1],
            [out_w-1, out_h-1],
        ])

        M = cv2.getPerspectiveTransform(pts_src, pts_dst)
        M_inv = cv2.getPerspectiveTransform(pts_dst, pts_src)
        self.diagnostics['warp_matrix'] = M
        self.diagnostics['warp_matrix_inv'] = M_inv
        self.diagnostics['warped_size'] = (out_h, out_w)
        self.img = cv2.warpPerspective(img, M, (out_w, out_h))

    def _compute_bubble_centers(self):
        """
        Compute bubble centers (in pixel coordinates of the warped image)
        for each (question_number, choice_key), using a column-major layout
        with blocks of `rows_per_block` questions and extra gaps between blocks.

        Column-major numbering:
        - Let rows = ceil(num_questions / num_cols)
        - Column 0 has questions 1..rows
        - Column 1 has rows+1..2*rows
        - etc.
        """
        img_shape = self.img.shape
        h, w = img_shape[:2]
        num_questions = self.layout_config.num_questions
        choices = list(self.layout_config.choice_keys)
        num_cols = self.layout_config.num_cols
        rows_per_block = self.layout_config.rows_per_block

        # questions are ordered column-wise and grouped into blocks of rows_per_block that cannot be broken except in the very last block of the very last column
        # so rows must be a multiple of rows_per_block, and there may be empty rows in the last column
        # padded number of questions is the smallest multiple of (num_cols * rows_per_block) >= num_questions
        total_rows = ((num_questions + num_cols * rows_per_block - 1) // (num_cols * rows_per_block)) * rows_per_block

        centers: Dict[Tuple[int, str], Tuple[int, int]] = {}

        for c in range(num_cols):  # column index
            for r in range(total_rows):  # row index within column
                qnum = r + c * total_rows + 1
                if qnum > num_questions:
                    continue

                # Compute vertical position, accounting for blocks of rows_per_block
                block_idx = r // rows_per_block
                row_in_block = r % rows_per_block

                # base_y in normalized coordinates
                y_norm = (
                    self.layout_config.first_row_top
                    + block_idx * (
                        self.layout_config.rows_per_block * self.layout_config.row_spacing
                        + self.layout_config.block_gap
                    )
                    + row_in_block * self.layout_config.row_spacing
                )

                # Horizontal position for this column's 'a' bubble
                x_norm_base = self.layout_config.first_col_left + c * self.layout_config.col_spacing
                for j, key in enumerate(choices):
                    x_norm = x_norm_base + j * self.layout_config.choice_spacing
                    cx = int(x_norm * w)
                    cy = int(y_norm * h)
                    centers[(qnum, key)] = (cx, cy)

        self.diagnostics['bubbles'] = centers

    def _measure_fill_ratio(
        self,
        gray: np.ndarray,
        center: Tuple[int, int],
        radius_px: int,
    ) -> float:
        """
        Measure the fraction of dark pixels inside a circular region around `center`.
        """
        h, w = gray.shape
        cx, cy = center
        if radius_px <= 0:
            return 0.0

        y_min = max(cy - radius_px, 0)
        y_max = min(cy + radius_px, h - 1)
        x_min = max(cx - radius_px, 0)
        x_max = min(cx + radius_px, w - 1)

        patch = gray[y_min:y_max + 1, x_min:x_max + 1]
        if patch.size == 0:
            return 0.0

        # Create circular mask
        yy, xx = np.ogrid[y_min:y_max+1, x_min:x_max+1]
        mask = (xx - cx)**2 + (yy - cy)**2 <= radius_px**2

        if not mask.any():
            return 0.0

        roi = patch[mask]
        # Normalize intensities (0=black, 1=white-ish)
        roi_float = roi.astype(np.float32) / 255.0

        # "Darkness" = 1 - mean intensity
        darkness = 1.0 - float(np.mean(roi_float))
        return darkness

    def _read_bubbles(self) -> Dict[int, str]:
        config = self.layout_config
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape
        bubble_radius = int(config.bubble_radius_frac * min(w, h))

        self._compute_bubble_centers()
        centers = self.diagnostics['bubbles']

        scores: Dict[Tuple[int, str], float] = {}
        for (qnum, key), center in centers.items():
            darkness = self._measure_fill_ratio(gray, center, bubble_radius)
            scores[(qnum, key)] = darkness

        answers: Dict[int, Optional[str]] = {}
        by_question: Dict[int, List[Tuple[str, float]]] = {}

        for (qnum, key), dark in scores.items():
            by_question.setdefault(qnum, []).append((key, dark))

        for qnum, items in by_question.items():
            items.sort(key=lambda kv: kv[1], reverse=True)
            top_key, top_score = items[0]
            runner_up_score = items[1][1] if len(items) > 1 else 0.0
            if (
                top_score >= config.fill_ratio_threshold
                and top_score >= runner_up_score + config.runner_up_margin
            ):
                answers[qnum] = top_key
            else:
                answers[qnum] = None

        self.results['answers'] = answers
        self.diagnostics['bubble_scores'] = scores

    def _read_qr(self):
        """
        Read the QR code from the warped answer-sheet image.
        """
        config = self.layout_config
        detector = cv2.QRCodeDetector()
        h, w = self.img.shape[:2]
        qr_ul = config.qr_upper_left_fracs
        qr_lr = qr_ul[0] + config.qr_size_frac, qr_ul[1] + config.qr_size_frac
        # shift qr_lr so that aspect ratio is 1:1
        x0, x1 = int(qr_ul[0] * w), int(qr_lr[0] * w)
        y0, y1 = int(qr_ul[1] * h), int(qr_lr[1] * h)
        # readjust x1, y1 to ensure square region
        side_len = min(x1 - x0, y1 - y0)
        x1 = x0 + side_len
        y1 = y0 + side_len

        self.diagnostics['qr_crop_region'] = {
            'upper_left': (x0, y0),
            'lower_right': (x1, y1),
        }

        # First: try on the whole image
        data, points, _ = detector.detectAndDecode(self.img)
        if data:
            self.results['version'] = data.strip()
            print(f"QR code detected in full image: {self.results['version']}")
        else:
            # If that fails, try cropping the top-right region where we know the QR lives

            roi = self.img[y0:y1, x0:x1]
            data, points, _ = detector.detectAndDecode(roi)
            if data:
                self.results['version'] = data.strip()
            else:
                raise RuntimeError("Failed to read QR code from answer sheet.")

    def _read_student_id_bubbles(self):
        config = self.layout_config
        num_digits = config.id_num_digits
        h, w = self.img.shape[:2]
        img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)

        bubble_radius = int(config.bubble_radius_frac * min(w, h))

        # Convert normalized coordinates to pixels

        id_bubbles_ul_frac = config.id_bubbles_ul_frac
        id_bubbles_lr_frac = config.id_bubbles_lr_frac
        id_bubbles_ul_px = (int(id_bubbles_ul_frac[0] * w), int(id_bubbles_ul_frac[1] * h))
        id_bubbles_lr_px = (int(id_bubbles_lr_frac[0] * w), int(id_bubbles_lr_frac[1] * h))
        x0, y0 = id_bubbles_ul_px
        x1, y1 = id_bubbles_lr_px
        bw = x1 - x0
        bh = y1 - y0
        id_bubbles_internal_margin_frac = config.id_bubbles_internal_margin_frac
        id_bubbles_internal_ul_px = (
            int((id_bubbles_ul_frac[0] + id_bubbles_internal_margin_frac[0]) * w),
            int((id_bubbles_ul_frac[1] + id_bubbles_internal_margin_frac[1]) * h),
        )
        id_bubbles_internal_lr_px = (
            int((id_bubbles_lr_frac[0] - id_bubbles_internal_margin_frac[0]) * w),
            int((id_bubbles_lr_frac[1] - id_bubbles_internal_margin_frac[1]) * h),
        )
        ix0, iy0 = id_bubbles_internal_ul_px
        ix1, iy1 = id_bubbles_internal_lr_px
        iw = ix1 - ix0
        ih = iy1 - iy0
        id_bubbles_column_interval_px = int(iw/(num_digits-0.5))
        id_bubbles_row_interval_px = int(ih / 10)
        id_bubble_centers_px: Dict[Tuple[int, str], Tuple[int, int]] = {}
        scores: Dict[Tuple[int, str], float] = {}
        for i in range(num_digits):
            cx = bubble_radius + id_bubbles_internal_ul_px[0] + i * id_bubbles_column_interval_px
            for j in range(10):
                cy = bubble_radius + id_bubbles_internal_ul_px[1] + j * id_bubbles_row_interval_px
                id_bubble_centers_px[(i, str(j))] = (cx, cy)
                darkness = self._measure_fill_ratio(img_gray, id_bubble_centers_px[(i, str(j))], bubble_radius)
                scores[(i, str(j))] = darkness

        # Determine filled bubbles per digit position
        id_answers: Dict[int, Optional[str]] = {}
        by_position: Dict[int, List[Tuple[str, float]]] = {}
        for (pos, digit), dark in scores.items():
            by_position.setdefault(pos, []).append((digit, dark))
        for pos, items in by_position.items():
            items.sort(key=lambda kv: kv[1], reverse=True)
            top_digit, top_score = items[0]
            runner_up_score = items[1][1] if len(items) > 1 else 0.0
            if (
                top_score >= config.fill_ratio_threshold
                and top_score >= runner_up_score + config.runner_up_margin
            ):
                id_answers[pos] = top_digit
            else:
                id_answers[pos] = None
        self.results['student_id_bubbles'] = ''.join(x if x is not None else '?' for x in id_answers.values())

        debug_img = self.img.copy()
        # draw a rectangle around the id region
        self.diagnostics['id_bubble_region'] = {
            'upper_left': id_bubbles_ul_px,
            'lower_right': id_bubbles_lr_px,
        }
        self.diagnostics['id_bubble_centers'] = id_bubble_centers_px

    def _read_student_id_ocr(self):
        config = self.layout_config
        num_digits = config.id_num_digits
        model = get_digit_model()
        h, w = self.img.shape[:2]
        img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        confidence_threshold = config.id_ocr_confidence_threshold

        id_digits_ul_frac = config.id_digits_ul_frac
        id_digits_lr_frac = config.id_digits_lr_frac
        id_digits_ul_px = (int(id_digits_ul_frac[0] * w), int(id_digits_ul_frac[1] * h))
        id_digits_lr_px = (int(id_digits_lr_frac[0] * w), int(id_digits_lr_frac[1] * h))
        x0, y0 = id_digits_ul_px
        x1, y1 = id_digits_lr_px
        digits_strip = self.img[y0:y1, x0:x1]
        digits_img_gray = cv2.cvtColor(digits_strip, cv2.COLOR_BGR2GRAY)

        # strip is horizontally divided into num_digits cells, with gaps between them, and no margins
        strip_h, strip_w = digits_img_gray.shape
        gap_size = int(config.id_digits_gap_size_frac * strip_w)
        total_gap_size = int(gap_size * (num_digits - 1))
        cell_w = int((strip_w - total_gap_size) / max(num_digits, 1))
        cell_plus_gap_w = cell_w + gap_size

        digits: list[str] = []

        for i in range(num_digits):
            # Bounds of this box in the strip
            cx0 = int(i * cell_plus_gap_w)
            cx1 = int(cx0 + cell_w)
            cell = digits_img_gray[:, cx0:cx1]

            ch, cw = cell.shape
            if ch <= 0 or cw <= 0:
                digits.append("")
                continue

            # *** Aggressive inner crop to avoid borders ***
            # Ignore 30% margins; adjust if needed.
            margin_y = int(config.id_digits_cell_margin_frac * ch)
            margin_x = int(config.id_digits_cell_margin_frac * cw)
            iy0 = margin_y
            iy1 = ch - margin_y
            ix0 = margin_x
            ix1 = cw - margin_x

            if iy1 <= iy0 or ix1 <= ix0:
                digits.append("")
                continue

            inner = cell[iy0:iy1, ix0:ix1]
            inner = get_centered_padded_digit(inner, pad=5)

            # Run CNN OCR
            digit, conf = ocr_digit_nn(inner, model=model)
            # logger.debug(f"Digit {i}: pred={digit}, conf={conf:.3f}")
            if conf < confidence_threshold:
                digits.append("?")
                if digit == '7':
                    # make a copy of the inner image and rotate it by 180 degrees
                    rotated_inner = cv2.rotate(inner, cv2.ROTATE_180)
                    digit_rot, conf_rot = ocr_digit_nn(rotated_inner, model=model)
                    # logger.debug(f"  Rotated check: pred={digit_rot}, conf={conf_rot:.3f}")
                    if conf_rot >= confidence_threshold and digit_rot == '6':
                        digits[-1] = '9'
            else:
                if digit == '3':
                    # might be an 8 with gaps
                    # make a copy of the inner image and flip it horizontally
                    flipped_inner = cv2.flip(inner, 1)
                    digit_flp, conf_flp = ocr_digit_nn(flipped_inner, model=model)
                    # logger.debug(f"  Flipped check: pred={digit_flp}, conf={conf_flp:.3f}")
                    if conf_flp >= confidence_threshold and digit_flp == '8':
                        digit = '8'
                digits.append(digit)

        # If all blanks, treat as no ID
        if all(d == "" for d in digits):
            self.results['student_id_ocr'] = None
        else:
            self.results['student_id_ocr'] = "".join(d if d else "?" for d in digits)

        # # generate an overlay image for debugging
        # out_path = self.debug_output_path / "student_id_ocr_overlay.png"
        # debug_img = self.img.copy()

        self.diagnostics['id_digits_region'] = {
            'upper_left': id_digits_ul_px,
            'lower_right': id_digits_lr_px,
        }   

        # draw a rectangle around the id region
        # cv2.rectangle(debug_img, id_digits_ul_px, id_digits_lr_px, (0, 255, 0), 2)
        # annotate each digit box with the recognized digit
        id_boxes = {}
        for i in range(num_digits):
            cx0 = int(x0 + i * (cell_w + gap_size))
            cx1 = int(cx0 + cell_w)
            cy0 = y0
            cy1 = y1
            id_boxes[i] = (cx0, cy0, cx1, cy1)
            # digit = self.results.get('student_id_ocr')
            # digit_char = digit[i] if digit and i < len(digit) else "?"
            # cv2.rectangle(debug_img, (cx0, cy0), (cx1, cy1), (0, 255, 0), 1)
            # cv2.putText(
            #     debug_img, digit_char, (cx0 + 5, cy0 + 25),
            #     cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA
            # )
        # cv2.imwrite(str(out_path), debug_img)

        self.diagnostics['id_digit_boxes'] = id_boxes

    def _read_student_id(self):
        """
        Read the student ID from the warped answer-sheet image,
        using both bubble detection and OCR methods.
        """
        self._read_student_id_bubbles()
        self._read_student_id_ocr()