import cv2
import numpy as np
from scipy.interpolate import RBFInterpolator  # or use cv2's TPS

import logging

logger = logging.getLogger(__name__)

def detect_bubble_centers(img_gray, expected_positions, search_radius=200):
    """
    Find actual bubble centers near expected positions in the roughly-warped image.
    
    Parameters
    ----------
    img_gray : grayscale image after initial 4-corner warp
    expected_positions : list of (x, y) canonical bubble positions
    search_radius : how far to search around each expected position
    
    Returns
    -------
    detected_centers : list of (x, y) actual detected positions
    valid_mask : boolean array indicating which bubbles were successfully detected
    """
    detected_centers = []
    valid_mask = []
    debug_img = img_gray.copy()
    # Threshold to find dark regions (filled bubbles)
    _, binary = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    for ex, ey in expected_positions:
        # Define search ROI
        x1 = max(0, int(ex - search_radius))
        y1 = max(0, int(ey - search_radius))
        x2 = min(binary.shape[1], int(ex + search_radius))
        y2 = min(binary.shape[0], int(ey + search_radius))
        
        roi = binary[y1:y2, x1:x2]
        # draw rectangle for debugging
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (128, 128, 0), 3)
        logger.debug(f'Searching for bubble near ({ex}, {ey}) in ROI ({x1}, {y1}) to ({x2}, {y2})')
        # Find circles in ROI using Hough transform
        circles = cv2.HoughCircles(
            roi, 
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=20,
            param1=50,
            param2=15,
            minRadius=20,
            maxRadius=25
        )
        
        if circles is not None:
            # Take the circle closest to expected center
            circles = circles[0]
            roi_center = (search_radius, search_radius)
            distances = np.sqrt((circles[:, 0] - roi_center[0])**2 + 
                              (circles[:, 1] - roi_center[1])**2)
            best_idx = np.argmin(distances)
            # Convert back to image coordinates
            detected_x = x1 + circles[best_idx, 0]
            detected_y = y1 + circles[best_idx, 1]
            # draw detected circle for debugging
            cv2.circle(debug_img, (int(detected_x), int(detected_y)), int(circles[best_idx, 2]), (230, 230, 10), 2)
            logger.debug(f'Detected bubble at ({detected_x}, {detected_y}) radius {circles[best_idx, 2]} near expected ({ex}, {ey})')
            detected_centers.append((detected_x, detected_y))
            valid_mask.append(True)
        else:
            # Fallback: use expected position
            detected_centers.append((ex, ey))
            valid_mask.append(False)
    
    # save binary image
    cv2.imwrite("debug_bubble_detection.png", debug_img)
    return np.array(detected_centers), np.array(valid_mask)


def thin_plate_spline_warp(img, src_points, dst_points):
    """
    Apply thin-plate spline warp using detected control points.
    This handles non-rigid, local deformations.
    """
    h, w = img.shape[:2]
    
    # Create dense grid of points to warp
    grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
    grid_points = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    
    # Fit RBF interpolator for x and y separately
    rbf_x = RBFInterpolator(dst_points, src_points[:, 0], kernel='thin_plate_spline')
    rbf_y = RBFInterpolator(dst_points, src_points[:, 1], kernel='thin_plate_spline')
    
    # Map grid points
    map_x = rbf_x(grid_points).reshape(h, w).astype(np.float32)
    map_y = rbf_y(grid_points).reshape(h, w).astype(np.float32)
    
    # Remap image
    warped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR)
    return warped


def warp(raw_img, corner_indicials, canonical_corners, canonical_page_dimensions):
    """
    Two-stage warping to handle local page deformations.
    
    Parameters
    ----------
    raw_img : the scanned image with deformations
    corner_indicials : detected (x, y) of 4 corner markers in raw image
    canonical_corners : canonical (x, y) of 4 corner markers
    
    Returns
    -------
    warped : image after two-stage correction
    """
    # h, w = raw_img.shape[:2]
    # camera_matrix = np.array([
    #     [w, 0, w/2],      # fx = image width (reasonable guess)
    #     [0, h, h/2],      # fy = image height
    #     [0, 0, 1]
    # ], dtype=np.float32)

    # # Try typical barrel distortion coefficients
    # # Format: [k1, k2, p1, p2, k3]
    # # k1, k2, k3 = radial distortion
    # # p1, p2 = tangential distortion (usually small)

    # # Start with mild barrel distortion (negative k1)
    # dist_coeffs = np.array([0.2, 0.05, 0, 0, 0], dtype=np.float32)

    # # Undistort the raw image
    # undistorted = cv2.undistort(raw_img, camera_matrix, dist_coeffs)
    # raw_img = undistorted
    # Stage 1: Initial 4-corner homography (your existing approach)
    CANONICAL_PAGE_WIDTH = int(canonical_page_dimensions[0])
    CANONICAL_PAGE_HEIGHT = int(canonical_page_dimensions[1])
    logger.debug(f"Size of raw image: {raw_img.shape[1]}x{raw_img.shape[0]}")
    logger.debug(f"Corner indicials: {corner_indicials}")
    logger.debug(f"Canonical corners: {canonical_corners}")
    logger.debug(f"Canonical page size: {CANONICAL_PAGE_WIDTH}x{CANONICAL_PAGE_HEIGHT}")
    H, _ = cv2.findHomography(corner_indicials, canonical_corners)
    warped = cv2.warpPerspective(raw_img, H, 
                                (CANONICAL_PAGE_WIDTH, CANONICAL_PAGE_HEIGHT))
            # After warping, check how accurate the corners are
    for i, (x_can, y_can) in enumerate(canonical_corners):
        x_actual, y_actual = corner_indicials[i]
        # Apply homography to see where this corner maps
        pt_transformed = cv2.perspectiveTransform(
            np.array([[corner_indicials[i]]], dtype=np.float32), H)[0][0]
        error = np.linalg.norm(pt_transformed - [x_can, y_can])
        logger.debug(f"Corner {i}: canonical ({x_can:.1f}, {y_can:.1f}), "
            f"transformed ({pt_transformed[0]:.1f}, {pt_transformed[1]:.1f}), "
            f"error = {error:.2f} pixels")
    # # Stage 2: Detect bubbles and apply flexible warp
    # gray = cv2.cvtColor(roughly_warped, cv2.COLOR_BGR2GRAY)
    # detected_centers, valid = detect_bubble_centers(
    #     gray, bubble_canonical_positions, search_radius=100
    # )
    
    # logger.debug(f"Detected {valid.sum()} / {len(valid)} bubbles successfully")
    
    # # Use only successfully detected bubbles + corners for control points
    # src_pts = np.vstack([
    #     corner_indicials,  # Keep corners as strong anchors
    #     detected_centers[valid]  # Add detected bubble centers
    # ])
    # dst_pts = np.vstack([
    #     canonical_corners,
    #     np.array(bubble_canonical_positions)[valid]
    # ])

    # logger.debug(f"src {src_pts}, dst {dst_pts}")
    
    # # draw bubble centers for debugging
    # for (x, y), v in zip(detected_centers, valid):
    #     color = (0, 255, 0) if v else (0, 0, 255)
    #     cv2.circle(roughly_warped, (int(x), int(y)), 10, color, 2)

    # # Apply thin-plate spline warp
    # final_warped = thin_plate_spline_warp(raw_img, src_pts, dst_pts)
    
    # return final_warped, roughly_warped, detected_centers, valid
    return warped