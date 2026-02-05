def diagnose_qr_detection(self, img):
    """Diagnose QR code detection issues with detailed logging and visualization."""
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
