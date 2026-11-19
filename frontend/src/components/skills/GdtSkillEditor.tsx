import { useState } from "react";
import { FolderOpen, Plus, Stethoscope, Trash2 } from "lucide-react";
import { PromptDialog } from "@/components/common/PromptDialog";
import { PathPickerDialog } from "@/components/settings/PathPickerDialog";
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
import { Switch } from "@/components/ui/switch";
import type { GdtDocTypeMapping, SkillDefinition } from "@/types/api";

interface GdtSkillEditorProps {
  skill: SkillDefinition;
  onChangeSkill: (patch: Partial<SkillDefinition>) => void;
}

export function GdtSkillEditor({ skill, onChangeSkill }: GdtSkillEditorProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [addMappingOpen, setAddMappingOpen] = useState(false);

  const docMap: Record<string, GdtDocTypeMapping> =
    skill.document_types &&
    !Array.isArray(skill.document_types) &&
    typeof skill.document_types === "object"
      ? (skill.document_types as Record<string, GdtDocTypeMapping>)
      : {};

  const updateMapping = (docType: string, targetCategory: string) => {
    onChangeSkill({
      document_types: {
        ...docMap,
        [docType]: { ...(docMap[docType] || {}), target_category: targetCategory },
      },
    });
  };

  const removeMapping = (docType: string) => {
    const next = { ...docMap };
    delete next[docType];
    onChangeSkill({ document_types: next });
  };

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <Stethoscope className="h-4 w-4 text-emerald-400" />
        <h4 className="text-sm font-semibold">
          GDT 2.1 PVS Interface Settings (Satzart 6310)
        </h4>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label>PVS Transfer Target Directory</Label>
          <div className="flex gap-2">
            <Input
              value={skill.target_dir || "./PVS_Transfer"}
              onChange={(e) => onChangeSkill({ target_dir: e.target.value })}
              className="h-8 font-mono text-xs"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPickerOpen(true)}
            >
              <FolderOpen className="h-3.5 w-3.5" />
              Browse
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <Label>Character Encoding (Tag 9206)</Label>
          <Select
            value={skill.codepage || "cp437"}
            onValueChange={(v) => onChangeSkill({ codepage: v })}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="cp437">cp437 (DOS Standard - Code 2)</SelectItem>
              <SelectItem value="iso-8859-1">
                iso-8859-1 (ANSI / Latin-1 - Code 3)
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <Label>Output Filename Prefix</Label>
          <Input
            value={skill.filename_prefix || "ORDINFLOW"}
            onChange={(e) => onChangeSkill({ filename_prefix: e.target.value })}
            className="h-8 font-mono text-xs"
          />
        </div>

        <div className="flex flex-col gap-1">
          <Label>Sender ID (Tag 8316, max 8 chars)</Label>
          <Input
            value={skill.sender_id || "ORDINFLOW"}
            onChange={(e) => onChangeSkill({ sender_id: e.target.value })}
            className="h-8 font-mono text-xs"
          />
        </div>

        <div className="flex flex-col gap-1">
          <Label>Receiver ID (Tag 8315)</Label>
          <Input
            value={skill.receiver_id || "PVS"}
            onChange={(e) => onChangeSkill({ receiver_id: e.target.value })}
            className="h-8 font-mono text-xs"
          />
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-3 py-2 sm:col-span-2">
          <Label htmlFor="gdt-semaphore" className="cursor-pointer text-xs text-foreground">
            Write accompanying semaphore trigger file (.sem) after atomic rename
          </Label>
          <Switch
            id="gdt-semaphore"
            checked={Boolean(skill.write_semaphore)}
            onCheckedChange={(chk) => onChangeSkill({ write_semaphore: chk })}
          />
        </div>
      </div>

      {/* Document Type -> PVS Target Category Mapping */}
      <div className="mt-1 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label>Document Type to PVS Category Mapping</Label>
          <Button
            variant="outline"
            size="xs"
            onClick={() => setAddMappingOpen(true)}
          >
            <Plus className="h-3 w-3" />
            Add Mapping
          </Button>
        </div>

        {Object.keys(docMap).length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
            No document type mappings configured.
          </div>
        ) : (
          <div className="divide-y divide-border rounded-lg border border-border">
            {Object.entries(docMap).map(([dt, cfg]) => (
              <div
                key={dt}
                className="grid items-center gap-2 p-2 sm:grid-cols-[1fr_1fr_auto]"
              >
                <Input
                  value={dt}
                  readOnly
                  className="h-8 bg-muted/40 font-mono text-xs"
                />
                <Input
                  value={cfg?.target_category || ""}
                  onChange={(e) => updateMapping(dt, e.target.value)}
                  placeholder="PVS category (e.g. Befund)"
                  className="h-8 text-xs"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => removeMapping(dt)}
                  aria-label={`Remove ${dt}`}
                  className="h-7 w-7 text-rose-400 hover:bg-rose-500/12"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <PathPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        title="Select PVS GDT Transfer Folder"
        pickerType="folder"
        initialPath={skill.target_dir || ""}
        onSelect={(path) => onChangeSkill({ target_dir: path })}
      />

      <PromptDialog
        open={addMappingOpen}
        onOpenChange={setAddMappingOpen}
        title="Add GDT Document Type Mapping"
        label="OrdinFlow Document Type"
        placeholder="e.g. Arztbrief, Laborbefund"
        onSubmit={(dt) => updateMapping(dt, dt)}
      />
    </div>
  );
}
