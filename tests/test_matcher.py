import pytest

from core.config import AppConfig
from core.processor import DocumentProcessor


@pytest.fixture
def processor():
    config = AppConfig()
    config.document_types = {
        "Rezept": {
            "routing": {"skip_doctor_name_check": True}
        }
    }
    return DocumentProcessor(config)



def test_person_matching_find_folder(tmp_path):
    import os

    from core.config import AppConfig
    from core.matcher import FileSystemRouter

    config = AppConfig()
    config.target_base_dir = str(tmp_path)
    router = FileSystemRouter(config)

    # Erstelle einen bestehenden Ordner
    os.makedirs(tmp_path / "2024-05-12--Einlagen--Muster--Max")

    # Suche nach derselben Person
    res1 = router.find_existing_person_folder(str(tmp_path), "Muster", "Max")
    assert res1 is not None
    assert "Muster--Max" in res1


