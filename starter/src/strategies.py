"""Single list of chunking strategies shared by the CLI and the demo app."""
from typing import NamedTuple


class StrategyInfo(NamedTuple):
    code: str
    name: str
    description: str
    official: bool          # part of the frozen A/B/C submission
    filter_by_version: bool  # query-time version filter is applied (strategy C)


STRATEGIES: dict[str, StrategyInfo] = {s.code: s for s in (
    StrategyInfo("A", "Fixed-size", "Cửa sổ 800 ký tự, chồng lấn 100", True, False),
    StrategyInfo("B", "Theo Điều", "Một Điều một chunk, Điều dài tách theo khoản", True, False),
    StrategyInfo("C", "B + filter năm", "Dùng chunk của B, lọc theo phiên bản (năm) khi truy vấn", True, True),
    StrategyInfo("D", "Recursive", "Tách theo đoạn → dòng → câu → ký tự (800/100)", False, False),
    StrategyInfo("E", "Semantic", "Cắt chỗ độ tương đồng giữa các câu liền kề giảm", False, False),
    StrategyInfo("F", "Parent-child", "Tìm trên chunk con nhỏ, trả về cả Điều chứa nó", False, False),
)}


def ingested_codes(store) -> list[str]:
    """Strategy codes that already have rows in the store, in registry order."""
    return [code for code in STRATEGIES if store.count(code) > 0]
