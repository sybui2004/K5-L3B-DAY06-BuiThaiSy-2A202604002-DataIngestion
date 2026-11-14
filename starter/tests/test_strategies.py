from src.strategies import STRATEGIES, ingested_codes


class StubStore:
    def __init__(self, counts):
        self.counts = counts

    def count(self, strategy=None):
        return self.counts[strategy]


def test_registry_codes():
    assert list(STRATEGIES) == list("ABCDEF")


def test_official_flags():
    assert [c for c, s in STRATEGIES.items() if s.official] == ["A", "B", "C"]
    assert [c for c, s in STRATEGIES.items() if s.filter_by_version] == ["C"]


def test_ingested_codes():
    store = StubStore({"A": 5, "B": 0, "C": 2, "D": 0, "E": 0, "F": 9})
    assert ingested_codes(store) == ["A", "C", "F"]
