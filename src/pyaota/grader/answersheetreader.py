from pathlib import Path
from ..generator.answersheet import LayoutConfig
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
        self.img = None
        self.layout_config = layout_config
        self.debug_output_path = debug_output_dir
        self.results = {}
        self.diagnostics = {'original_size': img.shape[:2]}  # (height, width)
        self.diagnostics['debug_image'] = self.rawimg.copy()
        if not self.debug_output_path.exists():
            self.debug_output_path.mkdir(parents=True, exist_ok=True)

    def _diagnostic_overlay(self):
        # return self.img
        unwarped = cv2.warpPerspective(self.diagnostics['debug_image'], self.diagnostics['warp_matrix_inv'], 
        self.diagnostics['original_size'][::-1])
        return unwarped

    def read(self) -> dict[str, Any]:
        self._find_indicials()
        self._warp_to_canonical()
        self._read_qr()
        self._read_student_id()
        self._read_bubblefield()
        return self.results
        
    def _find_indicials(self):
        """
        Detect indicial markers in the four corners of the answer sheet image.

        Returns a dictionary mapping corner names ('nw', 'ne', 'sw', 'se') to
        (x, y) pixel coordinates of the detected indicials.

        Raises RuntimeError if any indicial cannot be found.
        """
        config = self.layout_config
        img = self.rawimg.copy()
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
        
        indicials = {}
        
        for corner, (x1, y1, x2, y2) in search_regions.items():
            logger.debug(f"Indicial search region {corner}: ({x1}, {y1}) to ({x2}, {y2})")
            # draw the search region on diagnostic image
            if self.diagnostics.get('debug_image') is not None:
                cv2.rectangle(self.diagnostics['debug_image'], (x1, y1), (x2, y2), (255, 0, 0), 2)
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
            if self.diagnostics.get('debug_image') is not None:
                cv2.circle(self.diagnostics['debug_image'], (global_x, global_y), 
                        int(expected_radius_px*2), (0, 255, 0), 4)
        # save the image 
        if self.diagnostics.get('debug_image') is not None:
            debug_img_path = self.debug_output_path / f"indicials.png"
            cv2.imwrite(str(debug_img_path), self.diagnostics['debug_image'])
        self.diagnostics['indicials'] = indicials
        return indicials

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


    # def write_debug_output(self,
    #     version_label: str = None,
    # ):
    #     overlay_path = self.debug_output_path / f"debug_page_{version_label}.png"
    #     overlay_img = self._diagnostic_overlay()
    #     cv2.imwrite(str(overlay_path), overlay_img)
    #     logger.debug(f"Debug overlay written to {overlay_path}")

    # def _diagnostic_overlay(self, version_str: str = None):
    #     config = self.layout_config
    #     out_img = self.img_original.copy()
    #     in_img = self.img.copy()
    #     bubble_radius = int(self.layout_config.bubble_radius_frac * min(in_img.shape[:2]))

    #     local_version_str = version_str
    #     if local_version_str is None:
    #         local_version_str = self.results.get('version', None)
    
    #     # indicials are located in the unwarped image
    #     for name, region in self.diagnostics['indicial_regions'].items():
    #         upper_left = region["upper_left"]
    #         lower_right = region["lower_right"]
    #         cv2.rectangle(
    #             out_img,
    #             upper_left,
    #             lower_right,
    #             (255, 0, 0),
    #             2,
    #         )

    #     colors = {
    #         "nw": (0, 0, 255),   # red
    #         "ne": (0, 255, 0),   # green
    #         "se": (255, 0, 0),   # blue
    #         "sw": (0, 165, 200), # orange
    #     }

    #     for name, (x, y) in self.diagnostics['indicials'].items():
    #         color = colors.get(name, (255, 255, 255))
    #         cv2.circle(out_img, (x, y), 12, color, 3)
    #         cv2.putText(
    #             out_img,
    #             name.upper(),
    #             (x + 5, y - 5),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.6,
    #             color,
    #             2,
    #             cv2.LINE_AA,
    #         )

    #     # output a coordinate grid for debugging but in unwarped coordinates!
    #     grid_color = (200, 200, 200)
    #     h, w = out_img.shape[:2]
    #     dpx = 300/2.54/2 # every 500 mm
    #     for x in range(0, w, int(dpx)):
    #         pts_array = np.array([[[x, 0]], [[x, h]]], dtype=np.float32)
    #         unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #         x_unwrapped_top = int(round(unwrapped_pts[0][0][0], 0))
    #         x_unwrapped_bottom = int(round(unwrapped_pts[1][0][0], 0))
    #         text_x = x_unwrapped_top
    #         cv2.line(out_img, (x_unwrapped_top, 0), (x_unwrapped_bottom, h), grid_color, 1)
    #         # cv2.line(out_img, (x, 0), (x, h), grid_color, 1)
    #         cv2.putText(
    #             out_img,
    #             str(x),
    #             (text_x + 2, 12),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.4,
    #             grid_color,
    #             1,
    #             cv2.LINE_AA,
    #         )
    #     for y in range(0, h, int(dpx)):
    #         pts_array = np.array([[[0, y]], [[w, y]]], dtype=np.float32)
    #         unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #         y_unwrapped_left = int(round(unwrapped_pts[0][0][1], 0))
    #         y_unwrapped_right = int(round(unwrapped_pts[1][0][1], 0))
    #         text_y = y_unwrapped_left
    #         cv2.line(out_img, (0, y_unwrapped_left), (w, y_unwrapped_right), grid_color, 1)
    #         cv2.putText(
    #             out_img,
    #             str(y),
    #             (2, text_y - 2),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.4,
    #             grid_color,
    #             1,
    #             cv2.LINE_AA,
    #         )

    #     # bubble grid located in warped image, so have to unwarp the centers
    #     centers = self.diagnostics['bubbles']
    #     center_coords = list(centers.values())
    #     pts_array = np.array(center_coords, dtype=np.float32).reshape(-1, 1, 2)
    #     unwrapped_center_coords = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #     bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_center_coords]
    #     for (qnum, key), (cx, cy) in zip(centers.keys(), bubble_result_tuples):
    #         ucx, ucy = cx, cy
    #         cv2.circle(out_img, (ucx, ucy), bubble_radius, (0, 255, 0), 2)
    #         cv2.putText(
    #             out_img,
    #             f"{qnum}{key}",
    #             (ucx + 10, ucy - 10),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.5,
    #             (0, 255, 0),
    #             1,
    #             cv2.LINE_AA,
    #         )

    #     # qr region located in warped image, so have to unwarp the corners
    #     qr_crop = self.diagnostics.get('qr_crop_region', None)
    #     if qr_crop is not None:
    #         version_detected = self.results.get('version', 'unknown')
    #         qr_color = (139, 0, 0) # navy blue
    #         ul = qr_crop['upper_left']
    #         lr = qr_crop['lower_right']
    #         ur = (lr[0], ul[1])
    #         ll = (ul[0], lr[1])
    #         pts_array = np.array([ul, ur, lr, ll], dtype=np.float32).reshape(-1, 1, 2)
    #         unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #         qr_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
    #         u_ul, u_ur, u_lr, u_ll = qr_result_tuples
    #         cv2.line(out_img, tuple(u_ul), tuple(u_ur), qr_color, 2)
    #         cv2.line(out_img, tuple(u_ur), tuple(u_lr), qr_color, 2)
    #         cv2.line(out_img, tuple(u_lr), tuple(u_ll), qr_color, 2)
    #         cv2.line(out_img, tuple(u_ll), tuple(u_ul), qr_color, 2)
    #         cv2.putText(
    #             out_img,
    #             f"v{version_detected}",
    #             (u_ul[0], u_ul[1] - 10),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.7,
    #             qr_color,
    #             2,
    #             cv2.LINE_AA,
    #         )

    #     # student id bubble region located in warped image, so have to unwarp the corners
    #     id_bubble_color = (0, 165, 255)  # dark orange
    #     id_bubble_region = self.diagnostics.get('id_bubble_region', None)
    #     if id_bubble_region is not None:
    #         id_detected_digitstr = self.results.get('student_id_bubbles', 'unknown')
    #         id_detected = ''.join([str(d) if d is not None else '?' for d in id_detected_digitstr])
    #         ul = id_bubble_region['upper_left']
    #         lr = id_bubble_region['lower_right']
    #         ur = (lr[0], ul[1])
    #         ll = (ul[0], lr[1])
    #         pts_array = np.array([ul, ur, lr, ll], dtype=np.float32).reshape(-1, 1, 2)
    #         unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #         id_bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
    #         u_ul, u_ur, u_lr, u_ll = id_bubble_result_tuples
    #         cv2.line(out_img, tuple(u_ul), tuple(u_ur), id_bubble_color, 2)
    #         cv2.line(out_img, tuple(u_ur), tuple(u_lr), id_bubble_color, 2)
    #         cv2.line(out_img, tuple(u_lr), tuple(u_ll), id_bubble_color, 2)
    #         cv2.line(out_img, tuple(u_ll), tuple(u_ul), id_bubble_color, 2)
    #         cv2.putText(
    #             out_img,
    #             f"ID: {id_detected}",
    #             (u_ur[0]+10, int(0.5*(u_ur[1] + u_lr[1]))),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             1.5,
    #             id_bubble_color,
    #             2,
    #             cv2.LINE_AA,
    #         )   
    #     id_bubble_centers = self.diagnostics.get('id_bubble_centers', None)
    #     if id_bubble_centers is not None:
    #         center_coords = list(id_bubble_centers.values())
    #         pts_array = np.array(center_coords, dtype=np.float32).reshape(-1, 1, 2)
    #         unwrapped_center_coords = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #         id_bubble_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_center_coords]
    #         for (pos, digit), (cx, cy) in zip(id_bubble_centers.keys(), id_bubble_result_tuples):
    #             u_cx, u_cy = cx, cy
    #             cv2.circle(out_img, (u_cx, u_cy), bubble_radius, id_bubble_color, 2)
    #             cv2.putText(
    #                 out_img,
    #                 f"{pos}{digit}",
    #                 (u_cx + 10, u_cy - 10),
    #                 cv2.FONT_HERSHEY_SIMPLEX,
    #                 0.5,
    #                 id_bubble_color,
    #                 1,
    #                 cv2.LINE_AA,
    #             )

    #     # student id digit boxes located in warped image, so have to unwarp the corners
    #     id_digit_boxes = self.diagnostics.get('id_digit_boxes', None)
    #     if id_digit_boxes is not None:
    #         id_digits_ocr = self.results.get('student_id_ocr', "")
    #         id_digits_color = (0, 0, 139)  # dark red
    #         for i, (cx0, cy0, cx1, cy1) in id_digit_boxes.items():
    #             pts_array = np.array(
    #                 [(cx0, cy0), (cx1, cy0), (cx1, cy1), (cx0, cy1)],
    #                 dtype=np.float32
    #             ).reshape(-1, 1, 2)
    #             unwrapped_pts = cv2.perspectiveTransform(pts_array, self.diagnostics['warp_matrix_inv'])
    #             id_digits_result_tuples = [list(map(lambda x: int(round(x, 0)), pt.tolist()[0])) for pt in unwrapped_pts]
    #             u_ul, u_ur, u_lr, u_ll = id_digits_result_tuples
    #             cv2.line(out_img, tuple(u_ul), tuple(u_ur), id_digits_color, 2)
    #             cv2.line(out_img, tuple(u_ur), tuple(u_lr), id_digits_color, 2)
    #             cv2.line(out_img, tuple(u_lr), tuple(u_ll), id_digits_color, 2)
    #             cv2.line(out_img, tuple(u_ll), tuple(u_ul), id_digits_color, 2)
    #             # put text
    #             cv2.putText(
    #                 out_img,
    #                 f"{id_digits_ocr[i] if i < len(id_digits_ocr) else '?'}",
    #                 (u_ul[0] + 5, u_ul[1] + 25),
    #                 cv2.FONT_HERSHEY_SIMPLEX,
    #                 0.5,
    #                 id_digits_color,
    #                 1,
    #                 cv2.LINE_AA,
    #             )

    #     # bubble scores overlay in warped image, so unwarp the centers
    #     scores = self.diagnostics.get('bubble_scores', {})
    #     # logger.debug(f"Bubble scores: {scores}")
    #     all_vals = list(scores.values())
    #     if all_vals:
    #         vmin, vmax = min(all_vals), max(all_vals)
    #         if vmax == vmin:
    #             vmax = vmin + 1e-6
    #     else:
    #         vmin, vmax = 0.0, 1.0
    #     for (qnum, key), (cx, cy) in zip(centers.keys(), bubble_result_tuples):
    #         val = scores.get((qnum, key), 0.0)
    #         # logger.info(f"Bubble score Q{qnum}{key}: {val:.3f}")
    #         t = (val - vmin) / (vmax - vmin)
    #         # t=0 => green, t=1 => red
    #         r = 0
    #         g = int(255 * (1.0 - t))
    #         b = int(255 * t)
    #         color = (b, g, r)

    #         cv2.circle(out_img, (cx, cy), int(bubble_radius*1.05), color, 3)
    #         # label each first-choice bubble with qnum
    #         if key == config.choice_keys[0]:
    #             cv2.putText(
    #                 out_img, str(qnum), (cx - 15, cy - 12),
    #                 cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA
    #             )

    #     return out_img
    #     # out_img_file = "overlay.png" if local_version_str is None else f"overlay-{local_version_str}.png"
    #     # out_path = self.debug_output_path / out_img_file
    #     # logger.debug(f"indicials overlay written to {out_path}")
    #     # cv2.imwrite(str(out_path), out_img)

    def _warp_to_canonical(self):
        img = self.rawimg
        self.img_original = img.copy()
        self.original_size = img.shape[:2]  # (height, width)
        indicials = self.diagnostics['indicials']

        # Source points: detected indicials in image coordinates
        (nw, ne, sw, se) = indicials['nw'], indicials['ne'], indicials['sw'], indicials['se']
        pts_src = np.float32([nw, ne, sw, se])
        logger.debug(f'WARP TO CANONICAL: source indicials = {pts_src}')
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
        
        pts_dst = np.float32([nw_page, ne_page, sw_page, se_page])
        logger.debug(f'WARP TO CANONICAL: dest indicials = {pts_dst}')
        # Output size: full page dimensions in pixels
        page_width_px = int(config.canonical_width.to('pxl').magnitude)
        page_height_px = int(config.canonical_height.to('pxl').magnitude)
        logger.debug(f'WARP TO CANONICAL: page size = {page_width_px} x {page_height_px} px')
        out_w = page_width_px
        out_h = page_height_px

        # Compute transformation
        M = cv2.getPerspectiveTransform(pts_src, pts_dst)
        M_inv = cv2.getPerspectiveTransform(pts_dst, pts_src)
        
        # Apply warp
        warped = cv2.warpPerspective(img, M, (out_w, out_h))
        
        self.img = warped
        debug_img_path = self.debug_output_path / "warped_page.png"
        cv2.imwrite(str(debug_img_path), self.img)
        # warp the debug image as well, if present
        if self.diagnostics.get('debug_image') is not None:
            debug_warped = cv2.warpPerspective(
                self.diagnostics['debug_image'], M, (out_w, out_h)
            )
            self.diagnostics['debug_image'] = debug_warped
            debug_img_path = self.debug_output_path / "indicials_warped.png"
            cv2.imwrite(str(debug_img_path), self.diagnostics['debug_image'])
        self.diagnostics['warp_matrix'] = M
        self.diagnostics['warp_matrix_inv'] = M_inv
        self.diagnostics['warped_size'] = (out_h, out_w)

    # def _compute_bubble_centers(self):
    #     """
    #     Compute bubble centers (in pixel coordinates of the warped image)
    #     for each (question_number, choice_key), using a column-major layout
    #     with blocks of `rows_per_block` questions and extra gaps between blocks.

    #     Column-major numbering:
    #     - Let rows = ceil(num_questions / num_cols)
    #     - Column 0 has questions 1..rows
    #     - Column 1 has rows+1..2*rows
    #     - etc.
    #     """
    #     img_shape = self.img.shape
    #     h, w = img_shape[:2]
    #     num_questions = self.layout_config.num_questions
    #     choices = list(self.layout_config.choice_keys)
    #     num_cols = self.layout_config.num_cols
    #     rows_per_block = self.layout_config.rows_per_block

    #     # questions are ordered column-wise and grouped into blocks of rows_per_block that cannot be broken except in the very last block of the very last column
    #     # so rows must be a multiple of rows_per_block, and there may be empty rows in the last column
    #     # padded number of questions is the smallest multiple of (num_cols * rows_per_block) >= num_questions
    #     total_rows = ((num_questions + num_cols * rows_per_block - 1) // (num_cols * rows_per_block)) * rows_per_block

    #     centers: Dict[Tuple[int, str], Tuple[int, int]] = {}

    #     for c in range(num_cols):  # column index
    #         for r in range(total_rows):  # row index within column
    #             qnum = r + c * total_rows + 1
    #             if qnum > num_questions:
    #                 continue

    #             # Compute vertical position, accounting for blocks of rows_per_block
    #             block_idx = r // rows_per_block
    #             row_in_block = r % rows_per_block

    #             # base_y in normalized coordinates
    #             y_norm = (
    #                 self.layout_config.first_row_top
    #                 + block_idx * (
    #                     self.layout_config.rows_per_block * self.layout_config.row_spacing
    #                     + self.layout_config.block_gap
    #                 )
    #                 + row_in_block * self.layout_config.row_spacing
    #             )

    #             # Horizontal position for this column's 'a' bubble
    #             x_norm_base = self.layout_config.first_col_left + c * self.layout_config.col_spacing
    #             for j, key in enumerate(choices):
    #                 x_norm = x_norm_base + j * self.layout_config.choice_spacing
    #                 cx = int(x_norm * w)
    #                 cy = int(y_norm * h)
    #                 centers[(qnum, key)] = (cx, cy)

    #     self.diagnostics['bubbles'] = centers

    # def _measure_fill_ratio(
    #     self,
    #     gray: np.ndarray,
    #     center: Tuple[int, int],
    #     radius_px: int,
    # ) -> float:
    #     """
    #     Measure the fraction of dark pixels inside a circular region around `center`.
    #     """
    #     h, w = gray.shape
    #     cx, cy = center
    #     if radius_px <= 0:
    #         return 0.0

    #     y_min = max(cy - radius_px, 0)
    #     y_max = min(cy + radius_px, h - 1)
    #     x_min = max(cx - radius_px, 0)
    #     x_max = min(cx + radius_px, w - 1)

    #     patch = gray[y_min:y_max + 1, x_min:x_max + 1]
    #     if patch.size == 0:
    #         return 0.0

    #     # Create circular mask
    #     yy, xx = np.ogrid[y_min:y_max+1, x_min:x_max+1]
    #     mask = (xx - cx)**2 + (yy - cy)**2 <= radius_px**2

    #     if not mask.any():
    #         return 0.0

    #     roi = patch[mask]
    #     # Normalize intensities (0=black, 1=white-ish)
    #     roi_float = roi.astype(np.float32) / 255.0

    #     # "Darkness" = 1 - mean intensity
    #     darkness = 1.0 - float(np.mean(roi_float))
    #     return darkness


    def _read_bubblefield(self):
        """
        Read all question answers from the bubble field.
        
        Returns a list of answers, one per question.
        Each answer is either a choice key ('a', 'b', 'c', 'd', 'T', 'F') or '?' for unclear/unmarked.
        """
        config = self.layout_config
        
        # Image is already warped to canonical page coordinates
        img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        
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
        
        answers = []
        qidx = 0
        
        debug_image = self.diagnostics.get('debug_image', None)

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
                # if debug_image is not None:
                #     cv2.line(
                #         debug_image,
                #         (x_col_px - 10, y_block_start_px - 10),
                #         (x_col_px + 10, y_block_start_px + 10),
                #         (255, 0, 0),
                #         2
                #     )
                #     cv2.line(
                #         debug_image,
                #         (x_col_px - 10, y_block_start_px + 10),
                #         (x_col_px + 10, y_block_start_px - 10),
                #         (255, 0, 0),
                #         2
                #     )   
                for row in range(blocksize):
                    if qidx >= num_questions:
                        break
                    
                    # Get question type from question list if available
                    if hasattr(config, 'question_list') and config.question_list:
                        q = config.question_list[qidx]
                        qtyp = q.get("type", "mcq").lower()
                    else:
                        qtyp = "mcq"  # Default
                    
                    choices = choice_keys[qtyp]
                    
                    # Calculate row y position
                    y_base_px = y_block_start_px + row * block_row_gap_px
                    
                    # Starting x for choices
                    x_choices_px = x_col_px + block_numbering_gap_px
                    
                    # draw an X in the debug image at the center of the first choice bubble
                    # if debug_image is not None:
                    #     cv2.line(
                    #         debug_image,
                    #         (x_choices_px - 10, y_base_px - 10),
                    #         (x_choices_px + 10, y_base_px + 10),
                    #         (0, 0, 255),
                    #         2
                    #     )
                    #     cv2.line(
                    #         debug_image,
                    #         (x_choices_px - 10, y_base_px + 10),
                    #         (x_choices_px + 10, y_base_px - 10),
                    #         (0, 0, 255),
                    #         2
                    #     )

                    # Check each bubble for this question
                    bubble_fills = []  # (choice_key, fill_percentage)
                    
                    for i, key in enumerate(choices):
                        # Calculate bubble center position
                        x_bubble_px = x_choices_px + i * (block_choice_gap_px + bubble_radius_px * 2)
                        y_bubble_px = y_base_px
                        
                        if debug_image is not None:
                            cv2.circle(
                                debug_image,
                                (x_bubble_px, y_bubble_px),
                                bubble_radius_px,
                                (0, 255, 0),
                                2
                            )

                        # Extract circular region
                        x1 = x_bubble_px - bubble_radius_px
                        x2 = x_bubble_px + bubble_radius_px
                        y1 = y_bubble_px - bubble_radius_px
                        y2 = y_bubble_px + bubble_radius_px
                        
                        if x1 < 0 or y1 < 0 or x2 >= img_gray.shape[1] or y2 >= img_gray.shape[0]:
                            continue
                        
                        bubble_roi = img_gray[y1:y2, x1:x2]
                        
                        # Create circular mask
                        mask = np.zeros_like(bubble_roi, dtype=np.uint8)
                        cv2.circle(mask, (bubble_radius_px, bubble_radius_px), bubble_radius_px, 255, -1)
                        
                        # Calculate fill percentage
                        masked_pixels = bubble_roi[mask > 0]
                        if len(masked_pixels) == 0:
                            continue
                        
                        # Threshold and count dark pixels
                        _, binary = cv2.threshold(masked_pixels, 127, 255, cv2.THRESH_BINARY_INV)
                        fill_pct = np.sum(binary > 0) / len(masked_pixels)
                        bubble_fills.append((key, fill_pct, x_bubble_px, y_bubble_px))
                    
                    # Determine answer based on filled bubbles
                    threshold = config.fill_ratio_threshold
                    filled = [(choice, pct, x, y) for choice, pct, x, y in bubble_fills if pct >= threshold]
                    
                    if len(filled) == 0:
                        answers.append("?")  # No bubble filled
                    elif len(filled) == 1:
                        answers.append(filled[0][0])
                        # draw a slightly enlarged circle around the filled-in choice
                        x, y = filled[0][2], filled[0][3]
                        if debug_image is not None:
                            cv2.circle(
                                debug_image,
                                (x, y),
                                int(bubble_radius_px*1.05),
                                (190, 25, 25),
                                3
                            )
                    else:
                        # Multiple bubbles filled - pick darkest one
                        filled.sort(key=lambda x: x[1], reverse=True)
                        answers.append(filled[0][0])
                        x, y = filled[0][2], filled[0][3]
                        if debug_image is not None:
                            cv2.circle(
                                debug_image,
                                (x, y),
                                int(bubble_radius_px*1.05),
                                (190, 25, 25),
                                3
                            )
                    
                    qidx += 1
        
        self.results['answers'] = answers

    # def _read_bubble_field(self) -> Dict[int, str]:
    #     config = self.layout_config
    #     gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)

    #     h, w = gray.shape
    #     bubble_radius = int(config.bubble_radius_frac * min(w, h))

    #     self._compute_bubble_centers()
    #     centers = self.diagnostics['bubbles']

    #     scores: Dict[Tuple[int, str], float] = {}
    #     for (qnum, key), center in centers.items():
    #         darkness = self._measure_fill_ratio(gray, center, bubble_radius)
    #         scores[(qnum, key)] = darkness

    #     answers: Dict[int, Optional[str]] = {}
    #     by_question: Dict[int, List[Tuple[str, float]]] = {}

    #     for (qnum, key), dark in scores.items():
    #         by_question.setdefault(qnum, []).append((key, dark))

    #     for qnum, items in by_question.items():
    #         items.sort(key=lambda kv: kv[1], reverse=True)
    #         top_key, top_score = items[0]
    #         runner_up_score = items[1][1] if len(items) > 1 else 0.0
    #         if (
    #             top_score >= config.fill_ratio_threshold
    #             and top_score >= runner_up_score + config.runner_up_margin
    #         ):
    #             answers[qnum] = top_key
    #         else:
    #             answers[qnum] = None

    #     self.results['answers'] = answers
    #     self.diagnostics['bubble_scores'] = scores
    def diagnose_qr_detection(self):
        """Diagnose QR code detection issues with detailed logging and visualization."""
        img = self.img.copy()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Check OpenCV version (some versions have bugs)
        logger.info(f"OpenCV version: {cv2.__version__}")
        
        # 2. Try basic detection
        detector = cv2.QRCodeDetector()
        data, points, straight_qrcode = detector.detectAndDecode(img)
        logger.info(f"Basic detection - Data: {data}, Points: {points}")
        
        if points is not None:
            # Draw detected points
            debug_img = img.copy()
            points = points[0].astype(int)
            cv2.polylines(debug_img, [points], True, (0, 255, 0), 3)
            cv2.imwrite('qr_detected.png', debug_img)
            logger.info("QR code detected! Saved debug image.")
            return data
        
        # 3. Try different preprocessing approaches
        preprocessing_methods = {
            'original': gray,
            'otsu_threshold': cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
            'adaptive_mean': cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, 
                                                cv2.THRESH_BINARY, 11, 2),
            'adaptive_gaussian': cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                    cv2.THRESH_BINARY, 11, 2),
            'equalized': cv2.equalizeHist(gray),
            'blur_otsu': cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, 
                                    cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        }
        
        for name, processed in preprocessing_methods.items():
            logger.info(f"Trying preprocessing: {name}")
            
            # Convert back to BGR if needed
            if len(processed.shape) == 2:
                processed_bgr = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
            else:
                processed_bgr = processed
            
            data, points, _ = detector.detectAndDecode(processed_bgr)
            
            if data:
                logger.info(f"SUCCESS with {name}: {data}")
                cv2.imwrite(f'qr_success_{name}.png', processed_bgr)
                return data
            
            # Save failed attempts for inspection
            cv2.imwrite(f'qr_failed_{name}.png', processed)
        
        # 4. Try detect() separately to see if QR is found but not decoded
        logger.info("Trying detect() without decode...")
        retval, points = detector.detect(img)
        if retval:
            logger.info(f"QR code DETECTED but not decoded. Points: {points}")
            debug_img = img.copy()
            if points is not None:
                pts = points[0].astype(int)
                cv2.polylines(debug_img, [pts], True, (255, 0, 0), 3)
                cv2.imwrite('qr_detected_not_decoded.png', debug_img)
        else:
            logger.warning("QR code not even detected")
        
        # 5. Try with different scales
        logger.info("Trying different scales...")
        for scale in [0.5, 0.75, 1.0, 1.5, 2.0]:
            scaled = cv2.resize(img, None, fx=scale, fy=scale)
            data, points, _ = detector.detectAndDecode(scaled)
            if data:
                logger.info(f"SUCCESS at scale {scale}: {data}")
                return data
        
        # 6. Try pyzbar as alternative
        try:
            from pyzbar import pyzbar
            logger.info("Trying pyzbar as alternative...")
            decoded = pyzbar.decode(gray)
            if decoded:
                data = decoded[0].data.decode('utf-8')
                logger.info(f"pyzbar SUCCESS: {data}")
                return data
        except ImportError:
            logger.info("pyzbar not available (pip install pyzbar)")
        
        # 7. Check image statistics
        logger.info(f"Image stats - Mean: {gray.mean():.1f}, Std: {gray.std():.1f}, "
                f"Min: {gray.min()}, Max: {gray.max()}")
        
        logger.error("All QR detection methods failed")
        return None

    def _read_qr(self):
        """
        Read the QR code from the warped answer-sheet image.
        """
        config = self.layout_config
        detector = cv2.QRCodeDetector()
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=0.5, fy=0.5)

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
        # write the debug image
        if self.diagnostics.get('debug_image') is not None:
            debug_img_path = self.debug_output_path / f"qr.png"
            cv2.imwrite(str(debug_img_path), self.diagnostics['debug_image'])
        # self.diagnostics['qr_crop_region'] = {
        #     'upper_left': (x0, y0),
        #     'lower_right': (x1, y1),
        # }

        # First: try on the whole image
        data, points, _ = detector.detectAndDecode(gray)
        if data:
            self.results['version'] = data.strip()
            logger.debug(f"QR code detected in full image: {self.results['version']}")
        else:
            # If that fails, try cropping the top-right region where we know the QR lives

            roi = gray[y0:y1, x0:x1]
            data, points, _ = detector.detectAndDecode(roi)
            if data:
                self.results['version'] = data.strip()
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

    def _read_student_id_bubbles(self):
        config = self.layout_config
        num_digits = config.student_id_num_digits
        
        # Image is already warped to canonical page coordinates
        img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        
        # Convert layout positions from physical units to pixels
        # Match the TikZ coordinate system
        ul_x_px = int(config.student_id_digit_boxes_ul[0].to('pxl').magnitude)
        ul_y_px = int(config.student_id_digit_boxes_ul[1].to('pxl').magnitude)
        box_width_px = int(config.student_id_digit_boxes_box_size[0].to('pxl').magnitude)
        box_height_px = int(config.student_id_digit_boxes_box_size[1].to('pxl').magnitude)
        gap_px = int(config.student_id_digit_boxes_horiz_gap.to('pxl').magnitude)
        vgap_px = int(config.bubble_column_vert_gap.to('pxl').magnitude)
        bubble_radius_px = int(config.bubble_radius.to('pxl').magnitude)
        debug_image = self.diagnostics.get('debug_image', None)
        
        # Spacing between bubble centers (matches TikZ: 2*radius + vgap)
        spacing_px = 2 * bubble_radius_px + vgap_px
        
        id_digits: list[str] = []
        id_bubble_centers_px: Dict[Tuple[int, int], Tuple[int, int]] = {}
        # For each column (i = 1 to num_digits in TikZ)
        for i in range(1, num_digits + 1):
            # Calculate column center x position (matches TikZ: ul_x + (i - 0.5)*(gap+box_width) - bubble_radius)
            col_center_x = ul_x_px + int(round((i-1) * (gap_px + box_width_px))) + int(np.round(0.5 * box_width_px))
            
            # Check each bubble (0-9) in this column
            bubble_fills: list[Tuple[int, float]] = []  # (digit, fill_percentage)
            
            for j in range(10):
                # Calculate bubble center y position (matches TikZ: ul_y - box_height - spacing * j)
                bubble_center_y = ul_y_px + box_height_px + vgap_px + bubble_radius_px + spacing_px * j
                
                # draw a circle at the bubble center for diagnostics
                if debug_image is not None:
                    cv2.circle(
                        debug_image,
                        (col_center_x, bubble_center_y),
                        bubble_radius_px,
                        (0, 255, 0),
                        2,
                    )

                id_bubble_centers_px[(i, j)] = (col_center_x, bubble_center_y)

                # Extract circular region around bubble center
                x1 = col_center_x - bubble_radius_px
                x2 = col_center_x + bubble_radius_px
                y1 = bubble_center_y - bubble_radius_px
                y2 = bubble_center_y + bubble_radius_px
                
                if x1 < 0 or y1 < 0 or x2 >= img_gray.shape[1] or y2 >= img_gray.shape[0]:
                    continue
                    
                bubble_roi = img_gray[y1:y2, x1:x2]
                
                # Create circular mask
                mask = np.zeros_like(bubble_roi, dtype=np.uint8)
                cv2.circle(mask, (bubble_radius_px, bubble_radius_px), bubble_radius_px, 255, -1)
                
                # Calculate fill percentage (darker = more filled)
                masked_pixels = bubble_roi[mask > 0]
                if len(masked_pixels) == 0:
                    continue
                
                # Threshold and count dark pixels
                _, binary = cv2.threshold(masked_pixels, 127, 255, cv2.THRESH_BINARY_INV)
                fill_pct = np.sum(binary > 0) / len(masked_pixels)
                bubble_fills.append((j, fill_pct, col_center_x, bubble_center_y))
            
            # Find most filled bubble above threshold
            threshold = config.fill_ratio_threshold
            filled = [(d, f, x, y) for d, f, x, y in bubble_fills if f >= threshold]
            
            if len(filled) == 0:
                id_digits.append("?")  # No bubble filled
            elif len(filled) == 1:
                id_digits.append(str(filled[0][0]))
                x, y = filled[0][2], filled[0][3]
                if debug_image is not None:
                    cv2.circle(
                        debug_image,
                        (x, y),
                        int(bubble_radius_px*1.05),
                        (195, 25, 25),
                        3,
                    )
            else:
                # Multiple bubbles filled - pick darkest one
                filled.sort(key=lambda x: x[1], reverse=True)
                id_digits.append(str(filled[0][0]))
                x, y = filled[0][2], filled[0][3]
                if debug_image is not None:
                    cv2.circle(
                        debug_image,
                        (x, y),
                        int(bubble_radius_px*1.05),
                        (195, 25, 25),
                        3,
                    )
        
        # If all blanks, treat as no ID
        if all(d == "?" for d in id_digits):
            self.results['student_id_bubbles'] = None
        else:
            self.results['student_id_bubbles'] = "".join(id_digits)

        self.diagnostics['id_bubble_centers'] = id_bubble_centers_px

    def _read_student_id_ocr(self):
        config = self.layout_config
        num_digits = config.student_id_num_digits
        model = get_digit_model()
        
        # Image is already warped to canonical page coordinates
        img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        confidence_threshold = config.student_id_ocr_confidence_threshold

        # Convert layout positions from physical units to pixels
        id_box_ul_px = (
            int(config.student_id_digit_boxes_ul[0].to('pxl').magnitude),
            int(config.student_id_digit_boxes_ul[1].to('pxl').magnitude)
        )
        # write an X at the upper-left corner for diagnostics
        debug_image = self.diagnostics.get('debug_image', None)
        if debug_image is not None:
            cv2.line(
                debug_image,
                (id_box_ul_px[0] - 10, id_box_ul_px[1] - 10),
                (id_box_ul_px[0] + 10, id_box_ul_px[1] + 10),
                (34, 122, 255),
                3,
            )
            cv2.line(
                debug_image,
                (id_box_ul_px[0] - 10, id_box_ul_px[1] + 10),
                (id_box_ul_px[0] + 10, id_box_ul_px[1] - 10),
                (34, 122, 255),
                3,
            )
        box_width_px = int(config.student_id_digit_boxes_box_size[0].to('pxl').magnitude)
        box_height_px = int(config.student_id_digit_boxes_box_size[1].to('pxl').magnitude)
        gap_px = int(config.student_id_digit_boxes_horiz_gap.to('pxl').magnitude)
        
        x0, y0 = id_box_ul_px
        
        digits: list[str] = []

        outer_boxes = []
        inner_boxes = []

        for i in range(num_digits):
            # Calculate this box's position
            box_x0 = x0 + i * (box_width_px + gap_px)
            box_x1 = box_x0 + box_width_px
            box_y0 = y0
            box_y1 = y0 + box_height_px
            # draw this box for diagnostics
            debug_image = self.diagnostics.get('debug_image', None)
            if debug_image is not None:
                cv2.rectangle(
                    debug_image,
                    (box_x0, box_y0),
                    (box_x1, box_y1),
                    (255, 0, 0),
                    3,
                )
            outer_boxes.append((box_x0, box_y0, box_x1, box_y1))
            # Extract cell
            cell = img_gray[box_y0:box_y1, box_x0:box_x1]
            
            ch, cw = cell.shape
            if ch <= 0 or cw <= 0:
                digits.append("")
                continue

            # Inner crop to avoid borders
            margin_y = int(config.student_id_digits_cell_margin_frac * ch)
            margin_x = int(config.student_id_digits_cell_margin_frac * cw)
            iy0 = box_y0 + margin_y
            iy1 = box_y0 + ch - margin_y
            ix0 = box_x0 + margin_x
            ix1 = box_x0 + cw - margin_x

            if iy1 <= iy0 or ix1 <= ix0:
                digits.append("")
                continue

            inner = img_gray[iy0:iy1, ix0:ix1]
            inner_boxes.append((ix0, iy0, ix1, iy1))
            debug_image = self.diagnostics.get('debug_image', None)
            if debug_image is not None:
                logger.debug(f'ID OCR: digit {i+1}, outer box=({box_x0},{box_y0})-({box_x1},{box_y1}), inner box=({ix0},{iy0})-({ix1},{iy1})')
                cv2.rectangle(
                    debug_image,
                    (ix0, iy0),
                    (ix1, iy1),
                    (0, 0, 255),
                    3,
                )
            inner = get_centered_padded_digit(inner, pad=5)

            # Run CNN OCR
            digit, conf = ocr_digit_nn(inner, model=model)
            
            if conf < confidence_threshold:
                digits.append("?")
                if digit == '7':
                    # Check if it's actually a 9 written upside down
                    rotated_inner = cv2.rotate(inner, cv2.ROTATE_180)
                    digit_rot, conf_rot = ocr_digit_nn(rotated_inner, model=model)
                    if conf_rot >= confidence_threshold and digit_rot == '6':
                        digits[-1] = '9'
            else:
                if digit == '3':
                    # Might be an 8 with gaps
                    flipped_inner = cv2.flip(inner, 1)
                    digit_flp, conf_flp = ocr_digit_nn(flipped_inner, model=model)
                    if conf_flp >= confidence_threshold and digit_flp == '8':
                        digit = '8'
                digits.append(digit)

        # If all blanks, treat as no ID
        if all(d == "" for d in digits):
            self.results['student_id_ocr'] = None
        else:
            self.results['student_id_ocr'] = "".join(d if d else "?" for d in digits)

        self.diagnostics['id_digit_outer_boxes'] = outer_boxes
        self.diagnostics['id_digit_inner_boxes'] = inner_boxes

    def _read_student_id(self):
        """
        Read the student ID from the warped answer-sheet image,
        using both bubble detection and OCR methods.
        """
        self._read_student_id_bubbles()
        self._read_student_id_ocr()