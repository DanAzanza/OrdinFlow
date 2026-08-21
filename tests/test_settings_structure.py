import os
import tempfile

import yaml

from core.config import AppConfig


def test_settings_modular_structure():
    tmp_dir = tempfile.mkdtemp()
    try:
        config = AppConfig(base_dir=tmp_dir)

        # 1. Config aus neuem Temp-Ordner laden
        config.load_from_yaml()

        settings_dir = os.path.join(tmp_dir, "settings")
        skills_dir = os.path.join(settings_dir, "skills")
        assert os.path.exists(settings_dir)
        assert os.path.exists(skills_dir)
        assert os.path.exists(os.path.join(settings_dir, "config.yaml"))
        assert hasattr(config, "llm_model_path") and config.llm_model_path != ""
        assert hasattr(config, "mmproj_path") and config.mmproj_path != ""

        # 2. Neuen Dokumententyp hinzufügen und abspeichern
        config.document_types["TestDokument"] = {
            "emoji": "🧪",
            "classification_desc": "Ein Test-Dokument für modulare Einstellungen.",
            "routing": {"archive": True, "filename_template": "Test_{Datum}"},
        }
        config.save_to_yaml()

        test_skill_path = os.path.join(skills_dir, "Inbox Folder Import.yaml")
        assert os.path.exists(test_skill_path)

        with open(test_skill_path, encoding="utf-8") as f:
            skill_data = yaml.safe_load(f)
        assert "document_types" in skill_data
        assert "TestDokument" in skill_data["document_types"]
        assert skill_data["document_types"]["TestDokument"]["emoji"] == "🧪"

        # 3. Zweite Instanz von AppConfig im selben Ordner laden
        config2 = AppConfig(base_dir=tmp_dir)
        config2.load_from_yaml()

        assert "TestDokument" in config2.document_types
        assert config2.document_types["TestDokument"]["emoji"] == "🧪"
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)
