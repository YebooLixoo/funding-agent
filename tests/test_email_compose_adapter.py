from web.services.email_compose_adapter import group_by_source_type


class FakeOpp:
    def __init__(self, source_type, title="t", composite_id="c", **kwargs):
        self.source_type = source_type
        self.title = title
        self.composite_id = composite_id
        for attr in ("url", "deadline", "deadline_type", "opportunity_status",
                     "summary", "funding_amount", "source",
                     "resource_type", "resource_provider", "resource_scale",
                     "allocation_details", "eligibility", "access_url"):
            setattr(self, attr, kwargs.get(attr))


class FakeScore:
    def __init__(self, score=0.5):
        self.relevance_score = score


def test_groups_by_source_type():
    rows = [
        (FakeOpp("government", title="G1"), FakeScore()),
        (FakeOpp("industry", title="I1"), FakeScore()),
        (FakeOpp("compute", title="C1"), FakeScore()),
        (FakeOpp("university", title="U1"), None),
    ]
    out = group_by_source_type(rows)
    assert "government_opps" in out
    assert "industry_opps" in out
    assert "compute_opps" in out
    assert "university_opps" in out
    assert len(out["government_opps"]) == 1
    assert out["government_opps"][0]["title"] == "G1"


def test_missing_source_type_defaults_to_government():
    out = group_by_source_type([(FakeOpp(None, title="X"), FakeScore())])
    assert "government_opps" in out
    assert out["government_opps"][0]["title"] == "X"


def test_score_optional():
    out = group_by_source_type([(FakeOpp("government"), None)])
    assert out["government_opps"][0]["relevance_score"] is None


def test_dict_includes_all_emailer_fields():
    out = group_by_source_type([(FakeOpp("government", title="T", composite_id="cid",
                                          url="https://u", summary="s"), FakeScore(0.7))])
    d = out["government_opps"][0]
    for required in ("composite_id", "title", "url", "deadline", "summary",
                     "funding_amount", "source", "source_type", "deadline_type",
                     "opportunity_status", "relevance_score"):
        assert required in d, f"missing {required}"
