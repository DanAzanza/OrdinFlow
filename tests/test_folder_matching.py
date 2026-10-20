"""Tests for case folder matching, completion, and consolidation (match_folder_by)."""

import os
from pathlib import Path

from core.config import AppConfig
from core.file_service import FileService, matches_folder_keywords
from routes.schemas import ConfigUpdateSchema, validate_schema


def test_token_word_boundary_matching():
    """Validates that folder keyword matching respects word boundaries and delimiters."""
    # 1. Delimiter-separated tokens
    assert matches_folder_keywords("2026__Rechnungen__Acme_GmbH", ["Rechnungen", "Acme"])
    assert matches_folder_keywords("2026-05-12--Software--Mustermann--Erika", ["Mustermann", "Erika", "Software"])
    assert matches_folder_keywords("----__----__Blumenau__Klaus", ["Blumenau", "Klaus"])
    assert matches_folder_keywords("13-03-2026__Einlagen__Blumenau__Klaus", ["Blumenau", "Klaus"])

    # 2. German umlauts and special characters
    assert matches_folder_keywords("2026__Befund__Dr_Müller_Jörg", ["Müller", "Jörg"])

    # 3. Negative assertions: Substring collisions must NOT match
    assert not matches_folder_keywords("2026__Maier_Hans", ["Mai"])
    assert not matches_folder_keywords("2026__Mustermann_Erika", ["Mann"])
    assert not matches_folder_keywords("2026__Klinik_Nord", ["Li"])
    assert not matches_folder_keywords("2026__Lotto_GmbH", ["Otto"])


def test_incomplete_folder_renamed_when_complete_data_arrives(tmp_path):
    """The user's exact scenario:

    An old folder with incomplete metadata ('----__----__Blumenau__Klaus') contains a document.
    Later, complete metadata ('13-03-2026__Einlagen__Blumenau__Klaus') arrives.
    The old folder must be renamed and contain all prior documents.
    """
    cases_dir = tmp_path / "Cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig()
    config.target_base_dir = str(cases_dir)
    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.folder_delimiter = "__"
    config.match_folder_by = ["Nachname", "Vorname"]

    file_service = FileService(config)

    # 1. Create existing incomplete folder with an existing document
    old_folder = cases_dir / "----__----__Blumenau__Klaus"
    old_folder.mkdir(parents=True, exist_ok=True)
    existing_file = old_folder / "initial_doc.pdf"
    existing_file.write_bytes(b"%PDF-1.4 dummy content")

    # 2. Complete data arrives for Blumenau Klaus
    new_extracted = {
        "Document": "Einlagen",
        "Datum": "13-03-2026",
        "Produkt": "Einlagen",
        "Nachname": "Blumenau",
        "Vorname": "Klaus",
    }

    target_dir = file_service.determine_target_directory(new_extracted)
    expected_dir = str(cases_dir / "13-03-2026__Einlagen__Blumenau__Klaus")

    assert os.path.abspath(target_dir) == os.path.abspath(expected_dir)
    assert os.path.exists(expected_dir)
    # The old folder must be gone
    assert not os.path.exists(old_folder)
    # The prior file must now reside in the renamed folder
    migrated_file = Path(expected_dir) / "initial_doc.pdf"
    assert migrated_file.exists()


def test_incomplete_folder_merged_when_target_already_exists(tmp_path):
    """When both an incomplete folder and the complete folder exist, contents must merge."""
    cases_dir = tmp_path / "Cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig()
    config.target_base_dir = str(cases_dir)
    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.folder_delimiter = "__"
    config.match_folder_by = ["Nachname", "Vorname"]

    file_service = FileService(config)

    # 1. Incomplete folder with old doc
    old_folder = cases_dir / "----__----__Blumenau__Klaus"
    old_folder.mkdir(parents=True, exist_ok=True)
    (old_folder / "old_rezept.pdf").write_bytes(b"%PDF-1.4 old")

    # 2. Complete target folder already exists with an existing doc
    target_folder = cases_dir / "13-03-2026__Einlagen__Blumenau__Klaus"
    target_folder.mkdir(parents=True, exist_ok=True)
    (target_folder / "existing_einlagen.pdf").write_bytes(b"%PDF-1.4 new")

    new_extracted = {
        "Document": "Einlagen",
        "Datum": "13-03-2026",
        "Produkt": "Einlagen",
        "Nachname": "Blumenau",
        "Vorname": "Klaus",
    }

    target_dir = file_service.determine_target_directory(new_extracted)

    assert os.path.abspath(target_dir) == os.path.abspath(str(target_folder))
    # Both files must now exist in target_folder
    assert (target_folder / "existing_einlagen.pdf").exists()
    assert (target_folder / "old_rezept.pdf").exists()
    # Incomplete folder must have been removed
    assert not old_folder.exists()


def test_multiple_orphaned_incomplete_folders_consolidate(tmp_path):
    """When multiple orphaned incomplete folders exist, all must converge into the final folder."""
    cases_dir = tmp_path / "Cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig()
    config.target_base_dir = str(cases_dir)
    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.folder_delimiter = "__"
    config.match_folder_by = ["Nachname", "Vorname"]

    file_service = FileService(config)

    # Incomplete folder 1: 2 missing fields
    orphan1 = cases_dir / "----__----__Blumenau__Klaus"
    orphan1.mkdir(parents=True, exist_ok=True)
    (orphan1 / "doc1.pdf").write_bytes(b"%PDF-1.4 doc1")

    # Incomplete folder 2: 1 missing field
    orphan2 = cases_dir / "----__Einlagen__Blumenau__Klaus"
    orphan2.mkdir(parents=True, exist_ok=True)
    (orphan2 / "doc2.pdf").write_bytes(b"%PDF-1.4 doc2")

    # Complete document arrives
    complete_extracted = {
        "Document": "Einlagen",
        "Datum": "13-03-2026",
        "Produkt": "Einlagen",
        "Nachname": "Blumenau",
        "Vorname": "Klaus",
    }

    target_dir = file_service.determine_target_directory(complete_extracted)
    final_dir = Path(target_dir)

    assert "13-03-2026__Einlagen__Blumenau__Klaus" in target_dir
    assert (final_dir / "doc1.pdf").exists()
    assert (final_dir / "doc2.pdf").exists()
    assert not orphan1.exists()
    assert not orphan2.exists()


def test_fail_closed_matching_on_missing_required_match_keys(tmp_path):
    """Strict security test: If any required match key is missing, matching MUST fail closed."""
    cases_dir = tmp_path / "Cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig()
    config.target_base_dir = str(cases_dir)
    config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    config.folder_delimiter = "__"
    config.match_folder_by = ["Nachname", "Vorname"]

    file_service = FileService(config)

    # Pre-existing folder for Klaus Blumenau
    klaus_folder = cases_dir / "13-03-2026__Einlagen__Blumenau__Klaus"
    klaus_folder.mkdir(parents=True, exist_ok=True)
    (klaus_folder / "klaus_file.pdf").write_bytes(b"%PDF-1.4")

    # An incoming document with ONLY Nachname (Vorname is missing)
    partial_extracted = {
        "Document": "Rezept",
        "Datum": "15-03-2026",
        "Produkt": "Medikament",
        "Nachname": "Blumenau",
        "Vorname": "[MISSING]",
    }

    target_dir = file_service.determine_target_directory(partial_extracted)

    # Must NOT route into Klaus's folder (fail-closed to prevent DSGVO / medical secrecy leak)
    assert os.path.abspath(target_dir) != os.path.abspath(str(klaus_folder))
    assert "Klaus" not in target_dir


def test_config_update_schema_normalization():
    """Tests Pydantic normalization of match_folder_by and folder_structure."""
    # 1. Comma-separated string with curly braces
    payload1 = {"match_folder_by": "{Nachname}, {Vorname} "}
    validated1, err1 = validate_schema(ConfigUpdateSchema, payload1)
    assert err1 is None
    assert validated1 is not None
    assert validated1.match_folder_by == ["Nachname", "Vorname"]

    # 2. List with curly braces
    payload2 = {"match_folder_by": ["{Nachname}", " {Vorname} "]}
    validated2, err2 = validate_schema(ConfigUpdateSchema, payload2)
    assert err2 is None
    assert validated2 is not None
    assert validated2.match_folder_by == ["Nachname", "Vorname"]

    # 3. String for folder_structure
    payload3 = {"folder_structure": "{Datum}, {Produkt}, {Nachname}"}
    validated3, err3 = validate_schema(ConfigUpdateSchema, payload3)
    assert err3 is None
    assert validated3 is not None
    assert validated3.folder_structure == ["{Datum}", "{Produkt}", "{Nachname}"]


def test_api_config_match_folder_by_integration(client):
    """Tests GET and PUT /api/config for match_folder_by."""
    # 1. Update with list
    put_res = client.put("/api/config", json={"match_folder_by": ["Nachname", "Vorname"]})
    assert put_res.status_code == 200
    assert "match_folder_by" in put_res.get_json()["changed"]

    get_res = client.get("/api/config")
    assert get_res.status_code == 200
    assert get_res.get_json()["match_folder_by"] == ["Nachname", "Vorname"]

    # 2. Update with comma-separated string containing template braces
    put_res2 = client.put("/api/config", json={"match_folder_by": "{Nachname}, {Vorname}, {Titel}"})
    assert put_res2.status_code == 200
    assert "match_folder_by" in put_res2.get_json()["changed"]

    get_res2 = client.get("/api/config")
    assert get_res2.status_code == 200
    assert get_res2.get_json()["match_folder_by"] == ["Nachname", "Vorname", "Titel"]
