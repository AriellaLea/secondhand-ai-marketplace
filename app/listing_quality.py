"""Listing quality sub-score and its Hebrew reason (PRD section 6).

The program measures the description length; the model only says whether the
description is about the item in the title. The model writes no Hebrew: a 3B model
slipped Greek and Cyrillic letters into "קטגוריה" every time it wrote it.
"""

from dataclasses import dataclass

# Description length in words: under 3 is missing, from 15 it is detailed.
MISSING_BELOW_WORDS = 3
DETAILED_FROM_WORDS = 15

QUALITY_DETAILED = 25
QUALITY_SHORT = 15
QUALITY_POOR = 5


@dataclass(frozen=True)
class ListingQuality:
    points: int
    reason: str


def score_quality(description: str, matches_title: bool) -> ListingQuality:
    words = len(description.split())
    if words < MISSING_BELOW_WORDS:
        return ListingQuality(QUALITY_POOR, "התיאור חסר או כמעט ריק.")
    if not matches_title:
        return ListingQuality(QUALITY_POOR, "התיאור אינו מתאים לפריט שבכותרת.")
    if words >= DETAILED_FROM_WORDS:
        return ListingQuality(QUALITY_DETAILED, "התיאור מפורט ומתאים לפריט שבכותרת.")
    return ListingQuality(QUALITY_SHORT, "התיאור קצר ומתאים לפריט שבכותרת.")
