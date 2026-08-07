import os
from unittest.mock import patch

import pytest

from core.config import AppConfig
from core.processor import DocumentProcessor


@pytest.fixture
def processor(tmp_path):
    config = AppConfig()
    config.watch_dir = str(tmp_path / "watch")
    config.target_base_dir = str(tmp_path / "target")
    os.makedirs(config.watch_dir, exist_ok=True)
    os.makedirs(config.target_base_dir, exist_ok=True)

    config.document_types = {
        "Vertrag": {
            "classification_desc": "Ein rechtlicher Vertrag.",
            "extraction_fields": {
                "Vorname": "Vorname des Unterzeichners",
                "Nachname": "Nachname des Unterzeichners",
                "Datum": "Ausstellungsdatum im Format YYYY-MM-DD",
                "Produkt": "Welches Produkt (z.B. Software, Hardware, Dienstleistung)",
                "Signed": "true, wenn eine handschriftliche Unterschrift vorhanden ist, sonst false"
            },
            "validation": {
                "signature_required": True
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum",
                    "produkt": "Produkt"
                },
                "folder_date_fallback": "----",
                "filename_template": "Vertrag--{Produkt}--{Datum}"
            }
        },
        "Lieferschein": {
            "classification_desc": "Ein Lieferschein oder Übergabeprotokoll.",
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Datum": "Datum",
                "Produkt": "Produkt"
            },
            "validation": {
                "signature_required": False
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum",
                    "produkt": "Produkt"
                },
                "filename_template": "Lieferschein--{Produkt}--{Datum}"
            }
        },
        "Datenschutzerklärung": {
            "classification_desc": "Datenschutzerklärung.",
            "dependent": True,
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Datum": "Datum",
                "Signed": "true/false"
            },
            "validation": {
                "signature_required": True,
                "signature_only": True
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum"
                },
                "filename_template": "Datenschutz--{Nachname}_{Vorname}--{Datum}"
            }
        },
        "Kostenaufstellung": {
            "classification_desc": "Kostenaufstellung.",
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Datum": "Datum",
                "Produkt": "Produkt",
                "Signed": "true/false"
            },
            "validation": {
                "signature_required": True
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum",
                    "produkt": "Produkt"
                },
                "filename_template": "Kostenaufstellung--{Produkt}--{Datum}"
            }
        },
        "Zuzahlungsaufstellung": {
            "classification_desc": "Zuzahlungsaufstellung.",
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Datum": "Datum",
                "Produkt": "Produkt",
                "Signed": "true/false"
            },
            "validation": {
                "signature_required": True
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum",
                    "produkt": "Produkt"
                },
                "filename_template": "Zuzahlungsaufstellung--{Produkt}--{Datum}"
            }
        },
        "Notiz": {
            "classification_desc": "Notiz.",
            "dependent": True,
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Datum": "Datum",
                "Produkt": "Produkt"
            },
            "validation": {
                "signature_required": False
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum",
                    "produkt": "Produkt"
                },
                "filename_template": "Notiz--{Produkt}--{Datum}"
            }
        },
        "Visitenkarte": {
            "classification_desc": "Visitenkarte.",
            "extraction_fields": {
                "Vorname": "Vorname",
                "Nachname": "Nachname",
                "Datum": "Datum"
            },
            "validation": {
                "signature_required": False
            },
            "routing": {
                "archive": True,
                "mapping": {
                    "person_vorname": "Vorname",
                    "person_nachname": "Nachname",
                    "datum": "Datum"
                },
                "filename_template": "Visitenkarte--{Nachname}_{Vorname}--{Datum}"
            }
        }
    }
    return DocumentProcessor(config)


def test_vertrag_validation_requires_signature(processor):
    # Vertrag ohne Unterschrift -> Fehlschlag
    data_no_sign = {"Document": "Vertrag", "Nachname": "Muster", "Vorname": "Max", "Datum": "2026-07-01", "Produkt": "Software", "Signed": False}
    valid, reason = processor._validate_extracted_data(data_no_sign)
    assert not valid
    assert "Signature" in reason or "Unterschrift" in reason

    # Vertrag mit Unterschrift -> OK
    data_sign = {"Document": "Vertrag", "Nachname": "Muster", "Vorname": "Max", "Datum": "2026-07-01", "Produkt": "Software", "Signed": True}
    valid, reason = processor._validate_extracted_data(data_sign)
    assert valid
    assert reason == "OK"


def test_other_docs_require_signature_only(processor):
    for doc_type in ["Datenschutzerklärung", "Kostenaufstellung", "Zuzahlungsaufstellung"]:
        # Ohne Unterschrift -> Fehlschlag
        data_no_sign = {"Document": doc_type, "Nachname": "Muster", "Vorname": "Max", "Datum": "2026-07-01", "Produkt": "Software", "Signed": False}
        valid, reason = processor._validate_extracted_data(data_no_sign)
        assert not valid
        assert "Signature" in reason or "Unterschrift" in reason

        # Mit Unterschrift -> OK
        data_sign = {"Document": doc_type, "Nachname": "Muster", "Vorname": "Max", "Datum": "2026-07-01", "Produkt": "Software", "Signed": True}
        valid, reason = processor._validate_extracted_data(data_sign)
        assert valid
        assert reason == "OK"


def test_notiz_no_signature_required(processor):
    data_notiz = {"Document": "Notiz", "Nachname": "Muster", "Vorname": "Max", "Datum": "2026-07-01", "Produkt": "Software", "Signed": False}
    valid, reason = processor._validate_extracted_data(data_notiz)
    assert valid
    assert reason == "OK"


def test_person_memory_persists_even_on_validation_failure(processor, tmp_path):
    # Erstelle eine Dummy-Datei im watch_dir
    dummy_file = tmp_path / "watch" / "test_vertrag.pdf"
    dummy_file.write_text("dummy pdf content", encoding="utf-8")

    # Mocke extract_hybrid_voting, dass ein Vertrag OHNE Unterschrift für "Hans Müller" herauskommt
    mock_extracted = {
        "Document": "Vertrag",
        "Vorname": "Hans",
        "Nachname": "Müller",
        "Datum": "2026-07-01",
        "Produkt": "Software",
        "Signed": False,
        "ocr_text": "Vertrag für Software Hans Müller",
        "page_results": []
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        processor.process_and_route_file(str(dummy_file))

    # Prüfe: Die Datei musste durch eine .meta Sidecar-Datei im watch_dir für manuelle Prüfung markiert werden
    pruefen_files = os.listdir(processor.config.watch_dir)
    assert any(f.endswith(".meta") for f in pruefen_files)

    # Aber das Personen-Gedächtnis MUSS trotzdem aktualisiert worden sein!
    assert processor.last_person_data["Nachname"] == "Müller"
    assert processor.last_person_data["Vorname"] == "Hans"
    assert processor.last_person_data["Produkt"] == "Software"


def test_notiz_routes_to_rejected_vertrag_person(processor, tmp_path):
    # 1. Vertrag ohne Unterschrift im watch_dir verarbeiten -> schlägt fehl und bleibt im Eingang (.meta wird erstellt)
    vertrag_file = tmp_path / "watch" / "vertrag_ohne_signatur.pdf"
    processor.config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    vertrag_file.write_text("dummy vertrag", encoding="utf-8")

    mock_vertrag = {
        "Document": "Vertrag",
        "Vorname": "Anna",
        "Nachname": "Schmidt",
        "Datum": "2026-07-02",
        "Produkt": "Hardware",
        "Signed": False,
        "ocr_text": "Vertrag Anna Schmidt",
        "page_results": []
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_vertrag):
        processor.process_and_route_file(str(vertrag_file))

    # Vertrag ist nicht im target_dir gelandet
    assert len(os.listdir(processor.config.target_base_dir)) == 0

    # 2. Jetzt kommt eine Notiz OHNE Personennamen an
    notiz_file = tmp_path / "watch" / "notiz_ohne_name.pdf"
    notiz_file.write_text("dummy notiz", encoding="utf-8")

    mock_notiz = {
        "Document": "Notiz",
        "Vorname": "[MISSING]",
        "Nachname": "[MISSING]",
        "Datum": "[Date-MISSING]",
        "Produkt": "[ProductName-MISSING]",
        "Signed": False,
        "ocr_text": "Notiz ohne Namen",
        "page_results": []
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_notiz):
        success = processor.process_and_route_file(str(notiz_file))

    # Prüfe: Die Notiz wurde erfolgreich verarbeitet und in den Ordner von Anna Schmidt sortiert!
    assert success
    target_folders = os.listdir(processor.config.target_base_dir)
    assert len(target_folders) == 1
    assert "Schmidt" in target_folders[0] and "Anna" in target_folders[0]


def test_unbekannt_doc_type_fails_validation(processor):
    # Dokument UNBEKANNT -> Fehlschlag
    data_unbekannt = {
        "Document": "UNKNOWN",
        "Nachname": "Muster",
        "Vorname": "Max",
        "Datum": "2026-07-01",
        "Produkt": "Software",
        "Signed": True
    }
    valid, reason = processor._validate_extracted_data(data_unbekannt)
    assert not valid
    assert "Document unknown or missing" in reason or "Dokument unbekannt oder fehlt" in reason

    # Dokument mit UNBEKANNT auf einer Seite -> Fehlschlag
    data_multipage = {
        "Document": "Vertrag+UNKNOWN",
        "Nachname": "Muster",
        "Vorname": "Max",
        "Datum": "2026-07-01",
        "Produkt": "Software",
        "Signed": True,
        "page_results": [
            {"Document": "Vertrag", "Signed": True},
            {"Document": "UNKNOWN", "Signed": True}
        ]
    }
    valid, reason = processor._validate_extracted_data(data_multipage)
    assert not valid
    assert "Document unknown or missing" in reason or "Dokument unbekannt oder fehlt" in reason


def test_multipage_datenschutz_only_requires_last_page_signature(processor):
    # Datenschutzerklärung über 2 Seiten (Gruppierte Extraktion durch KI)
    # KI erkennt Unterschrift auf letzter Seite -> Signed = True
    data_valid = {
        "Document": "Datenschutzerklärung",
        "Nachname": "Muster",
        "Vorname": "Max",
        "Datum": "2026-07-01",
        "Signed": True,
        "page_results": [
            {"Document": "Datenschutzerklärung", "Signed": True, "pages": [1, 2]}
        ]
    }
    valid, reason = processor._validate_extracted_data(data_valid)
    assert valid

    # KI erkennt KEINE Unterschrift auf letzter Seite -> Signed = False
    data_invalid = {
        "Document": "Datenschutzerklärung",
        "Nachname": "Muster",
        "Vorname": "Max",
        "Datum": "2026-07-01",
        "Signed": False,
        "page_results": [
            {"Document": "Datenschutzerklärung", "Signed": False, "pages": [1, 2]}
        ]
    }
    valid, reason = processor._validate_extracted_data(data_invalid)
    assert not valid
    assert "Signature missing" in reason or "Unterschrift fehlt" in reason


def test_dependent_document_inherits_parent_optional_fields(processor):
    # Simuliere Eltern-Dokument (z.B. Lieferschein) ohne akademischen Titel (Titel ist optional)
    parent_extracted = {
        "Document": "Lieferschein",
        "Nachname": "Schmidt",
        "Vorname": "Thomas",
        "Datum": "2026-07-15",
        "Produkt": "Software",
        "Titel": "[MISSING]"
    }

    # Verarbeite Eltern-Dokument, um den Kontext zu belegen
    processor.last_context = dict(parent_extracted)
    processor.last_optional_fields = {"titel"}
    processor.last_extraction_fields = {"datum", "nachname", "vorname", "titel", "produkt"}

    # Simuliere abhängiges Dokument (z. B. Anhang, dependent: true)
    dependent_extracted = {
        "Document": "Anhang"
    }

    # Simuliere Verarbeitungs-Kontext wie in process_and_route_file
    matched_info = {
        "dependent": True,
        "routing": {
            "archive": True,
            "filename_template": "Anhang--{Nachname}_{Vorname}--{Datum}",
            "match_folder_by": ["Nachname", "Titel", "Vorname"]
        }
    }

    # Initialisiere optionale/Extraktions-Felder für das abhängige Dokument (leer vor Vererbung)
    optional_fields = set()
    extraction_fields = set()

    # 1. Vererbe Daten aus dem vorherigen Kontext
    prev_ctx = processor.last_context
    for k, v in prev_ctx.items():
        from core.utils import is_missing_value
        if is_missing_value(dependent_extracted.get(k)):
            dependent_extracted[k] = v

    # 2. Vererbe optionale und Extraktionsfelder
    if processor.last_optional_fields:
        optional_fields = optional_fields | processor.last_optional_fields
    if processor.last_extraction_fields:
        extraction_fields = extraction_fields | processor.last_extraction_fields

    processor.config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}", "{Titel}"]
    target_dir = processor._determine_target_directory(
        extracted=dependent_extracted,
        routing_cfg=matched_info["routing"],
        optional_fields=optional_fields,
        extraction_fields=extraction_fields
    )

    # Erwartet: "2026-07-15--Software--Schmidt--Thomas"
    assert "----" not in target_dir
    assert "Thomas" in target_dir


def test_validate_extracted_data_low_confidence(processor):
    extracted_low_conf = {
        "Document": "Vertrag",
        "Vorname": "Daniel-Timothy",
        "Nachname": "Peal",
        "Datum": "2026-05-13",
        "Produkt": "Software",
        "Signed": True,
        "_confidence": {
            "Vorname": 1.0,
            "Nachname": 1.0,
            "Datum": 0.50,
            "Signed": 1.0
        }
    }

    is_valid, reason = processor.extraction_pipeline.validate_extracted_data(extracted_low_conf)
    assert not is_valid
    assert "Low confidence for required field 'Datum'" in reason
    assert "0.50" in reason


def test_validate_multidoc_batch_low_confidence(processor):
    extracted_multidoc = {
        "Document": "Vertrag+Kostenaufstellung",
        "Vorname": "Denise",
        "Nachname": "Wesselmann",
        "Datum": "2026-04-08",
        "Produkt": "Software",
        "Signed": True,
        "page_results": [
            {
                "Document": "Vertrag",
                "Vorname": "Denise",
                "Nachname": "Wesselmann",
                "Datum": "2026-04-08",
                "Signed": True,
                "_confidence": {"Datum": 0.50, "Vorname": 1.0, "Nachname": 1.0}
            },
            {
                "Document": "Kostenaufstellung",
                "Vorname": "Andre",
                "Nachname": "Haverigo",
                "Datum": "2026-04-08",
                "Produkt": "Software",
                "Signed": True,
                "_confidence": {"Datum": 1.0, "Vorname": 1.0, "Nachname": 1.0}
            }
        ]
    }

    is_valid, reason = processor.extraction_pipeline.validate_extracted_data(extracted_multidoc)
    assert not is_valid
    assert "Low confidence for required field 'Datum'" in reason
    assert "0.50" in reason

    is_valid, reason = processor.extraction_pipeline.validate_extracted_data(extracted_multidoc)
    assert not is_valid
    assert "Low confidence for required field 'Datum'" in reason
    assert "0.50" in reason


def test_notiz_skips_llm_vision_extraction(processor):
    """Testet, dass für Dokumente ohne Extraktionsfelder (Notiz/dependent) keine LLM Vision API Calls gemacht werden."""
    notiz_page = {
        "page_num": 1,
        "raw_img": None,
        "prep_img": None,
        "b64_img": "dummy",
        "matched_name": "Notiz",
        "matched_info": {
            "name": "Notiz",
            "dependent": True,
            "extraction_fields": {},
            "validation": {"signature_required": False}
        }
    }

    with patch.object(processor.extraction_pipeline, "run_extraction_tier") as mock_tier:
        res = processor.extraction_pipeline.process_document_pages([notiz_page])

    assert not mock_tier.called
    assert res is not None
    assert res.get("Document") == "Notiz"
