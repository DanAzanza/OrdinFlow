"""Unit tests for Case-Centric RPA Execution and FOR_EACH_DOCUMENT loops."""

import json
import os
import shutil
import tempfile
import pytest

from core.skills.case_router import (
    extract_all_skill_document_types,
    find_pending_cases,
    mark_file_skill_executed,
)
from core.skills.engines.export_engine import ExportEngine
from core.skills.loop_runner import has_for_each_document
from core.skills.manager import SkillManager



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


def test_mark_file_skill_executed_and_metadata_merge(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))
    engine = ExportEngine({}, skill_manager=mgr)

    folder = tmp_path / "case_meta"
    folder.mkdir()
    pdf_path = str(folder / "Report.pdf")
    meta_path = pdf_path + ".meta"
    open(pdf_path, "w").close()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"Document": "Report", "Diagnosis": "Flu", "Patient": "Max"}, f)

    # Mark as executed by skill 1
    res = engine.mark_file_skill_executed(pdf_path, "export_skill_1")
    assert res is True

    with open(meta_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["executed_skills"] == ["export_skill_1"]
    assert "export_skill_1" in data["skill_execution_history"]

    # Mark as executed by skill 2 (multi-skill execution)
    engine.mark_file_skill_executed(pdf_path, "export_skill_2")
    with open(meta_path, encoding="utf-8") as f:
        data2 = json.load(f)
    assert data2["executed_skills"] == ["export_skill_1", "export_skill_2"]


def test_find_pending_cases_for_skill(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))
    skill_data = {
        "id": "rdp_export",
        "name": "RDP Export",
        "enabled": True,
        "document_types": ["Report", "Prescription"],
        "steps": [],
    }
    mgr.save_skill(skill_data)
    engine = ExportEngine(skill_data, skill_manager=mgr)

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()

    # Folder 1: Not approved -> Should be ignored
    c1 = cases_dir / "Case1"
    c1.mkdir()
    (c1 / "Report.pdf").touch()

    # Folder 2: Approved, with matching Report.pdf -> Should be found
    c2 = cases_dir / "Case2"
    c2.mkdir()
    (c2 / ".approved").touch()
    p2 = c2 / "Report.pdf"
    p2.touch()
    with open(str(p2) + ".meta", "w", encoding="utf-8") as f:
        json.dump({"Document": "Report"}, f)

    # Folder 3: Approved, but Report.pdf already exported with RDP Export -> Should be ignored
    c3 = cases_dir / "Case3"
    c3.mkdir()
    (c3 / ".approved").touch()
    p3 = c3 / "Report.pdf"
    p3.touch()
    with open(str(p3) + ".meta", "w", encoding="utf-8") as f:
        json.dump({"Document": "Report", "executed_skills": ["RDP Export"]}, f)

    pending = engine.find_pending_cases(str(cases_dir))
    assert len(pending) == 1
    assert pending[0]["folder_name"] == "Case2"
    assert pending[0]["unprocessed_count"] == 1


def test_export_engine_multi_file_folder_execution(tmp_path):
    folder = tmp_path / "case_folder"
    folder.mkdir()

    f1 = str(folder / "Fußscan__Left.pdf")
    f2 = str(folder / "Fußscan__Right.pdf")
    open(f1, "w").close()
    open(f2, "w").close()

    with open(f1 + ".meta", "w", encoding="utf-8") as meta_f:
        json.dump({"Document": "Fußscan", "Side": "Left"}, meta_f)
    with open(f2 + ".meta", "w", encoding="utf-8") as meta_f:
        json.dump({"Document": "Fußscan", "Side": "Right"}, meta_f)

    executed_files = []

    class MockExportEngine(ExportEngine):
        def execute_steps(self, context, reporter=None, depth=0):
            executed_files.append(context.get("document_fullpath"))
            return True

    skill_def = {
        "id": "fu_scan_export",
        "name": "Fußscan Export",
        "type": "export",
        "document_types": ["Fußscan"],
        "tasks": [
            {
                "id": "t1",
                "title": "Task 1",
                "actions": [{"action_type": "FOCUS_WINDOW", "window_title": "CorelDRAW*"}],
            }
        ],
    }
    engine = MockExportEngine(skill_def)

    success = engine.execute_skill_for_folder(str(folder))
    assert success is True
    assert len(executed_files) == 2
    assert f1 in executed_files
    assert f2 in executed_files

    with open(f1 + ".meta", "r", encoding="utf-8") as mf1:
        m1 = json.load(mf1)
    with open(f2 + ".meta", "r", encoding="utf-8") as mf2:
        m2 = json.load(mf2)
    assert "fu_scan_export" in m1.get("executed_skills", [])
    assert "fu_scan_export" in m2.get("executed_skills", [])


def test_case_router_clean_metadata_parsing(tmp_path):
    # Create approved case folder with __ delimiter and standard folder structure
    folder_name = "2026-08-22__Einlagen__Mustermann__Max__----"
    case_path = tmp_path / folder_name
    case_path.mkdir()
    (case_path / ".approved").touch()

    scan_pdf = str(case_path / "Fußscan__2026-08-22.pdf")
    open(scan_pdf, "w").close()
    with open(scan_pdf + ".meta", "w", encoding="utf-8") as mf:
        json.dump({"Document": "Fußscan"}, mf)

    folder_struct = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}", "{Titel}"]
    cases = find_pending_cases(
        str(tmp_path),
        skill_id="fu_scan_export",
        allowed_types=["Fußscan"],
        folder_structure=folder_struct,
        delimiter="__",
    )

    assert len(cases) == 1
    c = cases[0]
    meta = c["parsed_metadata"]
    assert meta["Datum"] == "2026-08-22"
    assert meta["Produkt"] == "Einlagen"
    assert meta["Nachname"] == "Mustermann"
    assert meta["Vorname"] == "Max"
    assert meta["Titel"] == ""  # '----' stripped to empty

