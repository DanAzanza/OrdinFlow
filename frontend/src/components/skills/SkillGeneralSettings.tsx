import { ChevronDown, Plus, X } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SkillDefinition } from "@/types/api";

interface SkillGeneralSettingsProps {
  skill: SkillDefinition;
  allSkills: SkillDefinition[];
  availableDocTypes: string[];
  selectedDocTypes: string[];
  onChangeSkill: (patch: Partial<SkillDefinition>) => void;
  onChangeDocTypes: (docTypes: string[]) => void;
}

export function SkillGeneralSettings({
  skill,
  allSkills,
  availableDocTypes,
  selectedDocTypes,
  onChangeSkill,
  onChangeDocTypes,
}: SkillGeneralSettingsProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const exportSubSkills = allSkills.filter(
    (s) => s.type === "export" && s.id !== skill.id,
  );
  const addableTypes = availableDocTypes.filter(
    (name) => !selectedDocTypes.includes(name),
  );

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="skill-name-input">Skill Name</Label>
          <Input
            id="skill-name-input"
            value={skill.name}
            onChange={(e) => onChangeSkill({ name: e.target.value })}
            placeholder="e.g. Export to Practice Software"
            className="h-8 text-xs"
          />
        </div>

        <div className="flex flex-col gap-1">
          <Label htmlFor="skill-type-select">Skill Type</Label>
          <Select
            value={skill.type || "export"}
            onValueChange={(v) => onChangeSkill({ type: v })}
          >
            <SelectTrigger id="skill-type-select" className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="export">
                Export Skill (RDP / GUI Automation)
              </SelectItem>
              <SelectItem value="import">
                Import Skill (Inbox &amp; AI Schema)
              </SelectItem>
              <SelectItem value="gdt">
                GDT 2.1 PVS Export (Satzart 6310)
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="skill-desc-input">Description</Label>
        <Input
          id="skill-desc-input"
          value={skill.description || ""}
          onChange={(e) => onChangeSkill({ description: e.target.value })}
          placeholder="Short description of what this skill automates..."
          className="h-8 text-xs"
        />
      </div>

      {skill.type === "export" && (
        <>
          <div className="flex flex-col gap-1.5">
            <Label>Allowed Document Types (empty = match all)</Label>
            <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-input bg-background/50 p-2">
              {selectedDocTypes.length === 0 ? (
                <span className="text-xs text-muted-foreground">
                  All documents (no filter)
                </span>
              ) : (
                selectedDocTypes.map((dt) => (
                  <Badge key={dt} variant="default" className="gap-1 pr-1">
                    {dt}
                    <button
                      type="button"
                      onClick={() =>
                        onChangeDocTypes(selectedDocTypes.filter((x) => x !== dt))
                      }
                      aria-label={`Remove ${dt}`}
                      className="rounded hover:bg-white/20 cursor-pointer"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))
              )}

              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="xs" className="ml-auto h-6">
                    <Plus className="h-3 w-3" />
                    Add Type
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-52 p-1.5" align="end">
                  {addableTypes.length === 0 ? (
                    <div className="p-2 text-center text-xs text-muted-foreground">
                      All defined document types selected
                    </div>
                  ) : (
                    <div className="flex max-h-48 flex-col gap-0.5 overflow-y-auto">
                      {addableTypes.map((name) => (
                        <button
                          key={name}
                          type="button"
                          onClick={() =>
                            onChangeDocTypes([...selectedDocTypes, name])
                          }
                          className="rounded px-2 py-1.5 text-left text-xs hover:bg-accent cursor-pointer"
                        >
                          {name}
                        </button>
                      ))}
                    </div>
                  )}
                </PopoverContent>
              </Popover>
            </div>
          </div>

          <div>
            <button
              type="button"
              onClick={() => setAdvancedOpen((o) => !o)}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
              />
              Advanced Launch, RDP &amp; Window Settings
            </button>

            {advancedOpen && (
              <div className="mt-2.5 grid gap-3 rounded-lg border border-border bg-background/40 p-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <Label>Fallback Window Title Pattern</Label>
                  <Input
                    value={skill.target_window || ""}
                    onChange={(e) =>
                      onChangeSkill({ target_window: e.target.value })
                    }
                    placeholder="Remote Desktop*"
                    className="h-8 font-mono text-xs"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <Label>RDP Path Prefix Mapping</Label>
                  <Input
                    value={skill.rdp_path_prefix || ""}
                    onChange={(e) =>
                      onChangeSkill({ rdp_path_prefix: e.target.value })
                    }
                    placeholder="\\tsclient\C"
                    className="h-8 font-mono text-xs"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <Label>Launch / Login Sub-Skill</Label>
                  <Select
                    value={skill.launch_skill_id || "__none__"}
                    onValueChange={(v) =>
                      onChangeSkill({
                        launch_skill_id: v === "__none__" ? "" : v,
                      })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">
                        None (Direct execution)
                      </SelectItem>
                      {exportSubSkills.map((s) => (
                        <SelectItem key={s.id} value={s.id}>
                          {s.name || s.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-1">
                  <Label>Executable Fallback Path</Label>
                  <Input
                    value={skill.executable_path || ""}
                    onChange={(e) =>
                      onChangeSkill({ executable_path: e.target.value })
                    }
                    placeholder="C:\Program Files\App\App.exe"
                    className="h-8 font-mono text-xs"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-4 sm:col-span-2">
                  <label className="flex cursor-pointer items-center gap-2 text-xs">
                    <Checkbox
                      checked={Boolean(skill.maximize_window)}
                      onCheckedChange={(checked) =>
                        onChangeSkill({ maximize_window: Boolean(checked) })
                      }
                    />
                    Ensure Window Maximized
                  </label>
                  <label className="flex cursor-pointer items-center gap-2 text-xs">
                    <Checkbox
                      checked={Boolean(skill.recover_hung_process)}
                      onCheckedChange={(checked) =>
                        onChangeSkill({ recover_hung_process: Boolean(checked) })
                      }
                    />
                    Auto-Restart if Process Freezes
                  </label>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
