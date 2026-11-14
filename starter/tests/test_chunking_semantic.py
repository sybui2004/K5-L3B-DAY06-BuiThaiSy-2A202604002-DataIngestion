from src.chunking import build_stream
from src.chunking_extra import semantic, split_sentences
from tests.conftest import make_page


class FakeEmbed:
    """'lương' sentences → [1,0]; everything else → [0,1]. Records every input it sees."""

    def __init__(self):
        self.seen: list[str] = []

    def __call__(self, texts):
        self.seen += texts
        return [[1.0, 0.0] if "lương" in t.lower() else [0.0, 1.0] for t in texts]


PAY = ["Tiền lương được trả đúng hạn cho người lao động. ",
       "Mức lương tối thiểu được quy định theo từng vùng. ",
       "Lương làm thêm giờ được tính cao hơn ngày thường. ",
       "Phụ cấp lương phải ghi rõ trong hợp đồng lao động. "]
LEAVE = ["Người lao động được nghỉ phép hằng năm mười hai ngày. ",
         "Nghỉ tết âm lịch kéo dài năm ngày liên tục. ",
         "Nghỉ việc riêng cần báo trước cho người sử dụng. ",
         "Nghỉ ốm đau phải có xác nhận của cơ sở y tế. "]


def _pages(sentences):
    return [make_page(1, "".join(sentences).strip())]


def test_split_sentences_offsets_cover_text():
    text = "Câu một. Câu hai; câu ba:\nCâu bốn"
    parts = [text[a:b].strip() for a, b in split_sentences(text)]
    assert parts == ["Câu một.", "Câu hai;", "câu ba:", "Câu bốn"]


def test_split_sentences_keeps_article_heading_together():
    text = "Điều 1. Phạm vi điều chỉnh\nBộ luật này quy định tiêu chuẩn."
    parts = [text[a:b].strip() for a, b in split_sentences(text)]
    assert parts[0] == "Điều 1. Phạm vi điều chỉnh"


def test_semantic_cuts_at_topic_change():
    chunks = semantic(_pages(PAY + LEAVE), FakeEmbed(), threshold=0.6, max_size=1500, min_size=0)
    assert len(chunks) == 2
    assert "lương" in chunks[0].text.lower() and "lương" not in chunks[1].text.lower()
    assert "nghỉ" not in chunks[0].text.lower()


def test_semantic_respects_max_size():
    chunks = semantic(_pages(PAY * 6), FakeEmbed(), threshold=0.6, max_size=500)
    assert len(chunks) >= 3 and all(len(c.text) <= 500 for c in chunks)


def test_semantic_embeds_each_sentence_once():
    pages = _pages(PAY + LEAVE)
    stream, _ = build_stream(pages)
    fake = FakeEmbed()
    semantic(pages, fake)
    assert len(fake.seen) == len(split_sentences(stream))


def test_semantic_single_sentence_page():
    chunks = semantic([make_page(1, "lương " * 50)], FakeEmbed())
    assert len(chunks) == 1


def test_semantic_metadata_and_ids():
    chunks = semantic(_pages(PAY + LEAVE), FakeEmbed())
    assert chunks[0].chunk_id == "E:blld-2019:0000"
    assert all(c.metadata["strategy"] == "E" and c.metadata["version"] == "2019" for c in chunks)
    assert chunks[0].metadata["page_start"] == 1 and chunks[0].metadata["content_hash"]


def test_semantic_does_not_cut_below_min_size():
    pages = _pages([PAY[0]] + LEAVE)  # one short 'lương' sentence, then another topic
    assert len(semantic(pages, FakeEmbed(), threshold=0.6, max_size=1500, min_size=0)) == 2
    merged = semantic(pages, FakeEmbed(), threshold=0.6, max_size=1500, min_size=200)
    assert len(merged) == 1 and "lương" in merged[0].text and "nghỉ" in merged[0].text.lower()
