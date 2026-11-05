import pytest
from pydantic import ValidationError

from satellitecreator.schema import Frozen, Sourced


class _Sample(Frozen):
    name: str


def test_frozen_model_rejects_mutation():
    sample = _Sample(name="a")

    with pytest.raises(ValidationError):
        sample.name = "b"


def test_frozen_model_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        _Sample(name="a", typo="b")


def test_sourced_accepts_http_url():
    sourced = Sourced(source="https://example.com/doc.pdf", section="6.1")

    assert sourced.provisional is False


def test_sourced_accepts_provisional_without_source():
    assert Sourced(provisional=True).source is None


def test_sourced_rejects_missing_source_when_not_provisional():
    with pytest.raises(ValidationError, match="provisional"):
        Sourced()


def test_sourced_rejects_source_that_is_not_a_url():
    with pytest.raises(ValidationError, match="URL"):
        Sourced(source="some book")
