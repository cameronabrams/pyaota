import cv2

def blend_images(img1_path, img2_path, alpha=0.5, output_path=None):
    """
    Blend two images with alpha transparency to see through the top one.

    Args:
        img1_path (str): Path to first image.
        img2_path (str): Path to second image.
        alpha (float, optional): Transparency of first image (0–1, default 0.5).
        output_path (str, optional): Path to save result. If None, displays instead.

    Returns:
        numpy.ndarray: Blended image.
    """
    # Load images
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    
    # Check they loaded
    if img1 is None:
        raise ValueError(f"Could not load {img1_path}")
    if img2 is None:
        raise ValueError(f"Could not load {img2_path}")
    
    # Check same size
    if img1.shape != img2.shape:
        raise ValueError(f"Images must be same size. Got {img1.shape} and {img2.shape}")
    
    # Blend
    overlay = cv2.addWeighted(img1, alpha, img2, 1-alpha, 0)
    
    # Save or display
    if output_path:
        cv2.imwrite(output_path, overlay)
        print(f"Saved to {output_path}")
    else:
        cv2.imshow('Overlay', overlay)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    
    return overlay

# Usage:
# blend_images('image1.png', 'image2.png')  # Display
# blend_images('image1.png', 'image2.png', alpha=0.7, output_path='overlay.png')  # Save