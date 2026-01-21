"""
answer_sheet_reader.py

Tools for reading filled bubbles from the ENGR 131 answer sheet.

Pipeline:
  - Load scanned image
  - Detect 4 corner fiducial dots
  - Warp image to canonical rectangle
  - Compute expected bubble centers from a layout model
  - For each question & choice, measure "ink" in bubble region
  - Decide which choice is filled for each question
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Sequence, Optional, Any
from typing import Sequence
import cv2
import numpy as np
import math

from ...ocr.digit_ocr import ocr_digit_nn, load_digit_model

# Optionally load global model once if you like
_DIGIT_MODEL = None

def get_digit_model():
    global _DIGIT_MODEL
    if _DIGIT_MODEL is None:
        _DIGIT_MODEL = load_digit_model()
    return _DIGIT_MODEL

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
    num_questions: int  # must be provided
    choice_keys: Sequence[str] = ("a", "b", "c", "d")
    num_cols: int = 3

    # --- Vertical structure ---
    rows_per_block: int = 5

    # y-coordinate of the first row's bubbles in *normalized* coordinates
    first_row_top: float = 0.239

    # Vertical spacing between consecutive question rows *within a block*
    row_spacing: float = 0.0257  # tune

    # Extra vertical gap *between* blocks (on top of row_spacing steps)
    block_gap: float = 0.0214    # tune

    # --- Horizontal structure ---

    # x-coordinate of the first column's 'a' bubble (Q1) in normalized coords
    first_col_left: float = 0.3075

    # Horizontal spacing between columns (distance from col c to col c+1
    # for the 'a' bubble of the same row)
    col_spacing: float = 0.181   # tune

    # Horizontal spacing between choices (a->b, b->c, etc.), normalized
    choice_spacing: float = 0.0253

    # --- Bubble reading parameters ---

    # Radius of sampling region as fraction of min(width, height)
    bubble_radius_frac: float = 0.015

    # Darkness threshold to call a bubble filled
    fill_ratio_threshold: float = 0.10

    # runner up margin (relative) to call a bubble filled
    runner_up_margin: float = 0.09

    # --- Student ID reading parameters ---
    id_digits: int = 8
    id_top: float = 0.127      # y of top edge of ID boxes
    id_bottom: float = 0.154   # y of bottom edge of ID boxes
    id_left: float = 0.375     # x of left-most box
    id_right: float = 0.698    # x of right-most box
    gap_size_frac: float = 0.038  # gap between cells as fraction of box width
    cell_margin_frac: float = 0.06  # margin inside each cell for OCR crop
    id_upsample_factor: float = 3.0   # scale factor for resizing
    id_dilate: bool = True            # whether to dilate strokes a bit

    # --- Bubble overlay parameters ---
    overlay_correct_choice_color: Tuple[int, int, int] = (0, 255, 0)  # green
    overlay_incorrect_choice_color: Tuple[int, int, int] = (0, 0, 255)  # red

    # --- Student ID echo overlay parameters ---
    id_echo_textbox = TextBoxConfig(
        box_origin_x_frac=0.2,
        box_origin_y_frac=0.69,
        background_color=(77, 41, 7),  # black
        background_alpha=0.25,  # semi-transparent
        text_color=(25, 230, 255),  # yellow
        text_scale=2.5,
        text_thickness=4,
        box_margin_frac=0.04,  # margin inside box
    )

    score_textbox = TextBoxConfig(
        box_origin_x_frac=0.2,
        box_origin_y_frac=0.75,
        background_color=(77, 41, 7),  # black
        background_alpha=0.25,  # semi-transparent
        text_color=(255, 255, 255),  # white
        text_scale=2.5,
        text_thickness=4,
        box_margin_frac=0.04,  # margin inside box
    )

# ---------------- Fiducial detection & warping ----------------

def find_fiducials(
    img: np.ndarray,
    search_margin_frac: float = 0.06,
    north_offset_frac: float = 0.08,
) -> Dict[str, Tuple[int, int]]:

    h, w = img.shape[:2]
    mf = search_margin_frac
    nof = north_offset_frac

    # Define small search windows near the *physical* page corners
    regions = {
        "nw": (
            slice(0, int((mf+nof) * h)),         # rows
            slice(0, int(mf * w)),         # cols
            (0, 0),                        # reference corner (x_ref, y_ref)
        ),
        "ne": (
            slice(0, int((mf+nof) * h)),
            slice(int((1 - mf) * w), w),
            (w - 1, 0),
        ),
        "sw": (
            slice(int((1 - mf) * h), h),
            slice(0, int(mf * w)),
            (0, h - 1),
        ),
        "se": (
            slice(int((1 - mf) * h), h),
            slice(int((1 - mf) * w), w),
            (w - 1, h - 1),
        ),
    }

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Light background, dark dots/text → invert for contour detection
    _, bin_inv = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    centers: Dict[str, Tuple[int, int]] = {}

    for name, (rs, cs, (x_ref, y_ref)) in regions.items():
        sub = bin_inv[rs, cs]
        contours, _ = cv2.findContours(
            sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            raise RuntimeError(f"No fiducial candidate found in region {name}")

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
            row_offset = rs.start or 0
            col_offset = cs.start or 0
            cx = col_offset + cx_sub
            cy = row_offset + cy_sub

            # Distance from the physical corner
            dx = cx - x_ref
            dy = cy - y_ref
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
            raise RuntimeError(f"No valid fiducial found in region {name}")

        centers[name] = best_center

    if set(centers.keys()) != {"nw", "ne", "sw", "se"}:
        raise RuntimeError("Failed to detect all four fiducials.")

    # print(centers)
    return centers


def debug_fiducials_overlay(
    img: np.ndarray,
    fiducials: dict[str, tuple[int, int]],
    out_path: str = "debug_fiducials.png",
) -> None:
    """
    Draw colored circles at the detected fiducial locations on the original image.
    """
    vis = img.copy()
    colors = {
        "nw": (0, 0, 255),   # red
        "ne": (0, 255, 0),   # green
        "se": (255, 0, 0),   # blue
        "sw": (0, 255, 255), # yellow
    }

    for name, (x, y) in fiducials.items():
        color = colors.get(name, (255, 255, 255))
        cv2.circle(vis, (x, y), 12, color, 3)
        cv2.putText(
            vis,
            name.upper(),
            (x + 5, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )

    cv2.imwrite(out_path, vis)
    print(f"[DEBUG] fiducials overlay written to {out_path}")

def warp_to_canonical(
        img: np.ndarray,
        fiducials: dict[str, tuple[int, int]],
        base_width: int = 1700):
    (nw, ne, sw, se) = fiducials['nw'], fiducials['ne'], fiducials['sw'], fiducials['se']
    pts_src = np.float32([nw, ne, sw, se])

    # approximate physical width/height from the fiducials
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
    warped = cv2.warpPerspective(img, M, (out_w, out_h))
    return warped



# ---------------- Bubble geometry ----------------

def compute_bubble_centers(
    config: LayoutConfig,
    img_shape: Tuple[int, int, int],
) -> Dict[Tuple[int, str], Tuple[int, int]]:
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
    h, w = img_shape[:2]
    N = config.num_questions
    C = config.num_cols
    choices = list(config.choice_keys)

    rows = math.ceil(N / C)

    centers: Dict[Tuple[int, str], Tuple[int, int]] = {}

    for c in range(C):  # column index
        for r in range(rows):  # row index within column
            qnum = r + c * rows + 1
            if qnum > N:
                continue

            # Compute vertical position, accounting for blocks of rows_per_block
            block_idx = r // config.rows_per_block
            row_in_block = r % config.rows_per_block

            # base_y in normalized coordinates
            y_norm = (
                config.first_row_top
                + block_idx * (
                    config.rows_per_block * config.row_spacing
                    + config.block_gap
                )
                + row_in_block * config.row_spacing
            )

            # Horizontal position for this column's 'a' bubble
            x_norm_base = config.first_col_left + c * config.col_spacing

            for j, key in enumerate(choices):
                x_norm = x_norm_base + j * config.choice_spacing
                cx = int(x_norm * w)
                cy = int(y_norm * h)
                centers[(qnum, key)] = (cx, cy)

    return centers

# ---------------- Bubble reading ----------------

def measure_fill_ratio(
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


def read_bubbles_with_debug(
    warped_img: np.ndarray,
    config: LayoutConfig,
    overlay_out_path: Optional[str] = None,
) -> tuple[Dict[int, Optional[str]],
           Dict[tuple, float],
           Dict[tuple, tuple]]:
    """
    Like read_bubbles, but also return raw scores and centers.

    Returns:
      answers, scores, centers
    """
    gray = cv2.cvtColor(warped_img, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape
    bubble_radius = int(config.bubble_radius_frac * min(w, h))

    centers = compute_bubble_centers(config, warped_img.shape)

    scores: Dict[Tuple[int, str], float] = {}
    for (qnum, key), center in centers.items():
        darkness = measure_fill_ratio(gray, center, bubble_radius)
        scores[(qnum, key)] = darkness

    answers: Dict[int, Optional[str]] = {}
    by_question: Dict[int, List[Tuple[str, float]]] = {}

    for (qnum, key), dark in scores.items():
        by_question.setdefault(qnum, []).append((key, dark))

    for qnum, items in by_question.items():
        items.sort(key=lambda kv: kv[1], reverse=True)
        top_key, top_score = items[0]
        runner_up_score = items[1][1] if len(items) > 1 else 0.0
        # print(f"Q{qnum}: top {top_key}={top_score:.3f}, runner-up={runner_up_score:.3f}")
        if (
            top_score >= config.fill_ratio_threshold
            and top_score >= runner_up_score + config.runner_up_margin
        ):
            answers[qnum] = top_key
        else:
            answers[qnum] = None

    # -- debug overlay ---
    if overlay_out_path:
        # Normalize scores to [0,1] for coloring
        all_vals = list(scores.values())
        if all_vals:
            vmin, vmax = min(all_vals), max(all_vals)
            if vmax == vmin:
                vmax = vmin + 1e-6
        else:
            vmin, vmax = 0.0, 1.0
        vis = warped_img.copy()
        for (qnum, key), (cx, cy) in centers.items():
            val = scores.get((qnum, key), 0.0)
            t = (val - vmin) / (vmax - vmin)
            # t=0 => green, t=1 => red
            r = int(255 * t)
            g = int(255 * (1.0 - t))
            b = 0
            color = (b, g, r)

            cv2.circle(vis, (cx, cy), 10, color, 2)
            # label each first-choice bubble with qnum
            if key == config.choice_keys[0]:
                cv2.putText(
                    vis, str(qnum), (cx - 15, cy - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA
                )

        cv2.imwrite(overlay_out_path, vis)
        print(f"[DEBUG] bubble-detection debug overlay written to {overlay_out_path}")

    return answers, scores, centers

def read_qr_label_from_warped(warped_img: np.ndarray) -> Optional[str]:
    """
    Read the QR code from the warped answer-sheet image.

    Returns:
      - The decoded string (e.g. '12345678') if found, or
      - None if no QR code was detected.
    """
    detector = cv2.QRCodeDetector()

    # First: try on the whole image
    data, points, _ = detector.detectAndDecode(warped_img)
    if data:
        return data.strip()

    # If that fails, try cropping the top-right region where we know the QR lives
    h, w = warped_img.shape[:2]
    y0, y1 = 0, int(0.35 * h)     # top 35% of the page
    x0, x1 = int(0.55 * w), w     # right 45% of the page

    roi = warped_img[y0:y1, x0:x1]
    data, points, _ = detector.detectAndDecode(roi)
    if data:
        return data.strip()

    return None

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

def read_student_id_from_warped(
    warped_img: np.ndarray,
    config: LayoutConfig,
    confidence_threshold: float = 0.85,
    debug_overlay_path: Optional[str] = None,
) -> Optional[str]:
    """
    Read the student ID as a sequence of individual digits.

    We assume:
      - There are `config.id_digits` equally spaced boxes in a horizontal row.
      - The row occupies [id_left, id_right] x [id_top, id_bottom] in normalized
        coordinates on the warped page.

    Strategy:
      - Crop the ID strip.
      - Split into `id_digits` vertical cells.
      - For each cell:
          - Crop an INNER region (ignore 25–30% margin to avoid the box edges).
          - Upscale & threshold.
          - Run Tesseract in single-character, digits-only mode.
      - Join digits; unknown digits become "?".
    """

    model = get_digit_model()
    h, w = warped_img.shape[:2]

    # Convert normalized coordinates to pixels
    y0 = int(config.id_top * h)
    y1 = int(config.id_bottom * h)
    x0 = int(config.id_left * w)
    x1 = int(config.id_right * w)

    if y1 <= y0 or x1 <= x0:
        # Misconfigured geometry
        return None

    strip = warped_img[y0:y1, x0:x1]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)

    strip_h, strip_w = gray.shape
    num_digits = config.id_digits
    gap_size = int(config.gap_size_frac * strip_w)
    total_gap_size = int(gap_size * (num_digits - 1))
    cell_w = int((strip_w - total_gap_size) / max(num_digits, 1))
    cell_plus_gap_w = cell_w + gap_size

    digits: list[str] = []

    for i in range(num_digits):
        # Bounds of this box in the strip
        cx0 = int(i * cell_plus_gap_w)
        cx1 = int(cx0 + cell_w)
        cell = gray[:, cx0:cx1]

        ch, cw = cell.shape
        if ch <= 0 or cw <= 0:
            digits.append("")
            continue

        # *** Aggressive inner crop to avoid borders ***
        # Ignore 30% margins; adjust if needed.
        margin_y = int(config.cell_margin_frac * ch)
        margin_x = int(config.cell_margin_frac * cw)
        iy0 = margin_y
        iy1 = ch - margin_y
        ix0 = margin_x
        ix1 = cw - margin_x

        if iy1 <= iy0 or ix1 <= ix0:
            digits.append("")
            continue

        inner = cell[iy0:iy1, ix0:ix1]
        inner = get_centered_padded_digit(inner, pad=5)

        if debug_overlay_path is not None:
            # write per-digit crops for debugging into the debug overlay path's directory
            digit_filepath = debug_overlay_path.replace(".png", f"_id_digit_{i}.png")
            cv2.imwrite(digit_filepath, inner)

        # Run CNN OCR
        digit, conf = ocr_digit_nn(inner, model=model)
        print(f"Digit {i}: pred={digit}, conf={conf:.3f}")
        if conf < confidence_threshold:
            digits.append("?")
            if digit == '7':
                # make a copy of the inner image and rotate it by 180 degrees
                rotated_inner = cv2.rotate(inner, cv2.ROTATE_180)
                digit_rot, conf_rot = ocr_digit_nn(rotated_inner, model=model)
                print(f"  Rotated check: pred={digit_rot}, conf={conf_rot:.3f}")
                if conf_rot >= confidence_threshold and digit_rot == '6':
                    digits[-1] = '9'
        else:
            if digit == '3':
                # might be an 8 with gaps
                # make a copy of the inner image and flip it horizontally
                flipped_inner = cv2.flip(inner, 1)
                digit_flp, conf_flp = ocr_digit_nn(flipped_inner, model=model)
                print(f"  Flipped check: pred={digit_flp}, conf={conf_flp:.3f}")
                if conf_flp >= confidence_threshold and digit_flp == '8':
                    digit = '8'
            digits.append(digit)

    # If all blanks, treat as no ID
    if all(d == "" for d in digits):
        return None

    # Represent unknowns as '?' so you can see where OCR struggled
    return "".join(d if d else "?" for d in digits)

def read_answer_sheet(
    image_path: str,
    layout: LayoutConfig,
    warp_size: Tuple[int, int] = (1700, 2200),
    debug_overlay_path: Optional[str] = None,
) -> Dict:
    """
    Like read_answer_sheet, but also decode the QR version label from the page.

    Returns:
      (answers_dict, version_label_or_None)
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    fid = find_fiducials(img)
    warped = warp_to_canonical(img, fid)

    version_label = read_qr_label_from_warped(warped)
    answers, scores, centers = read_bubbles_with_debug(warped, layout, 
                                                       overlay_out_path=debug_overlay_path)
    student_id = read_student_id_from_warped(warped, layout, debug_overlay_path=debug_overlay_path)
    
    return dict(answers=answers, 
                version_label=version_label, 
                student_id=student_id,
                scores=scores,
                centers=centers,
                warped_image=warped)

def annotate_overlay(
    warped_img: np.ndarray,
    layout: LayoutConfig,
    centers: Dict[tuple, tuple],
    student_id: Optional[str],
    per_question: Dict[int, Dict[str, Any]],
    overlay_path: str,
    num_correct: int,
    num_questions: int,
    score_fraction: float | None,
) -> None:
    
    vis = warped_img.copy()
    if vis.ndim == 2:
        vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)

    h, w = vis.shape[:2]

    for (qnum, key), (cx, cy) in centers.items():
        pq = per_question.get(qnum, {})
        correct = (pq.get("correct") or "").lower()
        detected = (pq.get("detected") or "").lower()

        is_selected = bool(detected) and (detected == key.lower())
        is_correct_choice = bool(correct) and (correct == key.lower())

        correct_color = layout.overlay_correct_choice_color
        incorrect_color = layout.overlay_incorrect_choice_color

        if is_correct_choice:
            cv2.circle(vis, (cx, cy), 20, correct_color, 2)
        elif is_selected:
            cv2.circle(vis, (cx, cy), 20, incorrect_color, 2)

        # label question once at first choice
        if key == layout.choice_keys[0]:
            cv2.putText(
                vis,
                str(qnum),
                (cx - 50, cy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 120, 0),
                1,
                cv2.LINE_AA,
            )

 # ---------------- ID row: outer strip, per-digit boxes, inner OCR regions ----------------
    y0 = int(layout.id_top * h)
    y1 = int(layout.id_bottom * h)
    x0 = int(layout.id_left * w)
    x1 = int(layout.id_right * w)
    # print(f"ID box pixel coords: ({x0}, {y0}) to ({x1}, {y1})")
    if y1 > y0 and x1 > x0:
        # Outer strip in red
        cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 0, 255), 2)

        strip_w = x1 - x0
        num_digits = layout.id_digits
        gap_size = int(layout.gap_size_frac * strip_w)
        total_gap_size = int(gap_size * (num_digits - 1))
        cell_w = int((strip_w - total_gap_size) / max(num_digits, 1))
        cell_plus_gap_w = cell_w + gap_size
        # print(f" ID strip width: {strip_w}, cell width: {cell_w}, gap size: {gap_size}")
        # cell_w = strip_w / max(layout.id_digits, 1)

        # Same margin fraction as in read_student_id_from_warped
        inner_margin_frac = layout.cell_margin_frac

        for i in range(layout.id_digits):
            cx0 = int(x0 + i * cell_plus_gap_w)
            cx1 = int(cx0 + cell_w)
            # print(f" Digit {i}: box pixel coords: ({cx0}, {y0}) to ({cx1}, {y1})")

            # Outer digit box (green)
            cv2.rectangle(vis, (cx0, y0), (cx1, y1), (0, 255, 0), 1)

            # Inner OCR region (cyan), matching the per-digit crop
            box_w = cx1 - cx0
            box_h = y1 - y0
            mx = int(inner_margin_frac * box_w)
            my = int(inner_margin_frac * box_h)
            ix0 = cx0 + mx
            ix1 = cx1 - mx
            iy0 = y0 + my
            iy1 = y1 - my
            if ix1 > ix0 and iy1 > iy0:
                cv2.rectangle(vis, (ix0, iy0), (ix1, iy1), (255, 255, 0), 1)

        if student_id:
            vis = add_text_box(vis, f"ID: {student_id}", config=layout.id_echo_textbox)

    # Compose the text
    if score_fraction is not None and num_questions > 0:
        pct = 100.0 * score_fraction
        text = f"{num_correct}/{num_questions} correct ({pct:.1f}%)"
    else:
        text = f"{num_correct}/{num_questions} correct"

    vis = add_text_box(vis, text, config=layout.score_textbox)

    cv2.imwrite(overlay_path, vis)

def add_text_box(
        image: np.ndarray,
        text: str,
        config: TextBoxConfig = TextBoxConfig(),
        **kwargs) -> np.ndarray:
    
    vis = image.copy()
    h, w = vis.shape[:2]

    fontscale = config.text_scale
    fontthickness = config.text_thickness
    box_margin_frac = config.box_margin_frac
    box_location_x_frac = config.box_origin_x_frac
    box_location_y_frac = config.box_origin_y_frac
    background_color = config.background_color
    background_alpha = config.background_alpha
    text_color = config.text_color
    
    (text_w, text_h), baseline = cv2.getTextSize(
        text,
        fontFace=cv2.FONT_HERSHEY_SIMPLEX,
        fontScale=fontscale,
        thickness=fontthickness,
    )

    box_w = int(text_w * (1 + 2 * box_margin_frac))
    set_margin = int(box_margin_frac * box_w)
    box_h = int(text_h + 2 * set_margin)
    
    x0 = int(box_location_x_frac * w)
    y0 = int(box_location_y_frac * h + box_h)
    x1 = int(x0 + box_w)
    y1 = int(y0 - box_h)
    text_x = x0 + set_margin
    text_y = y0 - set_margin #- baseline

    print(f"Text box coords: ({x0}, {y0}) to ({x1}, {y1}) for text '{text}'")
    overlay = vis.copy()
    cv2.rectangle(
        overlay,
        (x0, y0),
        (x1, y1),
        background_color,
        thickness=-1,
    )
    # Blend box with original for 60% opacity
    alpha = background_alpha
    vis = cv2.addWeighted(overlay, alpha, vis, 1 - alpha, 0)

    # Draw the text on top (white)
    cv2.putText(
        vis,
        text,
        (text_x, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        fontscale,
        text_color,
        fontthickness,
        cv2.LINE_AA,
    )
    return vis
