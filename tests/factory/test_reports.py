import pytest

from factory_app.reports import INSUFFICIENT, parse_report

ALLOWED = ("PASS", "CHANGES")


def test_valid_report_parses():
    r = parse_report('VERDICT: CHANGES\n```json\n{"findings": [{"id": "RF-01"}]}\n```\nbody',
                     ALLOWED)
    assert r.ok and r.verdict == "CHANGES" and r.data["findings"][0]["id"] == "RF-01"


@pytest.mark.parametrize("text", [
    "",
    "Looks good to me! PASS",                                   # no verdict line
    "Intro text\nVERDICT: PASS\n```json\n{}\n```",              # verdict not on line 1
    "VERDICT: APPROVED\n```json\n{}\n```",                      # verdict not allowed
    "VERDICT: PASS\nno json here",                              # missing JSON
    "VERDICT: PASS\n```json\n{not json}\n```",                  # broken JSON
    "VERDICT: PASS\n```json\n[1, 2]\n```",                      # not an object
])
def test_unparseable_reports_are_insufficient_evidence_never_pass(text):
    r = parse_report(text, ALLOWED)
    assert r.verdict == INSUFFICIENT and not r.ok and r.error
