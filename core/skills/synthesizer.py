"""Skill AI Synthesizer: converts recorded UI actions into structured, human-readable Tasks & Actions."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from routes.state import DashboardState

logger = logging.getLogger(__name__)


class SkillSynthesizer:
    """Uses the local LLM and heuristic rules to clean, group, and enrich raw recorded RPA events."""

    @classmethod
    def synthesize(
        cls,
        raw_steps: list[dict[str, Any]],
        user_instruction: str = "",
        existing_doc_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Synthesizes raw recorded steps into a clean Task & Action skill structure."""
        if not raw_steps:
            return cls._generate_fallback_synthesis(
                user_instruction=user_instruction,
                existing_doc_types=existing_doc_types,
            )

        # 1. Gather domain context (configured document categories & extraction fields)
        known_categories, known_variables = cls._get_domain_context(existing_doc_types)

        # 2. Try LLM synthesis
        llm_extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
        if llm_extractor is not None:
            try:
                synthesis = cls._synthesize_with_llm(
                    raw_steps=raw_steps,
                    user_instruction=user_instruction,
                    known_categories=known_categories,
                    known_variables=known_variables,
                    llm_extractor=llm_extractor,
                )
                if synthesis and isinstance(synthesis.get("tasks"), list) and synthesis["tasks"]:
                    return synthesis
            except Exception as e:
                logger.warning("[SkillSynthesizer] LLM synthesis failed, using heuristic fallback: %s", e)

        # 3. Deterministic heuristic fallback
        return cls._synthesize_with_heuristics(
            raw_steps=raw_steps,
            user_instruction=user_instruction,
            known_categories=known_categories,
        )

    @classmethod
    def _synthesize_with_llm(
        cls,
        raw_steps: list[dict[str, Any]],
        user_instruction: str,
        known_categories: list[str],
        known_variables: list[str],
        llm_extractor: Any,
    ) -> dict[str, Any] | None:
        """Prompts the local LLM to structure, name, and parameterize the skill."""
        prompt = (
            "Du bist ein intelligenter Assistent für Praxis- und Büroautomation (RPA).\n"
            "Ein Nutzer hat eine Bildschirmaufnahme durchgeführt, um einen Arbeitsablauf zu automatisieren.\n"
            "Deine Aufgabe ist es, diese rohen Schritte zu analysieren, logisch in Aufgaben (Tasks) zu bündeln,\n"
            "statische Werte durch Variablen zu ersetzen und verständliche deutsche Bezeichnungen zu vergeben.\n\n"
            f"Bekannte Dokument-Kategorien im System: {json.dumps(known_categories, ensure_ascii=False)}\n"
            f"Verfügbare Variablen: {json.dumps(known_variables, ensure_ascii=False)}\n"
            f"Zusätzliche Nutzer-Anweisung: \"{user_instruction}\"\n\n"
            f"Aufgenommene rohe Schritte:\n{json.dumps(raw_steps, ensure_ascii=False, indent=2)}\n\n"
            "Regeln für die Synthese:\n"
            "1. Wenn ein Dateipfad eingetippt oder gewählt wurde (z.B. C:\\... oder *.pdf), ersetze ihn in Action TYPE_FILE_PATH durch '{document_fullpath}'.\n"
            "2. Wenn ein Text eingegeben wurde, der wie ein Nachname/Datum aussieht, setze die passende Variable (z.B. {Nachname}, {Datum}) ein.\n"
            "3. Entferne versehentliche Klicks auf 'Stop' oder das Dashboard.\n"
            "4. Fasse zusammenhängende Aktionen in logische Aufgaben (Tasks) zusammen (z.B. Task 1: 'Datei im Programm öffnen', Task 2: 'Als CDR exportieren').\n"
            "5. Schlage einen prägnanten Skill-Namen auf Deutsch vor (z.B. 'Fußscan als CDR exportieren').\n"
            "6. Wähle die am besten passende Kategorie aus den bekannten Dokument-Kategorien (oder ['*'] für alle).\n\n"
            "Gib AUSSCHLIESSLICH ein valides JSON-Objekt mit folgender Schema-Struktur zurück:\n"
            "{\n"
            '  "name": "Fußscan als CDR exportieren",\n'
            '  "description": "Öffnet das Dokument im CAD-Programm und exportiert es als CDR-Datei.",\n'
            '  "suggested_document_types": ["Fußscan"],\n'
            '  "detected_variables": [\n'
            '    {"original": "C:\\\\Temp\\\\test.pdf", "variable": "{document_fullpath}", "label": "Dateipfad"}\n'
            "  ],\n"
            '  "tasks": [\n'
            "    {\n"
            '      "id": "task_1",\n'
            '      "title": "Datei im Zielprogramm öffnen",\n'
            '      "actions": [\n'
            '        {"id": "act_1", "action_type": "FOCUS_WINDOW", "description": "Fenster fokussieren", "window_title": "Remote Desktop*"},\n'
            '        {"id": "act_2", "action_type": "CLICK", "description": "Menü Datei -> Öffnen", "locator": {"type": "ocr_contains", "prompt": "Datei"}},\n'
            '        {"id": "act_3", "action_type": "TYPE_FILE_PATH", "description": "Dateipfad übergeben", "file_path": "{document_fullpath}", "press_enter": true}\n'
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        res = llm_extractor.extract_fields_from_text(prompt, {})
        if isinstance(res, dict) and "tasks" in res:
            return res
        return None

    @classmethod
    def _synthesize_with_heuristics(
        cls,
        raw_steps: list[dict[str, Any]],
        user_instruction: str,
        known_categories: list[str],
    ) -> dict[str, Any]:
        """Deterministic heuristic fallback when LLM is unavailable."""
        cleaned_actions: list[dict[str, Any]] = []
        detected_vars: list[dict[str, Any]] = []
        detected_doc_types: list[str] = ["*"]

        # Check if user instruction mentions a known category
        if user_instruction:
            user_low = user_instruction.lower()
            for cat in known_categories:
                if cat.lower() in user_low:
                    detected_doc_types = [cat]
                    break

        act_idx = 1
        for s in raw_steps:
            act_type = s.get("action_type", "CLICK")
            desc = s.get("description", f"Aktion {act_idx}")

            act: dict[str, Any] = {
                "id": f"act_{act_idx}",
                "action_type": act_type,
                "description": desc,
            }

            if act_type == "FOCUS_WINDOW":
                act["window_title"] = s.get("window_title", "Remote Desktop*")
            elif act_type in ("CLICK", "DOUBLE_CLICK"):
                act["locator"] = s.get("locator", {"type": "auto", "prompt": ""})
            elif act_type == "TYPE_TEXT":
                raw_t = str(s.get("text", ""))
                # Detect file path in text
                if re.search(r"[a-zA-Z]:[\\/].*\.(pdf|png|jpg|cdr|tif)", raw_t, re.IGNORECASE):
                    act["action_type"] = "TYPE_FILE_PATH"
                    act["file_path"] = "{document_fullpath}"
                    act["press_enter"] = bool(s.get("press_enter", True))
                    act["description"] = "Dateipfad übergeben"
                    detected_vars.append(
                        {"original": raw_t, "variable": "{document_fullpath}", "label": "Dateipfad"}
                    )
                else:
                    act["text"] = raw_t
                    act["press_enter"] = bool(s.get("press_enter", False))
            elif act_type == "TYPE_FILE_PATH":
                act["file_path"] = s.get("file_path", "{document_fullpath}")
                act["press_enter"] = bool(s.get("press_enter", True))

            if s.get("delay_ms"):
                act["delay_ms"] = s["delay_ms"]

            cleaned_actions.append(act)
            act_idx += 1

        # Group actions into 1 or 2 logical tasks
        tasks: list[dict[str, Any]] = []
        if len(cleaned_actions) > 4:
            mid = len(cleaned_actions) // 2
            tasks.append({
                "id": "task_1",
                "title": "Programm vorbereiten & Datei aufrufen",
                "actions": cleaned_actions[:mid],
            })
            tasks.append({
                "id": "task_2",
                "title": "Aktion ausführen & speichern",
                "actions": cleaned_actions[mid:],
            })
        else:
            tasks.append({
                "id": "task_1",
                "title": "Arbeitsablauf ausführen",
                "actions": cleaned_actions,
            })

        skill_name = "Neuer Skill"
        if detected_doc_types != ["*"]:
            skill_name = f"{detected_doc_types[0]} exportieren"

        return {
            "name": skill_name,
            "description": f"Automatisierter Ablauf mit {len(cleaned_actions)} Aktionen.",
            "suggested_document_types": detected_doc_types,
            "detected_variables": detected_vars,
            "tasks": tasks,
        }

    @classmethod
    def _generate_fallback_synthesis(
        cls,
        user_instruction: str = "",
        existing_doc_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generates an initial structured Task template."""
        return {
            "name": "Neuer Skill",
            "description": "Automatisierter Arbeitsablauf.",
            "suggested_document_types": existing_doc_types or ["*"],
            "detected_variables": [],
            "tasks": [
                {
                    "id": "task_1",
                    "title": "Programm aufrufen",
                    "actions": [
                        {
                            "id": "act_1",
                            "action_type": "FOCUS_WINDOW",
                            "description": "Zielfenster in den Vordergrund bringen",
                            "window_title": "Remote Desktop*",
                        }
                    ],
                }
            ],
        }

    @classmethod
    def _get_domain_context(
        cls, existing_doc_types: list[str] | None = None
    ) -> tuple[list[str], list[str]]:
        """Extracts available categories and variables from runtime configuration."""
        known_categories: list[str] = []
        known_variables: list[str] = [
            "{document_fullpath}",
            "{document_filename}",
            "{document_name}",
        ]

        if DashboardState.config:
            if DashboardState.config.document_types:
                known_categories = list(DashboardState.config.document_types.keys())
                for doc in DashboardState.config.document_types.values():
                    ext_fields = (
                        doc.get("extraction_fields")
                        if isinstance(doc, dict)
                        else getattr(doc, "extraction_fields", None)
                    )
                    if ext_fields:
                        for f in ext_fields:
                            var_tag = f"{{{f}}}"
                            if var_tag not in known_variables:
                                known_variables.append(var_tag)

            if DashboardState.config.folder_structure:
                for part in DashboardState.config.folder_structure:
                    p = str(part).strip()
                    if p:
                        tag = p if p.startswith("{") and p.endswith("}") else f"{{{p}}}"
                        if tag not in known_variables:
                            known_variables.append(tag)

        if existing_doc_types:
            for cat in existing_doc_types:
                if cat not in known_categories:
                    known_categories.append(cat)

        return known_categories, known_variables

    @classmethod
    def modify_skill(
        cls,
        existing_skill: dict[str, Any],
        user_instruction: str,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Modifies an existing skill using conversational natural language instructions and returns (skill, reply)."""
        if not user_instruction.strip():
            return existing_skill, "No instruction provided."

        updated = dict(existing_skill)
        known_categories, known_variables = cls._get_domain_context()
        reply_message = "Changes were applied successfully."

        history_text = ""
        if history and isinstance(history, list):
            history_lines = []
            for h in history[-6:]:
                role = "User" if h.get("role") == "user" else "Assistant"
                content = str(h.get("content", "")).strip()
                if content:
                    history_lines.append(f"{role}: {content}")
            if history_lines:
                history_text = "Previous conversation history:\n" + "\n".join(history_lines) + "\n\n"

        llm_extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
        if llm_extractor is not None:
            try:
                prompt = (
                    "You are an intelligent workflow automation assistant (RPA).\n"
                    "The user wants to modify, extend, or refine an existing skill based on a conversation with you.\n\n"
                    f"{history_text}"
                    f"Existing skill definition:\n{json.dumps(existing_skill, ensure_ascii=False, indent=2)}\n\n"
                    f"Known document categories: {json.dumps(known_categories, ensure_ascii=False)}\n"
                    f"Available variables: {json.dumps(known_variables, ensure_ascii=False)}\n"
                    f"User instruction: \"{user_instruction}\"\n\n"
                    "Rules:\n"
                    "1. Accurately implement the user's intent (e.g. add new actions, adjust delays, fix order, set window titles, use variables).\n"
                    "2. Preserve valid existing tasks and actions unless the user requested to remove or replace them.\n"
                    "3. When adding actions, use standard action types (CLICK, DOUBLE_CLICK, TYPE_TEXT, TYPE_FILE_PATH, FOCUS_WINDOW, DELAY, VERIFY_SCREEN, CALL_SKILL).\n"
                    "4. Return a JSON object with two top-level fields:\n"
                    "   - 'reply': A concise, helpful English explanation for the chat feed summarizing what was modified or added.\n"
                    "   - 'skill': The complete updated skill object with all fields.\n\n"
                    "Return ONLY the valid JSON object."
                )
                res = llm_extractor.extract_fields_from_text(prompt, {})
                if isinstance(res, dict):
                    if "skill" in res and isinstance(res["skill"], dict):
                        skill_res = res["skill"]
                        reply_res = str(res.get("reply") or "")
                        for k, v in skill_res.items():
                            if v is not None:
                                updated[k] = v
                        return updated, reply_res or "I have updated the skill according to your instruction."
                    elif "tasks" in res or "steps" in res or "name" in res:
                        for k, v in res.items():
                            if v is not None:
                                updated[k] = v
                        return updated, "I have updated the skill according to your instruction."
            except Exception as e:
                logger.warning("[SkillSynthesizer] LLM skill modification failed, applying heuristic fallback: %s", e)

        # Heuristic fallback for common instructions
        lower = user_instruction.lower()
        tasks = updated.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            tasks = [{"id": "task_1", "title": "Execution Workflow", "actions": []}]
            updated["tasks"] = tasks

        last_task = tasks[-1]
        if not isinstance(last_task.get("actions"), list):
            last_task["actions"] = []

        added_descriptions = []

        # Check for delay/pause first
        if any(k in lower for k in ["warte", "pause", "delay", "sleep", "wait"]):
            m_delay = re.search(r"(\d+)\s*(ms|millisekunden|milliseconds|sekunden|seconds|s|sec)?", lower)
            delay_ms = 500
            if m_delay:
                val = int(m_delay.group(1))
                unit = m_delay.group(2) or "ms"
                delay_ms = val * 1000 if unit in ["s", "sekunden", "seconds", "sec"] else val
            last_task["actions"].append({
                "id": f"act_{int(time.time())}_delay",
                "action_type": "DELAY",
                "description": f"Wait {delay_ms} ms",
                "delay_ms": delay_ms,
            })
            added_descriptions.append(f"delay of {delay_ms} ms")

        # Check for click
        if any(k in lower for k in ["klick", "click"]):
            m_quote = re.search(r"['\"]([^'\"]+)['\"]", user_instruction)
            if m_quote:
                target = m_quote.group(1).strip()
            else:
                target = re.sub(r"(?i).*(klicke auf|klick auf|click on|klicke|click|klick ein auf|klick ein)\s*", "", user_instruction).strip("\"' .")
            last_task["actions"].append({
                "id": f"act_{int(time.time())}_click",
                "action_type": "CLICK",
                "description": f"Click on {target or 'Element'}",
                "locator": {"type": "auto", "prompt": target or "Button"},
            })
            added_descriptions.append(f"click on '{target or 'Element'}'")

        # Check for file path
        if any(k in lower for k in ["datei", "file", "pfad", "path"]) and not any(k in lower for k in ["klick", "click"]):
            last_task["actions"].append({
                "id": f"act_{int(time.time())}_path",
                "action_type": "TYPE_FILE_PATH",
                "description": "Pass file path",
                "file_path": "{document_fullpath}",
                "press_enter": True,
            })
            added_descriptions.append("pass file path ({document_fullpath})")

        # Check for window focus
        if any(k in lower for k in ["fenster", "window", "fokus", "focus"]):
            m_win = re.search(r"['\"]([^'\"]+)['\"]", user_instruction)
            title = m_win.group(1) if m_win else "Remote Desktop*"
            updated["target_window"] = title
            last_task["actions"].insert(0, {
                "id": f"act_{int(time.time())}_win",
                "action_type": "FOCUS_WINDOW",
                "description": f"Focus window {title}",
                "window_title": title,
            })
            added_descriptions.append(f"focus window '{title}'")

        if added_descriptions:
            reply_message = "I have added the following actions: " + ", ".join(added_descriptions) + "."
        else:
            reply_message = "I have analyzed your instruction and updated the workflow in the editor."

        return updated, reply_message

