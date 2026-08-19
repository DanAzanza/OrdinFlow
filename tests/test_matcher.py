import os

from core.config import AppConfig
from core.matcher import FileSystemRouter


def test_find_existing_folder_by_keywords(tmp_path):
    config = AppConfig()
    config.target_base_dir = str(tmp_path)
    router = FileSystemRouter(config)

    # 1. Matching person and product in folder name
    os.makedirs(tmp_path / "2026-05-12--Software--Mustermann--Erika")
    res1 = router.find_existing_folder_by_keywords(str(tmp_path), ["Mustermann", "Erika", "Software"])
    assert res1 is not None
    assert "Mustermann--Erika" in res1

    # 2. Matching cross-domain invoice / tenant keywords
    os.makedirs(tmp_path / "2026__Rechnungen__Acme_GmbH")
    res2 = router.find_existing_folder_by_keywords(str(tmp_path), ["Rechnungen", "Acme"])
    assert res2 is not None
    assert "Acme_GmbH" in res2

    # 3. Non-matching keywords return None
    res_none = router.find_existing_folder_by_keywords(str(tmp_path), ["NonExistentKeyword"])
    assert res_none is None
