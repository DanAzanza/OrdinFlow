import { useState } from "react";
import { Brain, FileText, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { PromptDialog } from "@/components/common/PromptDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { DocumentTypeConfig, SkillDefinition } from "@/types/api";

interface ImportSkillEditorProps {
  skill: SkillDefinition;
  docTypes: Record<string, DocumentTypeConfig>;
  onChangeSkill: (patch: Partial<SkillDefinition>) => void;
  onChangeDocTypes: (next: Record<string, DocumentTypeConfig>) => void;
}

export function ImportSkillEditor({
  skill,
  docTypes,
  onChangeSkill,
  onChangeDocTypes,
}: ImportSkillEditorProps) {
  const keys = Object.keys(docTypes);
  const [selectedType, setSelectedType] = useState<string | null>(
    () => keys[0] ?? null,
  );
  const [addTypeOpen, setAddTypeOpen] = useState(false);
  const [addFieldOpen, setAddFieldOpen] = useState(false);
  const [deleteTypeTarget, setDeleteTypeTarget] = useState<string | null>(null);

  const activeKey =
    selectedType && docTypes[selectedType] ? selectedType : keys[0] ?? null;
  const activeDoc = activeKey ? docTypes[activeKey] : null;
  const activeFields = activeDoc?.extraction_fields || {};

  const allowedExtStr = Array.isArray(skill.allowed_extensions)
    ? skill.allowed_extensions.join(", ")
    : String(skill.allowed_extensions || ".pdf, .png, .jpg, .jpeg, .tif, .tiff");

  const updateActiveDoc = (patch: Partial<DocumentTypeConfig>) => {
    if (!activeKey || !activeDoc) return;
    onChangeDocTypes({
      ...docTypes,
      [activeKey]: { ...activeDoc, ...patch },
    });
  };

  const handleAddCategory = (rawName: string) => {
    if (docTypes[rawName]) {
      toast.error(`Category '${rawName}' already exists.`);
      return;
    }
    onChangeDocTypes({
      ...docTypes,
      [rawName]: {
        emoji: "📄",
        classification_desc: "",
        extraction_fields: {
          Document: { description: "Category of the document", required: true },
        },
      },
    });
    setSelectedType(rawName);
  };

  const handleDeleteCategory = () => {
    if (!deleteTypeTarget) return;
    const next = { ...docTypes };
    delete next[deleteTypeTarget];
    onChangeDocTypes(next);
    if (selectedType === deleteTypeTarget) {
      setSelectedType(Object.keys(next)[0] ?? null);
    }
    setDeleteTypeTarget(null);
  };

  const handleAddField = (rawField: string) => {
    if (!activeKey || !activeDoc) return;
    if (activeFields[rawField]) {
      toast.error(`Field '${rawField}' already exists.`);
      return;
    }
    updateActiveDoc({
      extraction_fields: {
        ...activeFields,
        [rawField]: { description: "", required: false },
      },
    });
  };

  const updateField = (
    fieldKey: string,
    prop: "description" | "required",
    val: string | boolean,
  ) => {
    if (!activeKey || !activeDoc) return;
    const existing = activeFields[fieldKey];
    const normalized =
      typeof existing === "string"
        ? { description: existing, required: false }
        : { ...(existing || {}) };

    updateActiveDoc({
      extraction_fields: {
        ...activeFields,
        [fieldKey]: {
          ...normalized,
          [prop]: val,
        },
      },
    });
  };

  const removeField = (fieldKey: string) => {
    if (!activeKey || !activeDoc) return;
    const nextFields = { ...activeFields };
    delete nextFields[fieldKey];
    updateActiveDoc({ extraction_fields: nextFields });
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Import Settings */}
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor="import-ext-input">
            Allowed File Extensions (comma-separated)
          </Label>
          <Input
            id="import-ext-input"
            value={allowedExtStr}
            onChange={(e) =>
              onChangeSkill({
                allowed_extensions: e.target.value
                  .split(",")
                  .map((s) => s.trim().toLowerCase())
                  .filter(Boolean)
                  .map((s) => (s.startsWith(".") ? s : `.${s}`)),
              })
            }
            className="h-8 font-mono text-xs"
          />
        </div>

        <div className="flex flex-wrap gap-6">
          <label className="flex cursor-pointer items-center gap-2 text-xs">
            <Checkbox
              checked={skill.split_multi_documents !== false}
              onCheckedChange={(checked) =>
                onChangeSkill({ split_multi_documents: Boolean(checked) })
              }
            />
            Automatically split multi-document PDF collations
          </label>

          <label className="flex cursor-pointer items-center gap-2 text-xs">
            <Checkbox
              checked={Boolean(skill.save_empty_pages)}
              onCheckedChange={(checked) =>
                onChangeSkill({ save_empty_pages: Boolean(checked) })
              }
            />
            Retain empty scanned pages
          </label>
        </div>
      </div>

      {/* Document Types & Extraction Schema */}
      <div className="grid gap-3 rounded-xl border border-border bg-card p-4 lg:grid-cols-[220px_1fr]">
        {/* Categories Sidebar */}
        <div className="flex flex-col gap-2 border-b border-border pb-3 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Categories
            </span>
            <Button
              variant="outline"
              size="xs"
              onClick={() => setAddTypeOpen(true)}
            >
              <Plus className="h-3 w-3" />
              Add
            </Button>
          </div>

          <div className="flex flex-col gap-1">
            {keys.length === 0 ? (
              <div className="py-4 text-center text-xs text-muted-foreground">
                No categories defined.
              </div>
            ) : (
              keys.map((key) => {
                const count = Object.keys(
                  docTypes[key]?.extraction_fields || {},
                ).length;
                const isSelected = key === activeKey;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSelectedType(key)}
                    className={cn(
                      "flex items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-colors cursor-pointer",
                      isSelected
                        ? "bg-primary/14 font-semibold text-foreground ring-1 ring-primary/30"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-primary" />
                      <span className="truncate">{key}</span>
                    </span>
                    <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                      {count}
                    </Badge>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Category Schema Detail */}
        {activeKey && activeDoc ? (
          <div className="flex min-w-0 flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <h4 className="truncate text-sm font-semibold text-foreground">
                {activeKey}
              </h4>
              <Button
                variant="destructive"
                size="xs"
                onClick={() => setDeleteTypeTarget(activeKey)}
              >
                <Trash2 className="h-3 w-3" />
                Delete Category
              </Button>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="flex items-center gap-1.5">
                <Brain className="h-3.5 w-3.5 text-cyan-400" />
                Recognition &amp; Classification Rules (AI Vision)
              </Label>
              <Textarea
                rows={2}
                value={
                  activeDoc.classification_desc || activeDoc.vision_rules || ""
                }
                onChange={(e) =>
                  updateActiveDoc({
                    classification_desc: e.target.value,
                    vision_rules: e.target.value,
                  })
                }
                placeholder="Describe visual cues, headers, or layout hints..."
                className="text-xs"
              />
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label>Extraction Fields &amp; Prompts</Label>
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => setAddFieldOpen(true)}
                >
                  <Plus className="h-3 w-3" />
                  Add Field
                </Button>
              </div>

              {Object.keys(activeFields).length === 0 ? (
                <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  No extraction fields defined yet.
                </div>
              ) : (
                <div className="divide-y divide-border rounded-lg border border-border">
                  {Object.entries(activeFields).map(([fKey, fVal]) => {
                    const desc =
                      typeof fVal === "string" ? fVal : fVal?.description || "";
                    const required =
                      typeof fVal === "object" && fVal !== null
                        ? Boolean(fVal.required)
                        : false;
                    return (
                      <div
                        key={fKey}
                        className="grid items-center gap-2 p-2.5 sm:grid-cols-[150px_1fr_auto_auto]"
                      >
                        <Input
                          value={fKey}
                          readOnly
                          className="h-8 bg-muted/40 font-mono text-xs"
                        />
                        <Input
                          value={desc}
                          onChange={(e) =>
                            updateField(fKey, "description", e.target.value)
                          }
                          placeholder="AI extraction prompt..."
                          className="h-8 text-xs"
                        />
                        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
                          <Switch
                            checked={required}
                            onCheckedChange={(chk) =>
                              updateField(fKey, "required", chk)
                            }
                          />
                          Req
                        </label>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeField(fKey)}
                          aria-label={`Remove ${fKey}`}
                          className="h-7 w-7 text-rose-400 hover:bg-rose-500/12"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center py-12 text-xs text-muted-foreground">
            Select or create a document category on the left.
          </div>
        )}
      </div>

      <PromptDialog
        open={addTypeOpen}
        onOpenChange={setAddTypeOpen}
        title="Add Document Category"
        label="Category Name"
        placeholder="e.g. Arztbrief, Recipe, Invoice"
        onSubmit={handleAddCategory}
      />

      <PromptDialog
        open={addFieldOpen}
        onOpenChange={setAddFieldOpen}
        title={`Add Extraction Field to ${activeKey || ""}`}
        label="Field Key"
        placeholder="e.g. Nachname, Datum, InvoiceNumber"
        onSubmit={handleAddField}
      />

      <ConfirmDialog
        open={deleteTypeTarget !== null}
        onOpenChange={(open) => !open && setDeleteTypeTarget(null)}
        title="Delete document category?"
        description="Removes this category and its extraction prompts from this import skill."
        targetName={deleteTypeTarget || undefined}
        confirmLabel="Delete Category"
        onConfirm={handleDeleteCategory}
      />
    </div>
  );
}
