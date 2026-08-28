"""Unit tests for Case-Centric RPA Execution and FOR_EACH_DOCUMENT loops."""

import json
import os
import shutil
import tempfile
import pytest

from core.skills.case_router import (
    extract_all_skill_document_types,
    mark_file_skill_executed,
)
from core.skills.engines.export_engine import ExportEngine
from core.skills.loop_runner import has_for_each_document


@pytest.fixture
def temp_case_dir():
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_extract_all_skill_document_types():
    # 1. Root-only types
    skill1 = {
        "id": "skill1",
        "document_types": ["Fußscan", "Rezept"],
        "tasks": [],
    }
    assert extract_all_skill_document_types(skill1) == ["Fußscan", "Rezept"]

    # 2. Nested FOR_EACH_DOCUMENT inside tasks
    skill2 = {
        "id": "skill2",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "loop_docs",
                        "action_type": "FOR_EACH_DOCUMENT",
                        "document_types": ["Fußscan", "Arztbrief"],
                        "actions": [],
                    }
                ],
            }
        ],
    }
    assert set(extract_all_skill_document_types(skill2)) == {"Fußscan", "Arztbrief"}

    # 3. Wildcard inheritance
    skill3 = {
        "id": "skill3",
        "document_types": ["*"],
        "tasks": [],
    }
    assert extract_all_skill_document_types(skill3) == ["*"]


def test_has_for_each_document():
    flat_skill = {
        "id": "flat",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {"id": "a1", "action_type": "HOTKEY", "keys": ["ctrl", "s"]},
                ],
            }
        ],
    }
    assert not has_for_each_document(flat_skill)

    loop_skill = {
        "id": "loop",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "loop_act",
                        "action_type": "FOR_EACH_DOCUMENT",
                        "document_types": ["Fußscan"],
                        "actions": [{"id": "sub1", "action_type": "DELAY", "delay_ms": 10}],
                    }
                ],
            }
        ],
    }
    assert has_for_each_document(loop_skill)


def test_case_centric_execution_with_multiple_documents(temp_case_dir):
    # Setup test case folder with 3 documents
    case_folder = os.path.join(temp_case_dir, "2026-08-28__Einlagen__Mustermann__Max")
    os.makedirs(case_folder, exist_ok=True)
    with open(os.path.join(case_folder, ".approved"), "w", encoding="utf-8") as f:
        f.write("approved")

    doc1 = os.path.join(case_folder, "Fußscan__28.08.2026.pdf")
    doc2 = os.path.join(case_folder, "Rezept__28.08.2026.pdf")
    doc3 = os.path.join(case_folder, "Sonstiges__28.08.2026.pdf")

    for doc, cat in [(doc1, "Fußscan"), (doc2, "Rezept"), (doc3, "Sonstiges")]:
        with open(doc, "wb") as f:
            f.write(b"%PDF-1.4 test")
        with open(f"{doc}.meta", "w", encoding="utf-8") as f:
            json.dump({"category": cat, "executed_skills": []}, f)

    # Define case-centric skill
    skill_def = {
        "id": "case_upload_skill",
        "name": "Case Upload Skill",
        "type": "export",
        "tasks": [
            {
                "id": "t_setup",
                "title": "Setup",
                "actions": [
                    {"id": "act_set", "action_type": "SET_VARIABLE", "variable": "case_status", "value": "open"},
                ],
            },
            {
                "id": "t_loop",
                "title": "Loop Docs",
                "actions": [
                    {
                        "id": "loop_docs",
                        "action_type": "FOR_EACH_DOCUMENT",
                        "document_types": ["Fußscan", "Rezept"],
                        "actions": [
                            {
                                "id": "act_record",
                                "action_type": "SET_VARIABLE",
                                "variable": "last_doc",
                                "value": "{document_fullpath}",
                            },
                        ],
                    }
                ],
            },
            {
                "id": "t_teardown",
                "title": "Teardown",
                "actions": [
                    {"id": "act_close", "action_type": "SET_VARIABLE", "variable": "case_status", "value": "closed"},
                ],
            },
        ],
    }

    engine = ExportEngine(skill_def)

    # Verify discovery finds matching case
    pending = engine.find_pending_cases(temp_case_dir)
    assert len(pending) == 1
    assert pending[0]["folder_path"] == case_folder

    # Execute skill for folder
    success = engine.execute_skill_for_folder(case_folder, context={"patient_name": "Mustermann"})
    assert success is True

    # Verify .meta sidecars
    with open(f"{doc1}.meta", "r", encoding="utf-8") as f:
        meta1 = json.load(f)
        assert "case_upload_skill" in meta1.get("executed_skills", [])

    with open(f"{doc2}.meta", "r", encoding="utf-8") as f:
        meta2 = json.load(f)
        assert "case_upload_skill" in meta2.get("executed_skills", [])

    # Doc3 was not in allowed document_types and should NOT be marked
    with open(f"{doc3}.meta", "r", encoding="utf-8") as f:
        meta3 = json.load(f)
        assert "case_upload_skill" not in meta3.get("executed_skills", [])

    # Second execution should find no pending files for this skill
    pending_after = engine.find_pending_cases(temp_case_dir)
    assert len(pending_after) == 0


def test_atomic_meta_sidecar_replacement(temp_case_dir):
    test_pdf = os.path.join(temp_case_dir, "TestDoc.pdf")
    with open(test_pdf, "wb") as f:
        f.write(b"%PDF-1.4 test")

    meta_path = f"{test_pdf}.meta"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"category": "Rezept", "Nachname": "Mustermann", "executed_skills": []}, f)

    assert mark_file_skill_executed(test_pdf, "skill_alpha") is True

    with open(meta_path, "r", encoding="utf-8") as f:
        updated = json.load(f)
        assert "skill_alpha" in updated["executed_skills"]
        assert updated["Nachname"] == "Mustermann"

    # Marking same skill again is idempotent
    assert mark_file_skill_executed(test_pdf, "skill_alpha") is True
    with open(meta_path, "r", encoding="utf-8") as f:
        updated = json.load(f)
        assert updated["executed_skills"].count("skill_alpha") == 1
