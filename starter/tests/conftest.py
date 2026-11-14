import pytest

from src.models import DocumentPage


def make_page(page: int, text: str, doc: str = "blld-2019", version: str = "2019") -> DocumentPage:
    return DocumentPage(document_id=doc, source=f"{doc}.pdf", page=page, text=text,
                        metadata={"version": version, "printed_page": page + 2,
                                  "is_content": len(text) >= 200, "char_count": len(text)})


@pytest.fixture
def synthetic_pages():
    body1 = "Chương I\nNHỮNG QUY ĐỊNH CHUNG\nĐiều 1. Phạm vi\n" + ("Nội dung điều một. " * 30)
    body2 = ("Tiếp nội dung điều một. " * 10) + "\nĐiều 2. Đối tượng\n" + ("Nội dung điều hai. " * 20)
    body3 = "Chương II\nHỢP ĐỒNG\nĐiều 3. Hợp đồng\n" + ("Nội dung điều ba. " * 30)
    return [make_page(1, body1), make_page(2, body2), make_page(3, body3)]
