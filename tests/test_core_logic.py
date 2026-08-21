"""Unit-Tests für Kernlogik: Produkt-Normalisierung, Voting und OCR-Fallback."""

import os
import tempfile

from core.config import AppConfig
from core.processor import DocumentProcessor

# ──────────────────────────────────────────────────────────────
# HIGH VALUE
# ──────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────
# MEDIUM VALUE
# ──────────────────────────────────────────────────────────────


def test_load_from_yaml_creates_default_when_missing(tmp_path):
    """Fehlt die YAML-Datei, wird sie mit Default-Werten erzeugt."""
    config = AppConfig(base_dir=str(tmp_path))
    yaml_path = tmp_path / "settings" / "config.yaml"
    assert not yaml_path.exists()

    config.load_from_yaml()
    assert yaml_path.exists()

    import yaml as _yaml

    data = _yaml.safe_load(yaml_path.read_text())
    assert "llm_backend" in data


def test_setup_paths_creates_directories():
    """setup_paths erzeugt Eingang und Vorgänge automatisch."""
    tmp_dir = tempfile.mkdtemp()
    try:
        config = AppConfig(base_dir=tmp_dir)
        config.setup_paths()
        assert os.path.isdir(config.watch_dir)
        assert os.path.isdir(config.target_base_dir)
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_api_vorgaenge_edit_file_path_traversal_protection(client, tmp_path):
    """Versuch ausserhalb target_base_dir zu schreiben wird blockiert."""
    from routes.state import DashboardState

    # Sichere Basis-Verzeichnis setzen
    safe_base = str(tmp_path / "safe_target")
    os.makedirs(safe_base, exist_ok=True)
    DashboardState.config.target_base_dir = safe_base

    # Erstelle eine Datei DANN versuche ausserhalb zu verschieben
    src_file = tmp_path / "out_of_bounds"  # liegt AUSSERHALB target_base_dir
    src_file.mkdir()
    pdf_src = src_file / "escape.pdf"
    pdf_src.touch()

    response = client.post(
        f"/api/cases/{tmp_path.name}/escape.pdf/edit",
        json={
            "vorname": "Evil",
            "nachname": "Traveller",
            "datum": "2026-07-06",
            "produkt": "Schuhe",
            "document": "TestDoc",
        },
    )
    # Must be safely blocked as not found or access denied (never a 500 crash)
    assert response.status_code in (403, 404)


def test_api_eingang_preview_missing_file_returns_404(client):
    """Preview von nicht vorhandener Datei liefert 404."""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp()
    try:
        from routes.state import DashboardState

        DashboardState.config.watch_dir = tmp
        response = client.get("/api/inbox/preview/nonexistent.pdf")
        assert response.status_code == 404
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_universal_document_router_custom_schema(tmp_path):
    """Testet, dass der Universal Document Router mit frei definierten Feldern (z.B. Kuchen-Rezept) funktioniert."""
    from unittest.mock import patch

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    config.folder_structure = ["Konditorei", "{Kategorie}"]
    config.document_types = {
        "Rezeptur": {
            "classification_desc": "Ein Kuchenrezept.",
            "extraction_fields": {
                "Kategorie": "Welche Art Kuchen",
                "Rezeptname": "Name des Rezepts",
                "Backzeit": "Dauer in Minuten",
            },
            "routing": {"archive": True, "filename_template": "Kuchen__{Rezeptname}__{Backzeit}min"},
        }
    }

    processor = DocumentProcessor(config)
    dummy_file = tmp_path / "watch" / "schoko.pdf"
    dummy_file.write_text("Schokotorte", encoding="utf-8")

    mock_extracted = {
        "Document": "Rezeptur",
        "Kategorie": "Torten",
        "Rezeptname": "Schwarzwälder Kirsch",
        "Backzeit": "45",
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        success = processor.process_and_route_file(str(dummy_file))

    assert success
    expected_folder = tmp_path / "target" / "Konditorei__Torten"
    assert expected_folder.exists()
    files_in_folder = os.listdir(expected_folder)
    assert len(files_in_folder) == 1
    assert "Kuchen__Schwarzwälder Kirsch__45min.pdf" in files_in_folder[0]


def test_universal_document_router_custom_schema_custom_delimiter(tmp_path):
    """Testet Kuchen-Rezepte mit einem benutzerdefinierten Ordner-Delimiter ('++')."""
    from unittest.mock import patch

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    config.folder_delimiter = "++"
    config.folder_structure = ["Konditorei", "{Kategorie}", "{Rezeptname}"]
    config.document_types = {
        "Rezeptur": {
            "classification_desc": "Ein Kuchenrezept.",
            "extraction_fields": {
                "Kategorie": "Welche Art Kuchen",
                "Rezeptname": "Name des Rezepts",
                "Backzeit": "Dauer in Minuten",
            },
            "routing": {"archive": True, "filename_template": "Kuchen++{Rezeptname}++{Backzeit}min"},
        }
    }

    processor = DocumentProcessor(config)
    dummy_file = tmp_path / "watch" / "marmor.pdf"
    dummy_file.write_text("Marmorkuchen", encoding="utf-8")

    mock_extracted = {"Document": "Rezeptur", "Kategorie": "Rührkuchen", "Rezeptname": "Marmorkuchen", "Backzeit": "50"}

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        success = processor.process_and_route_file(str(dummy_file))

    assert success
    expected_folder = tmp_path / "target" / "Konditorei++Rührkuchen++Marmorkuchen"
    assert expected_folder.exists()
    files_in_folder = os.listdir(expected_folder)
    assert len(files_in_folder) == 1
    assert "Kuchen++Marmorkuchen++50min.pdf" in files_in_folder[0]


def test_optional_fields_in_folder_template(tmp_path):
    """Prüft, dass optionale Felder wie 'Titel' bei fehlendem Wert nicht als FEHLT im Ordnernamen erscheinen."""
    from unittest.mock import patch

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)
    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}, {Titel} {Vorname}"]
    config.document_types = {
        "Vertrag": {
            "classification_desc": "Vertragsdokument",
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Titel": "Titel",
                "Datum": "Datum",
                "Produkt": "Produkt",
            },
            "validation": {"optional_fields": ["Titel"]},
            "routing": {"archive": True, "filename_template": "Vertrag__{Produkt}__{Datum}"},
        }
    }

    processor = DocumentProcessor(config)
    dummy_file = tmp_path / "watch" / "vertrag.pdf"
    dummy_file.write_text("Dummy Vertrag", encoding="utf-8")

    mock_extracted = {
        "Document": "Vertrag",
        "Vorname": "Max",
        "Nachname": "Müller",
        "Titel": "[MISSING]",
        "Datum": "2026-07-08",
        "Produkt": "Software",
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        success = processor.process_and_route_file(str(dummy_file))

    assert success
    # Sollte sauber "{Datum}__{Produkt}__{Nachname}, {Vorname}" ergeben ohne doppelte Leerzeichen
    expected_folder = tmp_path / "target" / "2026-07-08__Software__Müller, Max"
    assert expected_folder.exists()


def test_split_multi_documents(tmp_path):
    """Prüft, ob ein Sammel-PDF mit mehreren Dokumenten bei erfolgreicher Validierung aufgeteilt wird."""
    from unittest.mock import patch

    import fitz

    from core.config import AppConfig
    from core.processor import DocumentProcessor

    # Konfiguration vorbereiten
    config = AppConfig()
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.document_types = {
        "Vertrag": {
            "validation": {"signature_required": True},
            "routing": {"archive": True, "filename_template": "{Document}__{Nachname}"},
        },
        "Lieferschein": {
            "validation": {"signature_required": False},
            "routing": {"archive": True, "filename_template": "{Document}__{Nachname}"},
        },
    }

    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    # Erstelle ein 2-seitiges PDF
    pdf_path = os.path.join(config.watch_dir, "sammelscan.pdf")
    doc = fitz.open()
    doc.new_page()  # Seite 1
    doc.new_page()  # Seite 2
    doc.save(pdf_path)
    doc.close()

    processor = DocumentProcessor(config)

    # Mock extraction returning 2 documents
    mock_extracted = {
        "Document": "Vertrag+Lieferschein",
        "Vorname": "Max",
        "Nachname": "Mustermann",
        "Datum": "2026-07-10",
        "Produkt": "Software",
        "Signed": True,
        "page_results": [
            {"Document": "Vertrag", "pages": [1], "Signed": True},
            {"Document": "Lieferschein", "pages": [2], "Signed": False},
        ],
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        success = processor.process_and_route_file(pdf_path, split_multi_documents=True)

    assert success
    assert not os.path.exists(pdf_path)

    target_dir = os.path.join(config.target_base_dir, "2026-07-10__Software__Mustermann__Max")
    assert os.path.exists(target_dir)

    vertrag_path = os.path.join(target_dir, "Vertrag__Mustermann.pdf")
    lieferschein_path = os.path.join(target_dir, "Lieferschein__Mustermann.pdf")

    assert os.path.exists(vertrag_path)
    assert os.path.exists(lieferschein_path)

    doc_rep = fitz.open(vertrag_path)
    assert len(doc_rep) == 1
    doc_rep.close()

    doc_bef = fitz.open(lieferschein_path)
    assert len(doc_bef) == 1
    doc_bef.close()


def test_empty_pages_deleted(tmp_path):
    """Testet, dass leere Seiten gelöscht werden, wenn save_empty_pages=False."""
    from unittest.mock import patch

    import fitz

    from core.config import AppConfig
    from core.processor import DocumentProcessor

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.document_types = {
        "Vertrag": {
            "extraction_fields": {
                "Vorname": "Vorname des Personen",
                "Nachname": "Nachname des Personen",
                "Datum": "Ausstellungsdatum",
                "Produkt": "Produkt",
            },
            "validation": {"signature_required": False},
            "routing": {"archive": True, "filename_template": "{Document}__{Nachname}"},
        }
    }

    # Erstelle ein 3-seitiges PDF
    pdf_path = os.path.join(config.watch_dir, "input.pdf")
    doc = fitz.open()
    doc.new_page()  # Page 1
    doc.new_page()  # Page 2 (will be classified as LEER)
    doc.new_page()  # Page 3
    doc.save(pdf_path)
    doc.close()

    processor = DocumentProcessor(config)

    # Mock _classify_single_page
    mock_classifications = [
        {
            "idx": 0,
            "page_num": 1,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "dummy1",
            "ocr_text": "Vertragstext",
            "doc_type": "Vertrag",
            "matched_name": "Vertrag",
            "matched_info": config.document_types["Vertrag"],
        },
        {
            "idx": 1,
            "page_num": 2,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "dummy2",
            "ocr_text": "",
            "doc_type": "LEER",
            "matched_name": "LEER",
            "matched_info": {},
        },
        {
            "idx": 2,
            "page_num": 3,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "dummy3",
            "ocr_text": "Vertragstext 2",
            "doc_type": "Vertrag",
            "matched_name": "Vertrag",
            "matched_info": config.document_types["Vertrag"],
        },
    ]

    mock_extracted_data = {
        "Document": "Vertrag",
        "Vorname": "Max",
        "Nachname": "Mustermann",
        "Datum": "2026-07-10",
        "Produkt": "Software",
    }

    with (
        patch.object(processor, "_classify_single_page", side_effect=mock_classifications),
        patch.object(processor.llm_extractor, "extract_data_from_images_with_type", return_value=mock_extracted_data),
    ):
        success = processor.process_and_route_file(pdf_path, save_empty_pages=False)

    assert success
    assert not os.path.exists(pdf_path)

    target_dir = os.path.join(config.target_base_dir, "2026-07-10__Software__Mustermann__Max")
    assert os.path.exists(target_dir)

    reconstructed_pdf = os.path.join(target_dir, "Vertrag__Mustermann.pdf")
    assert os.path.exists(reconstructed_pdf)
    assert os.path.exists(reconstructed_pdf)

    # Reconstructed PDF should only have 2 pages (page 2 LEER was deleted)
    doc_check = fitz.open(reconstructed_pdf)
    assert len(doc_check) == 2
    doc_check.close()


def test_all_pages_empty_deleted(tmp_path):
    """Tests that PDF is completely deleted when all pages are empty and save_empty_pages=False."""
    from unittest.mock import patch

    import fitz

    from core.config import AppConfig
    from core.processor import DocumentProcessor

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    # Create a 2-page PDF
    pdf_path = os.path.join(config.watch_dir, "empty.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    processor = DocumentProcessor(config)

    # Mock _classify_single_page to return LEER for all pages
    mock_classifications = [
        {
            "idx": 0,
            "page_num": 1,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "d1",
            "ocr_text": "",
            "doc_type": "LEER",
            "matched_name": "LEER",
            "matched_info": {},
        },
        {
            "idx": 1,
            "page_num": 2,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "d2",
            "ocr_text": "",
            "doc_type": "LEER",
            "matched_name": "LEER",
            "matched_info": {},
        },
    ]

    with patch.object(processor, "_classify_single_page", side_effect=mock_classifications):
        success = processor.process_and_route_file(pdf_path, save_empty_pages=False)

    assert success
    # File must be deleted!
    assert not os.path.exists(pdf_path)


def test_empty_pages_saved(tmp_path):
    """Tests that empty pages are preserved and assigned to surrounding document when save_empty_pages=True."""
    from unittest.mock import patch

    import fitz

    from core.config import AppConfig
    from core.processor import DocumentProcessor

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.document_types = {
        "Rezept": {
            "extraction_fields": {
                "Vorname": "Vorname des Personen",
                "Nachname": "Nachname des Personen",
                "Datum": "Ausstellungsdatum",
                "Produkt": "Produkt",
            },
            "validation": {"signature_required": False},
            "routing": {"archive": True, "filename_template": "{Document}__{Nachname}"},
        }
    }

    # Erstelle ein 3-seitiges PDF
    pdf_path = os.path.join(config.watch_dir, "input.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    processor = DocumentProcessor(config)

    # Mock _classify_single_page: Page 2 is LEER
    mock_classifications = [
        {
            "idx": 0,
            "page_num": 1,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "dummy1",
            "ocr_text": "Rezepttext",
            "doc_type": "Rezept",
            "matched_name": "Rezept",
            "matched_info": config.document_types["Rezept"],
        },
        {
            "idx": 1,
            "page_num": 2,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "dummy2",
            "ocr_text": "",
            "doc_type": "LEER",
            "matched_name": "LEER",
            "matched_info": {},
        },
        {
            "idx": 2,
            "page_num": 3,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "dummy3",
            "ocr_text": "Rezepttext 2",
            "doc_type": "Rezept",
            "matched_name": "Rezept",
            "matched_info": config.document_types["Rezept"],
        },
    ]

    mock_extracted_data = {
        "Document": "Rezept",
        "Vorname": "Max",
        "Nachname": "Mustermann",
        "Datum": "2026-07-10",
        "Produkt": "Einlagen",
    }

    with (
        patch.object(processor, "_classify_single_page", side_effect=mock_classifications),
        patch.object(processor.llm_extractor, "extract_data_from_images_with_type", return_value=mock_extracted_data),
    ):
        success = processor.process_and_route_file(pdf_path, save_empty_pages=True)

    assert success
    assert not os.path.exists(pdf_path)

    target_dir = os.path.join(config.target_base_dir, "2026-07-10__Einlagen__Mustermann__Max")
    assert os.path.exists(target_dir)

    reconstructed_pdf = os.path.join(target_dir, "Rezept__Mustermann.pdf")
    assert os.path.exists(reconstructed_pdf)

    # Reconstructed PDF should have retained all 3 pages
    doc_check = fitz.open(reconstructed_pdf)
    assert len(doc_check) == 3
    doc_check.close()


def test_pure_majority_voting_multipage():
    """Tests weighted fuzzy voting with consensus score K(f) across pages and tiers."""
    from unittest.mock import MagicMock

    from core.config import AppConfig
    from core.extraction_pipeline import ExtractionPipeline

    config = AppConfig()
    pipeline = ExtractionPipeline(config, MagicMock(), MagicMock())

    # 2 pages group
    group_pages = [
        {
            "page_num": 1,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "p1",
            "matched_info": {"extraction_fields": {"Datum": "...", "Nachname": "..."}},
        },
        {
            "page_num": 2,
            "raw_img": None,
            "prep_img": None,
            "b64_img": "p2",
            "matched_info": {"extraction_fields": {"Datum": "...", "Nachname": "..."}},
        },
    ]

    pipeline.llm_extractor.extract_data_from_images_with_type = MagicMock(
        side_effect=[
            {"Datum": "2026-04-10", "Nachname": "Gerbig"},  # Tier 1 Page 1
            {"Datum": "2026-04-10", "Nachname": "Gerbig"},  # Tier 1 Page 2
        ]
    )

    res = pipeline.process_page_group("Fußscan", group_pages)
    assert res is not None
    # Early-stop triggers after Tier 1 since all fields have K >= 0.85
    assert pipeline.llm_extractor.extract_data_from_images_with_type.call_count == 2
    assert res.get("Datum") == "2026-04-10"
    assert res.get("Nachname") == "Gerbig"
    # Confidence metrics are fully populated
    conf = res.get("_confidence", {})
    assert "Datum" in conf
    assert conf["Datum"] == 1.0


def test_boolean_field_voting_consensus():
    """Tests that boolean votes are weighted correctly across tiers and return a boolean."""
    from core.extraction_pipeline import _evaluate_field_consensus

    winner, k_score, counts = _evaluate_field_consensus(
        "Signed", [[{"Signed": True}], [{"Signed": False}], [{"Signed": False}]], ["tier1", "tier2", "tier3"]
    )
    assert winner is False
    assert isinstance(winner, bool)
    assert counts == {True: 1.0, False: 2.75}
    assert round(k_score, 2) == 0.73


def test_ocr_validation_dates_and_phrases():
    """Testet das Voting für Datumswerte und mehrzeilige/mehrwortige Namen."""
    from core.extraction_pipeline import _evaluate_field_consensus

    # Datum
    winner_d, k_score_d, counts_d = _evaluate_field_consensus(
        "Datum",
        [[{"Datum": "15.03.2026"}], [{"Datum": "15.03.2026"}]],
        ["tier1", "text"],
    )
    assert winner_d == "15.03.2026"
    assert counts_d.get("15.03.2026") == 2.0
    assert k_score_d == 1.0

    # Mehrwortiger Name
    winner_n, k_score_n, counts_n = _evaluate_field_consensus(
        "Nachname",
        [[{"Nachname": "Max Mustermann"}], [{"Nachname": "Max Mustermann"}]],
        ["tier1", "text"],
    )
    assert winner_n == "Max Mustermann"
    assert counts_n.get("Max Mustermann") == 2.0
    assert k_score_n == 1.0


def test_canonical_casing_clustering():
    """Testet, dass bei Gruppenmitgliedern die sauberste Groß-/Kleinschreibung gewählt wird."""
    from core.extraction_pipeline import _cluster_votes

    clusters = _cluster_votes([("max mustermann", 1.0), ("Max Mustermann", 1.0)])
    assert len(clusters) == 1
    assert clusters[0]["representative"] == "Max Mustermann"


def test_tiebreaker_target_fields_only():
    """Testet, dass Stufe 3 Tiebreaker nur gezielt die Konfliktfelder an das VLM übergibt."""
    from unittest.mock import MagicMock

    from core.config import AppConfig
    from core.vision import LLMExtractor

    config = AppConfig()
    config.document_types = {
        "TestDoc": {"extraction_fields": {"Vorname": "Vorname", "Nachname": "Nachname", "Geburtsdatum": "Geburtsdatum"}}
    }
    extractor = LLMExtractor(config)
    extractor.find_doc_type_config = MagicMock(return_value=("TestDoc", config.document_types["TestDoc"]))

    mock_api = MagicMock(return_value={"Nachname": "Mustermann"})
    extractor.call_vision_api_json = mock_api

    extractor.extract_data_from_images_with_type("b64_dummy", "TestDoc", target_fields=["Nachname"])

    assert mock_api.called
    payload = mock_api.call_args[0][0]
    messages = payload.get("messages", [])
    user_msg = next((m for m in messages if m.get("role") == "user"), {})
    content = user_msg.get("content", "")
    assert '"Nachname"' in content
    assert '"Vorname"' not in content


def test_stage2_target_fields_only():
    """Testet, dass Stufe 2 nur noch die unsicheren/fehlenden Felder aus Stufe 1 abfragt."""
    from unittest.mock import MagicMock

    from core.config import AppConfig
    from core.extraction_pipeline import ExtractionPipeline

    config = AppConfig()
    config.document_types = {
        "Vertrag": {
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Geburtsdatum": "Geburtsdatum",
            }
        }
    }
    pipeline = ExtractionPipeline(config, MagicMock(), MagicMock())
    group_pages = [
        {
            "page_num": 1,
            "prep_img": None,
            "b64_img": "dummy",
            "ocr_text": "Max Mustermann",
            "matched_info": config.document_types["Vertrag"],
        }
    ]

    # Tier 1 reliably provides first and last name from vision + OCR; birth date is missing ("----")
    # Tier 2 is invoked with target_fields=["Geburtsdatum"]
    recorded_target_fields = []

    def mock_run_tier(group_pages, doc_type, dimension, label, target_fields=None):
        if dimension == config.tier2_dimension:  # Tier 2
            recorded_target_fields.append(target_fields)
            return [{"Geburtsdatum": "15.03.1990"}]
        return [{"Vorname": "Max", "Nachname": "Mustermann", "Geburtsdatum": "----"}]

    pipeline.run_extraction_tier = MagicMock(side_effect=mock_run_tier)
    pipeline.run_text_extraction_tier = MagicMock(return_value=[{"Vorname": "Max", "Nachname": "Mustermann"}])
    res = pipeline.process_page_group("Vertrag", group_pages)

    assert res is not None
    assert recorded_target_fields == [["Geburtsdatum"]]
    assert res.get("Geburtsdatum") == "15.03.1990"


def test_substring_merging_and_ocr_priority():
    """Tests that partial names are merged with compound names, with longest candidate prevailing."""
    from core.extraction_pipeline import _are_similar_or_substring, _cluster_votes

    # 1. Test Substring Check
    assert _are_similar_or_substring("Wannink", "Bramkamp-Wannink") is True
    assert _are_similar_or_substring("Henning", "Henning Bjarne") is True

    # 2. Test Voting Cluster Selection
    votes = [
        ("Bramkamp-Wannink", 1.0),
        ("Bramkamp-Wannink", 1.0),
        ("Wannink", 1.0),
    ]

    clusters = _cluster_votes(votes, threshold=0.85)
    assert len(clusters) == 1
    assert clusters[0]["representative"] == "Bramkamp-Wannink"
