import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  FolderKanban,
  Pencil,
  Rocket,
  Search,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { CaseFilesGrid } from "@/components/cases/CaseFilesGrid";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppState } from "@/hooks/use-app-state";
import { casesApi } from "@/lib/api-client";
import {
  cleanHeaderLabel,
  formatDateString,
  getEffectiveDocTypes,
  parseDateToTimestamp,
} from "@/lib/utils";
import type { CaseFile } from "@/types/api";

const textCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

interface CasesViewProps {
  expandedFolder: string | null;
  onExpandedFolderChange: (folder: string | null) => void;
}

export function CasesView({
  expandedFolder,
  onExpandedFolderChange,
}: CasesViewProps) {
  const {
    cases,
    config,
    skills,
    isLoadingInitial,
    setInspectorState,
    refreshCases,
  } = useAppState();

  const [search, setSearch] = useState("");
  const [sortCol, setSortCol] = useState<number>(0);
  const [sortAsc, setSortAsc] = useState<boolean>(true);
  const [sortAnnouncement, setSortAnnouncement] = useState("");
  const [expandedFiles, setExpandedFiles] = useState<CaseFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);

  const [deleteFolderTarget, setDeleteFolderTarget] = useState<string | null>(null);
  const [deleteFileTarget, setDeleteFileTarget] = useState<{
    folder: string;
    filename: string;
  } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const folderStructure = useMemo(
    () => (Array.isArray(config?.folder_structure) ? config.folder_structure : []),
    [config?.folder_structure],
  );

  const docTypesMap = useMemo(
    () => getEffectiveDocTypes(skills, config),
    [skills, config],
  );

  const legendEntries = useMemo(
    () =>
      Object.entries(docTypesMap).filter(
        ([name, info]) =>
          name.toUpperCase() !== "UNKNOWN" && info?.routing?.archive !== false,
      ),
    [docTypesMap],
  );

  const loadFolderDetail = useCallback(async (folder: string) => {
    setLoadingFiles(true);
    try {
      const detail = await casesApi.getDetail(folder);
      setExpandedFiles(detail.files || []);
    } catch {
      setExpandedFiles([]);
    } finally {
      setLoadingFiles(false);
    }
  }, []);

  useEffect(() => {
    if (!expandedFolder) {
      setExpandedFiles([]);
      return;
    }
    const stillExists = cases.some((c) => c.folder === expandedFolder);
    if (!stillExists && cases.length > 0) {
      onExpandedFolderChange(null);
      setExpandedFiles([]);
      return;
    }
    void loadFolderDetail(expandedFolder);
  }, [expandedFolder, cases, loadFolderDetail, onExpandedFolderChange]);

  const sortedCases = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = cases.filter(
      (item) =>
        !q ||
        item.folder.toLowerCase().includes(q) ||
        (item.parts || []).some((p) => String(p).toLowerCase().includes(q)),
    );

    return [...filtered].sort((a, b) => {
      const va = a.parts?.[sortCol] ?? "";
      const vb = b.parts?.[sortCol] ?? "";
      const tsA = parseDateToTimestamp(va);
      const tsB = parseDateToTimestamp(vb);
      if (tsA !== null && tsB !== null) {
        return sortAsc ? tsA - tsB : tsB - tsA;
      }
      const cmp = textCollator.compare(String(va), String(vb));
      return sortAsc ? cmp : -cmp;
    });
  }, [cases, search, sortCol, sortAsc]);

  const handleSort = (idx: number, label: string) => {
    let nextAsc = true;
    if (sortCol === idx) {
      nextAsc = !sortAsc;
      setSortAsc(nextAsc);
    } else {
      setSortCol(idx);
      setSortAsc(true);
    }
    setSortAnnouncement(
      `Sorted by ${label}, ${nextAsc ? "ascending" : "descending"}, ${sortedCases.length} rows`,
    );
  };

  const handleApproveToggle = async (folder: string, currentApproved: boolean) => {
    try {
      await casesApi.approve(folder, !currentApproved);
      toast.success(
        !currentApproved
          ? "Case approved and queued for export skills"
          : "Case approval revoked",
      );
      await refreshCases();
    } catch (e) {
      toast.error(`Approval failed: ${e instanceof Error ? e.message : "Error"}`);
    }
  };

  const handleDeleteFolder = async () => {
    if (!deleteFolderTarget) return;
    setDeleting(true);
    try {
      await casesApi.deleteFolder(deleteFolderTarget);
      toast.success(`Case deleted: ${deleteFolderTarget}`);
      if (expandedFolder === deleteFolderTarget) {
        onExpandedFolderChange(null);
      }
      setDeleteFolderTarget(null);
      await refreshCases();
    } catch (e) {
      toast.error(`Delete failed: ${e instanceof Error ? e.message : "Error"}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteFile = async () => {
    if (!deleteFileTarget) return;
    setDeleting(true);
    try {
      await casesApi.deleteFile(deleteFileTarget.folder, deleteFileTarget.filename);
      toast.success(`Moved to recycle bin: ${deleteFileTarget.filename}`);
      const folder = deleteFileTarget.folder;
      setDeleteFileTarget(null);
      await Promise.all([refreshCases(), loadFolderDetail(folder)]);
    } catch (e) {
      toast.error(`Delete failed: ${e instanceof Error ? e.message : "Error"}`);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search archived cases..."
            aria-label="Search archived cases"
            className="pl-8"
          />
        </div>

        {legendEntries.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium text-muted-foreground">
              Types:
            </span>
            {legendEntries.map(([name]) => (
              <Badge key={name} variant="outline" className="text-[11px]">
                <FileText className="h-3 w-3 text-primary" />
                {name}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Live screen-reader sort announcer */}
      <div role="status" className="sr-only">
        {sortAnnouncement}
      </div>

      {/* Table */}
      {isLoadingInitial ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, idx) => (
            <Skeleton key={idx} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : sortedCases.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="No archived cases found"
          description="Processed documents from Inbox will appear here grouped by your dynamic folder hierarchy."
        />
      ) : (
        <div
          role="region"
          aria-label="Archived case folders"
          tabIndex={0}
          className="overflow-x-auto rounded-xl border border-border bg-card shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <table className="w-full min-w-[720px] border-collapse text-left text-xs">
            <caption className="sr-only">Archived case folders</caption>
            <thead>
              <tr className="border-b border-border bg-surface/80 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {folderStructure.map((comp, idx) => {
                  const label = cleanHeaderLabel(comp);
                  const isSorted = sortCol === idx;
                  return (
                    <th
                      key={comp}
                      scope="col"
                      aria-sort={
                        isSorted
                          ? sortAsc
                            ? "ascending"
                            : "descending"
                          : undefined
                      }
                      className="p-0"
                    >
                      <button
                        type="button"
                        onClick={() => handleSort(idx, label)}
                        className="flex min-h-9 w-full items-center gap-1.5 px-3 py-2 text-left transition-colors hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring cursor-pointer"
                      >
                        <span>{label}</span>
                        {isSorted ? (
                          sortAsc ? (
                            <ArrowUp className="h-3 w-3 text-primary" aria-hidden="true" />
                          ) : (
                            <ArrowDown className="h-3 w-3 text-primary" aria-hidden="true" />
                          )
                        ) : (
                          <ArrowUpDown className="h-3 w-3 opacity-35" aria-hidden="true" />
                        )}
                      </button>
                    </th>
                  );
                })}
                <th scope="col" className="px-3 py-2">
                  Documents &amp; Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/70">
              {sortedCases.map((c) => {
                const isExpanded = expandedFolder === c.folder;

                return (
                  <Fragment key={c.folder}>
                    <tr
                      onClick={() =>
                        onExpandedFolderChange(isExpanded ? null : c.folder)
                      }
                      className="cursor-pointer transition-colors hover:bg-accent/40"
                    >
                      {folderStructure.map((comp, idx) => {
                        let val = c.parts?.[idx] || "–";
                        if (
                          /^\d{4}-\d{2}-\d{2}$/.test(val) ||
                          /^\d{2}-\d{2}-\d{4}$/.test(val)
                        ) {
                          val = formatDateString(val);
                        }
                        return (
                          <td
                            key={`${c.folder}-${comp}`}
                            className="px-3 py-2.5 align-middle"
                          >
                            <div className="flex items-center gap-1.5">
                              {idx === 0 &&
                                (isExpanded ? (
                                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-primary" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                                ))}
                              {idx === 1 && folderStructure.length > 2 ? (
                                <Badge variant="secondary">{val}</Badge>
                              ) : (
                                <span className="font-medium text-foreground tabular-nums">
                                  {val}
                                </span>
                              )}
                            </div>
                          </td>
                        );
                      })}

                      <td
                        className="px-3 py-2.5 align-middle"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-1">
                            {(c.doc_types || []).slice(0, 4).map((dt) => (
                              <Badge key={dt} variant="outline" className="text-[10px]">
                                {dt}
                              </Badge>
                            ))}
                            <span className="ml-1 text-[11px] text-muted-foreground tabular-nums">
                              ({c.file_count})
                            </span>
                          </div>

                          <div className="flex items-center gap-1.5">
                            {c.export_status === "completed" ? (
                              <Badge variant="success">
                                <CheckCircle2 className="h-3 w-3" />
                                Completed
                              </Badge>
                            ) : c.export_status === "partially_exported" ? (
                              <Badge variant="warning">
                                <Clock className="h-3 w-3" />
                                In Progress
                                {c.total_applicable_tasks > 0 &&
                                  ` (${c.completed_applicable_tasks}/${c.total_applicable_tasks})`}
                              </Badge>
                            ) : c.is_approved ? (
                              <Button
                                variant="outline"
                                size="xs"
                                onClick={() =>
                                  void handleApproveToggle(c.folder, true)
                                }
                                title="Click to revoke approval"
                                className="border-cyan-500/35 bg-cyan-500/12 text-cyan-700 dark:text-cyan-300"
                              >
                                <CheckCircle2 className="h-3 w-3" />
                                Approved
                              </Button>
                            ) : (
                              <Button
                                variant="default"
                                size="xs"
                                onClick={() =>
                                  void handleApproveToggle(c.folder, false)
                                }
                                title="Approve case for export skills"
                              >
                                <Rocket className="h-3 w-3" />
                                Approve
                              </Button>
                            )}

                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() =>
                                setInspectorState({
                                  mode: "folder_edit",
                                  folder: c.folder,
                                })
                              }
                              title="Edit folder metadata"
                              aria-label={`Edit folder ${c.folder}`}
                              className="h-7 w-7"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>

                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setDeleteFolderTarget(c.folder)}
                              title="Delete case folder"
                              aria-label={`Delete folder ${c.folder}`}
                              className="h-7 w-7 text-rose-400 hover:bg-rose-500/12 hover:text-rose-300"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="bg-background/50">
                        <td colSpan={folderStructure.length + 1} className="p-4">
                          <CaseFilesGrid
                            files={expandedFiles}
                            loading={loadingFiles}
                            onInspectFile={(filename) =>
                              setInspectorState({
                                mode: "cases",
                                folder: c.folder,
                                filename,
                              })
                            }
                            onDeleteFile={(filename) =>
                              setDeleteFileTarget({ folder: c.folder, filename })
                            }
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={deleteFolderTarget !== null}
        onOpenChange={(open) => !open && setDeleteFolderTarget(null)}
        title="Delete entire case folder?"
        description="This moves the selected case folder and all contained documents to the system recycle bin."
        targetName={deleteFolderTarget || undefined}
        confirmLabel="Delete Case"
        busy={deleting}
        onConfirm={handleDeleteFolder}
      />

      <ConfirmDialog
        open={deleteFileTarget !== null}
        onOpenChange={(open) => !open && setDeleteFileTarget(null)}
        title="Delete archived file?"
        description="This moves the archived document and its metadata sidecar to the recycle bin."
        targetName={
          deleteFileTarget
            ? `${deleteFileTarget.folder}/${deleteFileTarget.filename}`
            : undefined
        }
        confirmLabel="Delete File"
        busy={deleting}
        onConfirm={handleDeleteFile}
      />
    </div>
  );
}
