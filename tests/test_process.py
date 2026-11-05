from satellitecreator.process import Phase, Review, load_review_specs, review_order


def test_reviews_follow_the_jerg_2_100_order():
    assert review_order() == (Review.MDR, Review.SRR, Review.SDR, Review.PDR, Review.CDR)


def test_reviews_map_to_the_phases_they_close():
    phases = {spec.review: spec.phase for spec in load_review_specs()}

    assert phases == {
        Review.MDR: Phase.PRE_A,
        Review.SRR: Phase.A,
        Review.SDR: Phase.A,
        Review.PDR: Phase.B,
        Review.CDR: Phase.C,
    }


def test_outputs_listed_by_jerg_2_100_are_sourced():
    specs = {spec.review: spec for spec in load_review_specs()}

    assert specs[Review.MDR].outputs == ("ミッション要求書（案）",)
    assert specs[Review.SRR].outputs == ("システム要求書", "運用コンセプト")
    assert specs[Review.SDR].outputs == ("システム仕様書",)
    assert all(specs[item].source for item in (Review.MDR, Review.SRR, Review.SDR))


def test_reviews_without_listed_outputs_are_provisional():
    specs = {spec.review: spec for spec in load_review_specs()}

    assert specs[Review.PDR].provisional
    assert specs[Review.CDR].provisional
