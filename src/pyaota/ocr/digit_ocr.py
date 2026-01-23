"""
MNIST-style digit OCR using a CNN.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import cv2
import tensorflow as tf

load_model = tf.keras.models.load_model

_MODEL: Optional[tf.keras.Model] = None

def load_digit_model(model_path: str | Path | None = None) -> tf.keras.Model:
    """
    Load (or reuse) the MNIST-style digit classifier.
    If no model path is provided, use the default model from the package.
    """
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    
    data_dir = files("pyaota") /  "data"
    models_dir = data_dir / "models"
    package_model_path = models_dir / "mnist_digit_cnn.keras"
    if model_path is None:
        model_path = package_model_path
    else:
        model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(
            f"Digit model not found at {model_path}. "
            f"Train it with train_mnist_digit_model.py first."
        )

    _MODEL = load_model(model_path)
    return _MODEL

def preprocess_digit_crop(
    img_gray: np.ndarray,
    target_size: Tuple[int, int] = (28, 28),
) -> np.ndarray:
    """
    Preprocess a grayscale digit crop for the CNN:

      - ensure grayscale
      - threshold to binary (digit strokes dark)
      - resize to target_size
      - normalize to [0, 1]
      - shape: (1, H, W, 1)
    """
    if img_gray.ndim == 3:
        img_gray = cv2.cvtColor(img_gray, cv2.COLOR_BGR2GRAY)

    # Otsu threshold, invert so digit is white on black or vice versa is okay
    _, th = cv2.threshold(
        img_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    resized = cv2.resize(
        th,
        target_size,
        interpolation=cv2.INTER_AREA,
    )

    # Normalize
    norm = resized.astype("float32") / 255.0
    norm = norm[..., None]  # add channel dim
    batch = np.expand_dims(norm, axis=0)
    return batch

def ocr_digit_nn(
    img_gray: np.ndarray,
    model: Optional[tf.keras.Model] = None,
    target_size: Tuple[int, int] = (28, 28),
) -> Tuple[Optional[str], float]:
    """
    Run the CNN digit classifier on a single grayscale crop.

    Returns
    -------
    (digit_str, confidence)
      digit_str: '0'..'9' or None if unreadable
      confidence: softmax probability of the predicted class (0..1)
    """
    if model is None:
        model = load_digit_model()

    batch = preprocess_digit_crop(img_gray, target_size=target_size)
    preds = model.predict(batch, verbose=0)[0]  # shape (10,)
    pred_idx = int(np.argmax(preds))
    confidence = float(preds[pred_idx])

    # You can set a minimum confidence threshold later (e.g., 0.6)
    return str(pred_idx), confidence
