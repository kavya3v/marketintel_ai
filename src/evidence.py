"""Conservative literal matching shared by extraction and verification."""
import re


def normalized(text):
    return ' '.join(text.casefold().split())


def literal_match(value, text):
    value = normalized(value)
    if not value:
        return False
    # Word boundaries alone accept $10 inside $10.99. Numeric punctuation matters.
    return bool(re.search(r'(?<!\w)(?<!\d[.,])' + re.escape(value)
                          + r'(?!\w|[.,]\d)', normalized(text)))
