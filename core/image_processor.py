"""
core/image_processor.py

Consolidated image processing for the BM platform.

All image work (validation, compression, face-detection crop) is now in one place.
Models call ImageProcessor.process_profile_photo() and ImageProcessor.process_complaint_photo().
This makes swapping or upgrading the face-detection library a single-file change.

Usage:
    from core.image_processor import ImageProcessor

    processed, error = ImageProcessor.process_profile_photo(upload_file)
    processed, error = ImageProcessor.process_complaint_photo(upload_file)
"""

import io
import os
import logging

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


class ImageProcessor:
    """
    Unified image processing pipeline.

    Methods
    -------
    validate_format(file)           → (is_valid, error)
    compress(pil_image, max_kb)     → ContentFile
    crop_face(pil_image)            → PIL.Image  (center-crop fallback if no face)
    process_profile_photo(file)     → (ContentFile | None, error | None)
    process_complaint_photo(file)   → (ContentFile | None, error | None)
    """

    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    PROFILE_MAX_KB     = 100
    COMPLAINT_MAX_KB   = 75

    # ─── Step 1: Format Validation ────────────────────────────────────────────

    @staticmethod
    def validate_format(file) -> tuple:
        """
        Returns (True, None) if the file extension is allowed,
        or (False, error_message) otherwise.
        """
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ImageProcessor.ALLOWED_EXTENSIONS:
            return False, f"Only {', '.join(ImageProcessor.ALLOWED_EXTENSIONS)} files are allowed."
        return True, None

    # ─── Step 2: Face Detection & Crop ───────────────────────────────────────

    @staticmethod
    def crop_face(pil_image):
        """
        Attempt to detect the largest face in the image and crop a square
        centered on it.  Falls back to a center-square crop if OpenCV is
        unavailable or no face is found.

        Returns a PIL Image (RGB, square).
        """
        try:
            import cv2
            import numpy as np
            from PIL import ImageOps

            pil_image = ImageOps.exif_transpose(pil_image)
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')

            cv_img  = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            gray    = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

            img_w, img_h = pil_image.size

            if len(faces) > 0:
                # Use the largest face
                faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                x, y, w, h = faces[0]
                cx, cy   = x + w // 2, y + h // 2
                sq       = min(int(max(w, h) * 1.5), img_w, img_h)
                left     = max(0, min(cx - sq // 2, img_w - sq))
                top      = max(0, min(cy - sq // 2, img_h - sq))
            else:
                sq   = min(img_w, img_h)
                left = (img_w - sq) // 2
                top  = (img_h - sq) // 2

            return pil_image.crop((left, top, left + sq, top + sq))

        except ImportError:
            logger.info("OpenCV not installed — using center crop.")
        except Exception as exc:
            logger.warning("Face detection failed (%s) — using center crop.", exc)

        # Center-crop fallback
        from PIL import ImageOps
        pil_image = ImageOps.exif_transpose(pil_image)
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        w, h  = pil_image.size
        sq    = min(w, h)
        left  = (w - sq) // 2
        top   = (h - sq) // 2
        return pil_image.crop((left, top, left + sq, top + sq))

    # ─── Step 3: Compression ─────────────────────────────────────────────────

    @staticmethod
    def compress(pil_image, max_kb: int, filename: str) -> ContentFile:
        """
        Compress a PIL Image (RGB) to JPEG under max_kb.

        Phase 1: Shrink pixel dimensions (down to 20% of original) at quality=85.
        Phase 2: Reduce JPEG quality (down to 10) on the smallest accepted size.

        Returns a ContentFile ready to be saved to a model ImageField.
        """
        target_bytes = max_kb * 1024

        def _try(img, quality):
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality, optimize=True, subsampling=0)
            return buf

        scale   = 1.0
        current = pil_image.copy()

        while True:
            buf = _try(current, 85)
            if buf.tell() <= target_bytes or scale <= 0.2:
                break
            scale  -= 0.1
            new_w   = max(int(pil_image.width * scale), 64)
            new_h   = max(int(pil_image.height * scale), 64)
            current = pil_image.resize((new_w, new_h), resample=3)  # 3 = LANCZOS

        if buf.tell() > target_bytes:
            for q in range(80, 9, -5):
                buf = _try(current, q)
                if buf.tell() <= target_bytes:
                    break

        buf.seek(0)
        final_name = os.path.splitext(filename)[0] + '.jpg'
        return ContentFile(buf.read(), name=final_name)

    # ─── Public API ───────────────────────────────────────────────────────────

    @staticmethod
    def process_profile_photo(upload_file) -> tuple:
        """
        Full pipeline for citizen profile photos:
          1. Validate format
          2. Open with Pillow
          3. Detect & crop to face (or center-square)
          4. Compress to ≤ PROFILE_MAX_KB

        Returns (ContentFile, None) on success or (None, error_str) on failure.
        """
        from PIL import Image

        valid, err = ImageProcessor.validate_format(upload_file)
        if not valid:
            return None, err

        try:
            upload_file.seek(0)
            img = Image.open(upload_file)
            img = img.convert('RGB')
        except Exception as exc:
            return None, f"Cannot open image: {exc}"

        try:
            img = ImageProcessor.crop_face(img)
        except Exception as exc:
            logger.warning("crop_face raised: %s", exc)

        try:
            content_file = ImageProcessor.compress(img, ImageProcessor.PROFILE_MAX_KB, upload_file.name)
            return content_file, None
        except Exception as exc:
            return None, f"Compression failed: {exc}"

    @staticmethod
    def process_complaint_photo(upload_file) -> tuple:
        """
        Pipeline for complaint/suggestion proof photos:
          1. Validate format
          2. Open with Pillow
          3. Convert to RGB
          4. Compress to ≤ COMPLAINT_MAX_KB (no crop — keep full scene)

        Returns (ContentFile, None) on success or (None, error_str) on failure.
        """
        from PIL import Image

        valid, err = ImageProcessor.validate_format(upload_file)
        if not valid:
            return None, err

        try:
            upload_file.seek(0)
            img = Image.open(upload_file).convert('RGB')
        except Exception as exc:
            return None, f"Cannot open image: {exc}"

        try:
            content_file = ImageProcessor.compress(img, ImageProcessor.COMPLAINT_MAX_KB, upload_file.name)
            return content_file, None
        except Exception as exc:
            return None, f"Compression failed: {exc}"
