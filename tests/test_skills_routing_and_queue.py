"""Unit tests for Skill routing, case discovery, and execution marking."""

from __future__ import annotations

import json

from core.skills.case_router import find_pending_cases
from core.skills.engines.export_engine import ExportEngine
from core.skills.manager import SkillManager


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
                "actions": [{"action_type": "FOCUS_WINDOW", "window_title": "CorelDRAW*"}]
            }
        ]
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
