"""
OCR-based value extraction from SAP GUI screenshots, using Tesseract.
Chosen over an AI vision API for three reasons: free with no rate limits,
fully offline (SAP screenshots never leave the machine -- important for
enterprise data policy), and deterministic (no hallucination risk on
numeric values like lock counts).

Includes safe file-stream isolation to prevent Windows file-lock crashes.
"""

import os
import re
import shutil
import pytesseract
from PIL import Image, ImageOps
from dotenv import load_dotenv

load_dotenv()

from utils.logger import get_logger

log = get_logger(__name__, "ocr_extractor")

_configured = False


def _configure_tesseract() -> bool:
    """Locates and configures the tesseract executable binary path."""
    global _configured
    if _configured:
        return True

    # 1. Check environment variable from .env
    env_path = os.getenv("TESSERACT_PATH")
    if env_path and os.path.isfile(env_path):
        pytesseract.pytesseract.tesseract_cmd = env_path
        _configured = True
        return True

    # 2. Check standard user and system installation directories
    candidate_paths = [
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for c_path in candidate_paths:
        if os.path.isfile(c_path):
            pytesseract.pytesseract.tesseract_cmd = c_path
            _configured = True
            log.info(f"Tesseract OCR configured at: {c_path}")
            return True

    # 3. Check system PATH via which
    which_path = shutil.which("tesseract")
    if which_path:
        pytesseract.pytesseract.tesseract_cmd = which_path
        _configured = True
        log.info(f"Tesseract OCR found on system PATH: {which_path}")
        return True

    log.warning("Tesseract binary not found in standard paths. OCR will be bypassed.")
    return False


def _preprocess_for_ocr(image_path: str) -> Image.Image:
    """
    Grayscale + 2x upscale + autocontrast noticeably improves accuracy
    on small, compressed SAP grid fonts.
    Uses context manager to release Windows file locks immediately.
    """
    with Image.open(image_path) as raw_img:
        img = raw_img.convert("L")  # grayscale
        img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
        img = ImageOps.autocontrast(img)
        return img.copy()  # Return an in-memory copy


def run_ocr(image_path: str) -> str:
    """Returns the full OCR text extracted from a screenshot, safely wrapped."""
    if not image_path or not os.path.exists(image_path):
        return ""

    if not _configure_tesseract():
        return ""

    try:
        img = _preprocess_for_ocr(image_path)
        # PSM 6 assumes a single uniform block of text (optimal for tables/screens)
        text = pytesseract.image_to_string(img, config="--psm 6", timeout=10)
        return text or ""
    except Exception as e:
        log.warning(f"OCR processing failed for {image_path}: {e}")
        return ""


def extract_patterns(text: str, patterns: dict) -> dict:
    """
    patterns: {result_key: regex_with_one_capture_group}
    Returns {result_key: matched_value} for every pattern that matched.
    """
    if not text or not patterns:
        return {}

    results = {}
    for key, pattern in patterns.items():
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                results[key] = match.group(1).strip()
        except Exception:
            continue
    return results


def count_date_prefixed_lines(text: str, date_pattern: str = r"^\d{2}\.\d{2}\.\d{4}\b") -> int:
    """Counts lines that start with a date (dd.mm.yyyy) for ST22 dump lists."""
    if not text:
        return 0
    count = 0
    for line in text.splitlines():
        if re.match(date_pattern, line.strip()):
            count += 1
    return count


def count_time_prefixed_rows(text: str, pattern: str = r"\b\d{2}:\d{2}:\d{2}\b") -> int:
    """Counts lines containing a HH:MM:SS time, used for job/queue list rows."""
    if not text:
        return 0
    count = 0
    for line in text.splitlines():
        if re.search(pattern, line):
            count += 1
    return count


def count_spool_rows(text: str) -> int:
    """Counts visible SP01 spool request rows."""
    if not text:
        return 0
    count = 0
    for line in text.splitlines():
        if re.match(r"^\d{4,7}\b", line.strip()):
            count += 1
    return count


def count_occurrences(text: str, keyword: str) -> int:
    """Case-insensitive count of a keyword's occurrences across all lines."""
    if not text or not keyword:
        return 0
    return len(re.findall(re.escape(keyword), text, re.IGNORECASE))


def debug_ocr_dump(image_path: str):
    """Prints the full raw OCR text for a screenshot."""
    text = run_ocr(image_path)
    print(f"\n{'='*60}\nOCR TEXT: {image_path}\n{'='*60}")
    print(text)
    print("=" * 60)