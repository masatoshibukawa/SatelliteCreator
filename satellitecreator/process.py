"""Development phases and reviews, as defined in `data/process/reviews.yaml`."""

from __future__ import annotations

from enum import StrEnum
from functools import cache

from satellitecreator.loading import load_yaml
from satellitecreator.schema import Sourced


class Phase(StrEnum):
    PRE_A = "pre_a"
    A = "a"
    B = "b"
    C = "c"


class Review(StrEnum):
    MDR = "MDR"
    SRR = "SRR"
    SDR = "SDR"
    PDR = "PDR"
    CDR = "CDR"


class ReviewSpec(Sourced):
    """One review. `phase` is the phase the review closes."""

    review: Review
    phase: Phase
    outputs: tuple[str, ...] = ()


@cache
def load_review_specs() -> tuple[ReviewSpec, ...]:
    return tuple(ReviewSpec(**item) for item in load_yaml("process/reviews.yaml")["reviews"])


def review_order() -> tuple[Review, ...]:
    return tuple(spec.review for spec in load_review_specs())
