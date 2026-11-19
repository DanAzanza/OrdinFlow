import { useEffect, useState } from "react";
import { Check, FileText, FolderPen, Plus, Trash2, X } from "lucide-react";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { DocumentPreview } from "@/components/common/DocumentPreview";
import { SplitSectionCard } from "@/components/inspector/SplitSectionCard";
import { useInspectorData } from "@/components/inspector/useInspectorData";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cleanHeaderLabel, isPdfUrl, normalizeDateForInput } from "@/lib/utils";
import type { InspectorState } from "@/types/api";

interface DocumentInspectorProps {
  inspectorState: InspectorState;
  onClose: () => void;
  registerActions: (
    actions: { submit: () => void; requestDelete: () => void } | null,
  ) => void;
}

export function DocumentInspector({
  inspectorState,
  onClose,
  registerActions,
}: DocumentInspectorProps) {
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  const data = useInspectorData(inspectorState, onClose);

  useEffect(() => {
    setConfirmDeleteOpen(false);
  }, [inspectorState]);

  useEffect(() => {
    registerActions({
      submit: () => void data.handleSubmit(),
      requestDelete: () => setConfirmDeleteOpen(true),
    });
    return () => registerActions(null);
  }, [data.handleSubmit, registerActions]);

  const title =
    inspectorState.mode === "folder_edit"
      ? "Edit Case Folder"
      : inspectorState.filename.split("/").pop() || inspectorState.filename;
  const subtitle =
    inspectorState.mode === "folder_edit"
      ? `Folder: ${inspectorState.folder}`
      : inspectorState.mode === "cases"
        ? `Case: ${inspectorState.folder}`
        : "Inbox Document Inspection";

  const showAddSection =
    inspectorState.mode !== "folder_edit" && isPdfUrl(inspectorState.filename);

  return (
    <aside className="flex h-full w-[400px] xl:w-[440px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex h-[52px] shrink-0 items-center justify-between gap-2 border-b border-border px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
            {inspectorState.mode === "folder_edit" ? (
              <FolderPen className="h-4 w-4" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
          </div>
          <div className="min-w-0">
            <h2
              className="truncate text-xs font-semibold text-foreground"
              title={title}
            >
              {title}
            </h2>
            <p
              className="truncate text-[11px] text-muted-foreground"
              title={subtitle}
            >
              {subtitle}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label="Close inspector"
          className="h-7 w-7 shrink-0"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {data.loading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-72 rounded-xl" />
            <Skeleton className="h-48 rounded-xl" />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {(data.previewFileUrl || data.previewThumbUrl) && (
              <DocumentPreview
                fileUrl={data.previewFileUrl}
                previewUrl={data.previewThumbUrl}
                fileName={data.previewFileName}
              />
            )}

            {inspectorState.mode === "folder_edit" ? (
              <div className="rounded-xl border border-border bg-card p-3.5 shadow-xs">
                <div className="mb-3 text-xs font-semibold text-foreground">
                  Metadata &amp; Folder Attributes
                </div>
                <div className="flex flex-col gap-2.5">
                  {data.folderFieldKeys.map((key) => {
                    const label = cleanHeaderLabel(key);
                    const val = data.folderFields[key] ?? "";
                    const isDate =
                      key.toLowerCase().includes("datum") ||
                      key.toLowerCase().includes("date");
                    const iso = isDate ? normalizeDateForInput(val) : null;
                    return (
                      <div key={key} className="flex flex-col gap-1">
                        <Label htmlFor={`folder-insp-${key}`}>{label}</Label>
                        <Input
                          id={`folder-insp-${key}`}
                          type={isDate && (iso !== null || !val) ? "date" : "text"}
                          value={isDate && iso !== null ? iso : val}
                          onChange={(e) =>
                            data.setFolderFields((prev) => ({
                              ...prev,
                              [key]: e.target.value,
                            }))
                          }
                          className="h-8 text-xs"
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {data.sections.map((sec, idx) => (
                  <SplitSectionCard
                    key={sec.id}
                    section={sec}
                    index={idx}
                    canRemove={data.sections.length > 1}
                    docTypeOptions={data.docTypeOptions}
                    docTypes={data.docTypes}
                    config={data.config}
                    onChangeDocType={(nextType) =>
                      data.setSections((prev) =>
                        prev.map((s) =>
                          s.id === sec.id ? { ...s, docType: nextType } : s,
                        ),
                      )
                    }
                    onChangePages={(nextPages) =>
                      data.setSections((prev) =>
                        prev.map((s) =>
                          s.id === sec.id ? { ...s, pages: nextPages } : s,
                        ),
                      )
                    }
                    onChangeField={(k, v) =>
                      data.setSections((prev) =>
                        prev.map((s) =>
                          s.id === sec.id
                            ? { ...s, extracted: { ...s.extracted, [k]: v } }
                            : s,
                        ),
                      )
                    }
                    onRemove={() =>
                      data.setSections((prev) =>
                        prev.filter((s) => s.id !== sec.id),
                      )
                    }
                  />
                ))}

                {showAddSection && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      data.setSections((prev) => [
                        ...prev,
                        {
                          id: `sec_${Date.now()}`,
                          docType: data.docTypeOptions[0] || "Document",
                          pages: "",
                          extracted: { ...data.baseExtracted },
                        },
                      ])
                    }
                    className="w-full"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add document type / page range
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2 border-t border-border bg-card/60 px-4 py-3">
        <Button
          variant="default"
          size="sm"
          disabled={data.loading || data.submitting}
          onClick={() => void data.handleSubmit()}
          className="flex-1"
        >
          <Check className="h-3.5 w-3.5" />
          {inspectorState.mode === "folder_edit"
            ? "Save Folder"
            : "Approve & Move"}
          <kbd className="ml-1 rounded bg-black/25 px-1 py-0.5 font-mono text-[10px]">
            Ctrl+↵
          </kbd>
        </Button>

        <Button
          variant="destructive"
          size="sm"
          disabled={data.loading || data.submitting}
          onClick={() => setConfirmDeleteOpen(true)}
          title="Delete (Alt+Del)"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      <ConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        title={
          inspectorState.mode === "folder_edit"
            ? "Delete entire case folder?"
            : "Move document to recycle bin?"
        }
        description="This action moves the item to the system recycle bin."
        targetName={
          inspectorState.mode === "folder_edit"
            ? inspectorState.folder
            : inspectorState.filename
        }
        confirmLabel="Move to Trash"
        busy={data.deleting}
        onConfirm={async () => {
          await data.handleDelete();
          setConfirmDeleteOpen(false);
        }}
      />
    </aside>
  );
}
