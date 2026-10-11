"""
OCR Text Preparation Utility Module.

Provides vendor-independent text cleaning, line-break hyphenation resolution,
header stripping, percentage removal, and ingredient term segmentation.
"""

import re
from typing import List, Tuple

# Common ingredient header labels to strip from raw OCR text
COMMON_HEADERS = [
    r"(?i)^full\s+ingredients?\s+(?:list|statement)?:?",
    r"(?i)^active\s+ingredients?:?",
    r"(?i)^inactive\s+ingredients?:?",
    r"(?i)^other\s+ingredients?:?",
    r"(?i)^key\s+ingredients?:?",
    r"(?i)^ingredients?:?",
    r"(?i)^contains:?",
    r"(?i)^formulated\s+with:?",
    r"(?i)^composition:?",
]

# Regex patterns for cleaning OCR artifacts
PERCENTAGE_PATTERN = re.compile(r"\(?\b\d+(?:\.\d+)?\s*%\s*(?:w/w|v/v|w/v)?\)?", re.IGNORECASE)
HYPHEN_LINEBREAK_PATTERN = re.compile(r"(\w+)\s*[-–—]\s*[\r\n]+\s*(\w+)", re.UNICODE)
MULTIPLE_COMMAS_PATTERN = re.compile(r",\s*,+")
BULLET_PATTERN = re.compile(r"[•\*▪►\-\|]")


def strip_headers(text: str) -> Tuple[str, List[str]]:
    """
    Strips recognized ingredient header prefixes from the beginning or lines of raw OCR text.
    Returns (cleaned_text, list_of_stripped_headers).
    """
    stripped_headers = []
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        stripped_line = line.strip()
        matched_header = False
        for header_pattern in COMMON_HEADERS:
            match = re.match(header_pattern, stripped_line)
            if match:
                header_text = match.group(0)
                stripped_headers.append(header_text)
                stripped_line = stripped_line[match.end():].strip()
                matched_header = True
                break
        if stripped_line:
            cleaned_lines.append(stripped_line)

    return "\n".join(cleaned_lines), stripped_headers


def fix_hyphenated_linebreaks(text: str) -> str:
    """
    Fixes words split by hyphens across line breaks (e.g. 'salicylic-\nacid' -> 'salicylic acid').
    """
    return HYPHEN_LINEBREAK_PATTERN.sub(r"\1 \2", text)


def remove_percentages(text: str) -> str:
    """
    Removes percentage concentration numbers like (5%), 0.5% w/w, 10%.
    """
    return PERCENTAGE_PATTERN.sub("", text)


def clean_ocr_raw_text(raw_text: str) -> Tuple[str, List[str], List[str]]:
    """
    Performs full cleaning sequence on raw OCR text.
    
    Returns:
        (cleaned_full_text, candidate_terms, warnings)
    """
    warnings = []
    if not raw_text or not raw_text.strip():
        return "", [], ["Raw OCR input text is empty."]

    # Step 1: Strip headers
    text_no_headers, headers_found = strip_headers(raw_text)
    if headers_found:
        warnings.append(f"Stripped ingredient header(s): {', '.join(headers_found)}")

    # Step 2: Fix hyphenated line breaks
    text_fixed_hyphens = fix_hyphenated_linebreaks(text_no_headers)

    # Step 3: Remove percentages
    text_no_percentages = remove_percentages(text_fixed_hyphens)

    # Step 4: Clean bullets and noise
    text_no_bullets = BULLET_PATTERN.sub(" ", text_no_percentages)
    text_no_multicommas = MULTIPLE_COMMAS_PATTERN.sub(",", text_no_bullets)

    # Normalize line breaks to commas or spaces where appropriate
    lines = [line.strip() for line in text_no_multicommas.splitlines() if line.strip()]
    unified_text = ", ".join(lines)

    # Step 5: Segment into candidate ingredient terms
    # Primary delimiters: comma, semicolon
    raw_segments = re.split(r"[,;]+", unified_text)
    
    candidate_terms = []
    seen = set()

    for seg in raw_segments:
        # Strip brackets, quotes, extra whitespace, trailing dots
        clean_seg = seg.strip(" \t\n\r.()[]{}'\"`*:-")
        # Remove internal multiple spaces
        clean_seg = re.sub(r"\s+", " ", clean_seg)

        # Skip trivial / non-ingredient text (pure numbers, empty strings, single chars)
        if not clean_seg or len(clean_seg) < 2:
            continue
        if clean_seg.isdigit():
            continue

        if clean_seg.lower() not in seen:
            seen.add(clean_seg.lower())
            candidate_terms.append(clean_seg)

    cleaned_full_text = ", ".join(candidate_terms)
    return cleaned_full_text, candidate_terms, warnings
