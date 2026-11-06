"""Base models shared across the package.

All quantities are SI and field names carry unit suffixes (`_m`, `_kg`, `_w`, ...), matching
RocketCreater. Angles stay in degrees and say so in their suffix.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True)]
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

UNIT_SUFFIXES = (
    "_m",
    "_m2",
    "_m4",
    "_m3s2",
    "_kg",
    "_s",
    "_w",
    "_wm2",
    "_wm2k4",
    "_j",
    "_jpk",
    "_jpkgk",
    "_k",
    "_deg",
    "_hz",
    "_mps",
    "_bps",
    "_bit",
    "_db",
    "_pa",
    "_ratio",
    "_count",
)


class Frozen(BaseModel):
    """Immutable base model that rejects unknown keys, so typos fail loudly."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Finding(Frozen):
    """One problem found by a deterministic check. `subject` names what it concerns."""

    code: str
    message: str
    subject: str = ""


class Sourced(Frozen):
    """Reference data: it must carry a source URL or be marked provisional."""

    source: str | None = None
    section: str = ""
    provisional: bool = False
    notes: str = ""

    @model_validator(mode="after")
    def _source_or_provisional(self) -> Sourced:
        if self.source is None:
            if not self.provisional:
                raise ValueError("needs a `source` URL or `provisional: true`")
            return self
        if not self.source.startswith(("https://", "http://")):
            raise ValueError(f"`source` must be a URL: {self.source!r}")
        return self
