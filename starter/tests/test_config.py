from src import config


def test_documents_exist_and_versions():
    ids = [d["document_id"] for d in config.DOCUMENTS]
    assert len(ids) == len(set(ids)) == 2
    for d in config.DOCUMENTS:
        assert (config.DATA_RAW / d["filename"]).exists()
        assert d["version"] in {"2012", "2019"}


def test_constants_from_spec():
    assert config.EMBED_MODEL == "bge-m3" and config.EMBED_DIM == 1024
    assert (config.A_SIZE, config.A_OVERLAP, config.B_MAX) == (800, 100, 1500)
    assert (config.MIN_PAGE_CHARS, config.MIN_EVIDENCE_CHARS, config.TOP_K) == (200, 30, 3)
    assert config.COHERENCE_PAGES == (5, 15, 25, 35, 45)
