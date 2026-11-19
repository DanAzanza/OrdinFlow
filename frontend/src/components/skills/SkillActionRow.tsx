import { useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Check,
  Crosshair,
  Eye,
  EyeOff,
  Lock,
  Pencil,
  Trash2,
  Unlock,
} from "lucide-react";
import {
  ACTION_TYPE_OPTIONS,
  getActionParamSummary,
  getActionStyleMeta,
} from "@/components/skills/SkillActionMeta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn, isActionSensitive } from "@/lib/utils";
import type { SkillAction } from "@/types/api";

interface SkillActionRowProps {
  action: SkillAction;
  index: number;
  total: number;
  availableVars: string[];
  onChange: (updated: SkillAction) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
  onPickElement: () => void;
}

export function SkillActionRow({
  action,
  index,
  total,
  availableVars,
  onChange,
  onMove,
  onRemove,
  onPickElement,
}: SkillActionRowProps) {
  const [editing, setEditing] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const meta = getActionStyleMeta(action.action_type);
  const Icon = meta.icon;
  const sensitive = isActionSensitive(action);
  const paramText = getActionParamSummary(action, sensitive, revealed);

  const normType = String(action.action_type || "").toUpperCase();
  const canPick = [
    "CLICK",
    "DOUBLE_CLICK",
    "RIGHT_CLICK",
    "WAIT_FOR_ELEMENT",
    "VERIFY_SCREEN",
    "EXTRACT_UI_TEXT",
  ].includes(normType);
  const showVars = normType === "TYPE_TEXT" || normType === "TYPE_FILE_PATH";

  const updateProp = (patch: Partial<SkillAction>) => {
    onChange({ ...action, ...patch });
  };

  const insertVariable = (varToken: string) => {
    if (normType === "TYPE_FILE_PATH") {
      updateProp({ file_path: `${action.file_path || ""}${varToken}` });
    } else if (normType === "TYPE_TEXT") {
      updateProp({ text: `${action.text || ""}${varToken}` });
    }
  };

  const onErrorStr =
    typeof action.on_error === "string" ? action.on_error : "ABORT";

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        editing
          ? "border-primary/45 bg-card"
          : "border-border/80 bg-background/40 hover:border-border",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div className="flex min-w-0 flex-1 items-start gap-2.5">
          <span
            className={cn(
              "inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
              meta.badgeClass,
            )}
          >
            <Icon className="h-3 w-3" />
            {meta.label}
          </span>

          {sensitive && (
            <Badge variant="warning" className="shrink-0">
              <Lock className="h-2.5 w-2.5" />
              Secret
            </Badge>
          )}

          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium text-foreground">
              {action.description || action.action_type || "Action"}
            </div>
            {paramText && (
              <div
                className="truncate font-mono text-[11px] text-muted-foreground"
                title={sensitive && !revealed ? "Sensitive value masked" : paramText}
              >
                {paramText}
              </div>
            )}
            {showVars && availableVars.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {availableVars.slice(0, 8).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => insertVariable(v)}
                    className="rounded border border-primary/25 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-indigo-600 dark:text-indigo-300 transition-colors hover:bg-primary/20 cursor-pointer"
                    title={`Insert ${v}`}
                  >
                    + {v}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant={editing ? "default" : "outline"}
            size="xs"
            onClick={() => setEditing((e) => !e)}
          >
            {editing ? (
              <>
                <Check className="h-3 w-3" /> Done
              </>
            ) : (
              <>
                <Pencil className="h-3 w-3" /> Edit
              </>
            )}
          </Button>

          {canPick && (
            <Button
              variant="outline"
              size="xs"
              onClick={onPickElement}
              title="Pick UI element on screen live"
            >
              <Crosshair className="h-3 w-3 text-cyan-400" />
              Pick
            </Button>
          )}

          {normType === "TYPE_TEXT" && sensitive && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setRevealed((r) => !r)}
              aria-label={revealed ? "Hide secret text" : "Reveal secret text"}
              className="h-7 w-7"
            >
              {revealed ? (
                <EyeOff className="h-3.5 w-3.5" />
              ) : (
                <Eye className="h-3.5 w-3.5" />
              )}
            </Button>
          )}

          {normType === "TYPE_TEXT" && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => updateProp({ is_secret: !action.is_secret })}
              aria-label={
                action.is_secret ? "Unmark secret" : "Mark as secret credential"
              }
              title={action.is_secret ? "Secret enabled" : "Mark as secret"}
              className="h-7 w-7"
            >
              {action.is_secret ? (
                <Lock className="h-3.5 w-3.5 text-amber-400" />
              ) : (
                <Unlock className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </Button>
          )}

          <Button
            variant="ghost"
            size="icon"
            disabled={index === 0}
            onClick={() => onMove(-1)}
            aria-label="Move action up"
            className="h-7 w-7"
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            disabled={index === total - 1}
            onClick={() => onMove(1)}
            aria-label="Move action down"
            className="h-7 w-7"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onRemove}
            aria-label="Remove action"
            className="h-7 w-7 text-rose-400 hover:bg-rose-500/12 hover:text-rose-300"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Inline Editor */}
      {editing && (
        <div className="grid gap-2.5 border-t border-border bg-surface/60 p-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label>Action Type</Label>
            <Select
              value={normType || "CLICK"}
              onValueChange={(v) => updateProp({ action_type: v })}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACTION_TYPE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1">
            <Label>Description</Label>
            <Input
              value={action.description || ""}
              onChange={(e) => updateProp({ description: e.target.value })}
              className="h-8 text-xs"
            />
          </div>

          {normType === "TYPE_TEXT" && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>Text to Type</Label>
              <Input
                type={sensitive && !revealed ? "password" : "text"}
                value={action.text || ""}
                onChange={(e) => updateProp({ text: e.target.value })}
                placeholder="Text or placeholder e.g. {Nachname}"
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {normType === "TYPE_FILE_PATH" && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>File Path</Label>
              <Input
                value={action.file_path || "{document_fullpath}"}
                onChange={(e) => updateProp({ file_path: e.target.value })}
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {(normType === "HOTKEY" || normType === "PRESS_KEY") && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>Keys (comma-separated, e.g. ctrl, s)</Label>
              <Input
                value={
                  Array.isArray(action.keys)
                    ? action.keys.join(", ")
                    : String(action.keys || "")
                }
                onChange={(e) =>
                  updateProp({
                    keys: e.target.value
                      .split(",")
                      .map((k) => k.trim())
                      .filter(Boolean),
                  })
                }
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {normType === "FOCUS_WINDOW" && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>Window Title Pattern</Label>
              <Input
                value={action.window_title || ""}
                onChange={(e) => updateProp({ window_title: e.target.value })}
                placeholder="CorelDRAW*"
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {(normType === "DELAY" || normType === "SLEEP" || normType === "WAIT") && (
            <div className="flex flex-col gap-1">
              <Label>Delay (ms)</Label>
              <Input
                type="number"
                value={
                  action.delay_ms ??
                  (action.duration_s !== undefined ? action.duration_s * 1000 : 500)
                }
                onChange={(e) =>
                  updateProp({ delay_ms: parseInt(e.target.value, 10) || 0 })
                }
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {canPick && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>Locator Target (Prompt / OCR / Automation ID)</Label>
              <Input
                value={
                  action.locator?.prompt ||
                  action.locator?.value ||
                  action.locator?.automation_id ||
                  ""
                }
                onChange={(e) =>
                  updateProp({
                    locator: {
                      ...(action.locator || { type: "auto" }),
                      prompt: e.target.value,
                    },
                  })
                }
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {(normType === "BRANCH" ||
            normType === "IF_CONDITION" ||
            normType === "VALIDATE_UI_STATE" ||
            normType === "WHILE_LOOP") && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>Condition Expression</Label>
              <Input
                value={
                  typeof action.condition === "string"
                    ? action.condition
                    : action.condition?.expr || ""
                }
                onChange={(e) => updateProp({ condition: e.target.value })}
                placeholder="{category} == 'Arztbrief'"
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {(normType === "POWERSHELL" ||
            normType === "RUN_SCRIPT" ||
            normType === "EXECUTE_COMMAND" ||
            normType === "SCRIPT") && (
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label>Command / Script</Label>
              <Textarea
                rows={4}
                value={action.command || action.script || ""}
                onChange={(e) => updateProp({ command: e.target.value })}
                className="font-mono text-xs"
              />
            </div>
          )}

          {normType === "SET_VARIABLE" && (
            <>
              <div className="flex flex-col gap-1">
                <Label>Variable Name</Label>
                <Input
                  value={action.variable || ""}
                  onChange={(e) => updateProp({ variable: e.target.value })}
                  className="h-8 font-mono text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label>Value</Label>
                <Input
                  value={action.value || ""}
                  onChange={(e) => updateProp({ value: e.target.value })}
                  className="h-8 font-mono text-xs"
                />
              </div>
            </>
          )}

          {normType === "EXTRACT_UI_TEXT" && (
            <div className="flex flex-col gap-1">
              <Label>Save Variable</Label>
              <Input
                value={action.extract_to_var || action.variable || ""}
                onChange={(e) => updateProp({ extract_to_var: e.target.value })}
                placeholder="ui_patient_id"
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          {normType === "CALL_SKILL" && (
            <div className="flex flex-col gap-1">
              <Label>Target Skill ID</Label>
              <Input
                value={action.skill_id || ""}
                onChange={(e) => updateProp({ skill_id: e.target.value })}
                className="h-8 font-mono text-xs"
              />
            </div>
          )}

          <div className="flex flex-col gap-1">
            <Label>On Error</Label>
            <Select
              value={onErrorStr}
              onValueChange={(v) => updateProp({ on_error: v })}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ABORT">Abort &amp; Stop Workflow</SelectItem>
                <SelectItem value="CONTINUE">Ignore &amp; Continue</SelectItem>
                <SelectItem value="RETRY">Retry Step (up to 3x)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
    </div>
  );
}
