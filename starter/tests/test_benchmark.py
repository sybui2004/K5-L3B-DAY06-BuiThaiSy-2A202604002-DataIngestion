import copy

import pytest

from src.benchmark import validate_questions
from src.evaluation import squash
from tests.conftest import make_page

PAGE_TEXT = "Điều 107. Làm thêm giờ\n" + "Số giờ làm thêm của người lao động không quá 40 giờ trong 01 tháng. " * 4


def _q(i, split="dev", flt=None, question="Mỗi tháng được làm thêm tối đa bao nhiêu giờ?"):
    return {"id": f"q{i:02d}", "split": split, "type": "truc_tiep", "question": question,
            "expected_answer": "40 giờ", "gold_source_id": "blld-2019", "gold_page": 1, "gold_dieu": 107,
            "evidence_quote": "giờ làm thêm của người lao động không quá 40 giờ trong 01 tháng", "alt_gold": [], "filter": flt}


@pytest.fixture
def pages():
    return {"blld-2019": [make_page(1, PAGE_TEXT)], "blld-2012": [make_page(1, PAGE_TEXT, "blld-2012", "2012")]}


@pytest.fixture
def valid():
    qs = [_q(i) for i in range(15)] + [_q(i, "test") for i in range(15, 20)]
    for i in (0, 1, 15):
        qs[i]["filter"] = {"version": "2019"}
        qs[i]["question"] = "Theo Bộ luật 2019, mỗi tháng được làm thêm tối đa bao nhiêu giờ?"
    return qs


def test_squash_tolerates_split_syllables():
    assert squash("ng ười s ử dụng lao động") == squash("Người sử dụng  lao\nđộng")


def test_valid_set_passes(valid, pages):
    assert validate_questions(valid, pages) == []


def test_rejects_unknown_filter_value(valid, pages):
    valid[0]["filter"] = {"version": "2020"}
    assert any("version" in e for e in validate_questions(valid, pages))


def test_rejects_filter_not_in_question(valid, pages):
    valid[1]["question"] = "Mỗi tháng được làm thêm tối đa bao nhiêu giờ?"
    assert any("q01" in e for e in validate_questions(valid, pages))


def test_rejects_short_or_missing_evidence(valid, pages):
    short = copy.deepcopy(valid)
    short[2]["evidence_quote"] = "40 giờ"
    assert any("q02" in e for e in validate_questions(short, pages))
    missing = copy.deepcopy(valid)
    missing[3]["evidence_quote"] = "không quá 300 giờ trong 01 năm đối với ngành dệt"
    assert any("q03" in e for e in validate_questions(missing, pages))


def test_alt_gold_evidence_checked(valid, pages):
    valid[4]["alt_gold"] = [{"source_id": "blld-2012", "page": 1, "dieu": 106, "evidence_quote": "câu không có trong trang này nhé"}]
    assert any("q04" in e for e in validate_questions(valid, pages))


def test_split_and_filter_counts(valid, pages):
    assert validate_questions(valid[1:], pages)  # 14 dev
    no_test_filter = copy.deepcopy(valid)
    no_test_filter[15]["filter"] = None
    no_test_filter[15]["question"] = "Mỗi tháng được làm thêm tối đa bao nhiêu giờ?"
    assert any("test" in e for e in validate_questions(no_test_filter, pages))
