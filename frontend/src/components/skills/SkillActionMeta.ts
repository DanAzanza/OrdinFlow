import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  CheckCircle2,
  Clock,
  Crosshair,
  Database,
  Download,
  Eye,
  FileInput,
  GitBranch,
  Hourglass,
  Keyboard,
  MousePointerClick,
  Repeat,
  SearchCheck,
  Terminal,
  Zap,
} from "lucide-react";
import type { SkillAction } from "@/types/api";

export interface ActionStyleMeta {
  label: string;
  icon: LucideIcon;
  badgeClass: string;
}

export function getActionStyleMeta(actionType: string | undefined): ActionStyleMeta {
  const norm = String(actionType || "").toUpperCase();
  switch (norm) {
    case "FOCUS_WINDOW":
      return {
        label: "Focus Window",
        icon: AppWindow,
        badgeClass: "border-slate-500/30 bg-slate-500/12 text-slate-300",
      };
    case "CLICK":
      return {
        label: "Click",
        icon: Crosshair,
        badgeClass: "border-indigo-500/30 bg-indigo-500/12 text-indigo-300",
      };
    case "DOUBLE_CLICK":
      return {
        label: "Double Click",
        icon: MousePointerClick,
        badgeClass: "border-indigo-500/30 bg-indigo-500/12 text-indigo-300",
      };
    case "RIGHT_CLICK":
      return {
        label: "Right Click",
        icon: MousePointerClick,
        badgeClass: "border-indigo-500/30 bg-indigo-500/12 text-indigo-300",
      };
    case "TYPE_TEXT":
      return {
        label: "Type Text",
        icon: Keyboard,
        badgeClass: "border-cyan-500/30 bg-cyan-500/12 text-cyan-300",
      };
    case "TYPE_FILE_PATH":
      return {
        label: "File Path",
        icon: FileInput,
        badgeClass: "border-emerald-500/30 bg-emerald-500/12 text-emerald-300",
      };
    case "VERIFY_SCREEN":
      return {
        label: "Verify Screen",
        icon: Eye,
        badgeClass: "border-violet-500/30 bg-violet-500/12 text-violet-300",
      };
    case "WAIT_FOR_ELEMENT":
      return {
        label: "Wait For Element",
        icon: Hourglass,
        badgeClass: "border-amber-500/30 bg-amber-500/12 text-amber-300",
      };
    case "CALL_SKILL":
      return {
        label: "Call Sub-Skill",
        icon: Zap,
        badgeClass: "border-violet-500/30 bg-violet-500/12 text-violet-300",
      };
    case "POWERSHELL":
    case "RUN_SCRIPT":
    case "EXECUTE_COMMAND":
    case "SCRIPT":
      return {
        label: "PowerShell / Script",
        icon: Terminal,
        badgeClass: "border-violet-500/30 bg-violet-500/12 text-violet-300",
      };
    case "HOTKEY":
    case "PRESS_KEY":
      return {
        label: "Hotkey / Key",
        icon: Keyboard,
        badgeClass: "border-cyan-500/30 bg-cyan-500/12 text-cyan-300",
      };
    case "SLEEP":
    case "DELAY":
    case "WAIT":
      return {
        label: "Delay",
        icon: Clock,
        badgeClass: "border-amber-500/30 bg-amber-500/12 text-amber-300",
      };
    case "BRANCH":
    case "IF_CONDITION":
      return {
        label: "Branch (IF/ELSE)",
        icon: GitBranch,
        badgeClass: "border-violet-500/30 bg-violet-500/12 text-violet-300",
      };
    case "FOR_EACH_DOCUMENT":
      return {
        label: "For Each Doc",
        icon: Repeat,
        badgeClass: "border-emerald-500/30 bg-emerald-500/12 text-emerald-300",
      };
    case "FOR_EACH":
      return {
        label: "For Each Item",
        icon: Repeat,
        badgeClass: "border-indigo-500/30 bg-indigo-500/12 text-indigo-300",
      };
    case "WHILE_LOOP":
      return {
        label: "While Loop",
        icon: Hourglass,
        badgeClass: "border-amber-500/30 bg-amber-500/12 text-amber-300",
      };
    case "EXTRACT_UI_TEXT":
      return {
        label: "Extract UI Text",
        icon: Download,
        badgeClass: "border-emerald-500/30 bg-emerald-500/12 text-emerald-300",
      };
    case "VALIDATE_UI_STATE":
      return {
        label: "Validate UI State",
        icon: SearchCheck,
        badgeClass: "border-violet-500/30 bg-violet-500/12 text-violet-300",
      };
    case "SET_VARIABLE":
      return {
        label: "Set Variable",
        icon: Database,
        badgeClass: "border-cyan-500/30 bg-cyan-500/12 text-cyan-300",
      };
    default:
      return {
        label: norm || "Action",
        icon: CheckCircle2,
        badgeClass: "border-border bg-secondary text-secondary-foreground",
      };
  }
}

export function getActionParamSummary(
  act: SkillAction,
  isSensitive: boolean,
  revealed: boolean,
): string {
  const norm = String(act.action_type || "").toUpperCase();
  if (norm === "FOCUS_WINDOW") return act.window_title || "Remote Desktop*";
  if (norm === "TYPE_FILE_PATH") return act.file_path || "{document_fullpath}";
  if (norm === "TYPE_TEXT") {
    if (isSensitive && !revealed) return "••••••••••••";
    return act.text || "";
  }
  if (norm === "WAIT_FOR_ELEMENT") {
    const loc = act.locator?.prompt || act.locator?.value || act.locator?.target || "Element";
    return `${loc} (${act.timeout_s ?? 5}s timeout)`;
  }
  if (norm === "CALL_SKILL") return `Skill: ${act.skill_id || ""}`;
  if (norm === "HOTKEY" || norm === "PRESS_KEY") {
    return Array.isArray(act.keys) ? act.keys.join(" + ") : String(act.keys || "");
  }
  if (norm === "DELAY" || norm === "SLEEP" || norm === "WAIT") {
    const ms =
      act.delay_ms !== undefined
        ? act.delay_ms
        : act.duration_s !== undefined
          ? act.duration_s * 1000
          : 500;
    return `${ms} ms`;
  }
  if (act.locator) {
    return (
      act.locator.prompt ||
      act.locator.value ||
      act.locator.target ||
      act.locator.automation_id ||
      ""
    );
  }
  return "";
}

export const ACTION_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "CLICK", label: "Click Element" },
  { value: "DOUBLE_CLICK", label: "Double Click" },
  { value: "RIGHT_CLICK", label: "Right Click" },
  { value: "TYPE_TEXT", label: "Type Text" },
  { value: "TYPE_FILE_PATH", label: "Type File Path" },
  { value: "HOTKEY", label: "Hotkey / Shortcut" },
  { value: "FOCUS_WINDOW", label: "Focus Window" },
  { value: "WAIT_FOR_ELEMENT", label: "Wait For Element" },
  { value: "VERIFY_SCREEN", label: "Verify Screen" },
  { value: "DELAY", label: "Delay / Pause" },
  { value: "FOR_EACH_DOCUMENT", label: "For Each Document (Loop)" },
  { value: "BRANCH", label: "Branch (IF / ELSE)" },
  { value: "FOR_EACH", label: "For Each Item (Loop)" },
  { value: "WHILE_LOOP", label: "While Condition (Polling)" },
  { value: "EXTRACT_UI_TEXT", label: "Extract UI Text" },
  { value: "VALIDATE_UI_STATE", label: "Validate UI State" },
  { value: "SET_VARIABLE", label: "Set Variable" },
  { value: "POWERSHELL", label: "PowerShell / Script" },
  { value: "CALL_SKILL", label: "Call Sub-Skill" },
];
