import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CornerLeftUp,
  FileCode2,
  FileText,
  Folder,
  HardDrive,
  MapPin,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { systemApi } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { FsEntry, FsListResponse } from "@/types/api";

interface PathPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  pickerType: "folder" | "file";
  fileFilter?: string;
  initialPath?: string;
  onSelect: (chosenPath: string) => void;
}

export function PathPickerDialog({
  open,
  onOpenChange,
  title,
  pickerType,
  fileFilter = "",
  initialPath = "",
  onSelect,
}: PathPickerDialogProps) {
  const [data, setData] = useState<FsListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterQuery, setFilterQuery] = useState("");
  const [selectedPath, setSelectedPath] = useState("");
  const [inputValue, setInputValue] = useState("");

  const abortRef = useRef<AbortController | null>(null);
  const selectedPathRef = useRef(selectedPath);
  selectedPathRef.current = selectedPath;

  const loadDirectory = useCallback(
    async (targetPath: string) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      setLoading(true);
      setError(null);
      setFilterQuery("");

      try {
        const clean = targetPath.trim().replace(/^["']+|["']+$/g, "");
        const res = await systemApi.listFilesystem(
          {
            path: clean,
            type: pickerType,
            filter: fileFilter,
          },
          ctrl.signal,
        );
        if (ctrl.signal.aborted) return;

        setData(res);
        if (pickerType === "folder" || !selectedPathRef.current) {
          setSelectedPath(res.current_path);
          setInputValue(res.current_path);
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof Error ? e.message : "Failed to load directory");
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    },
    [pickerType, fileFilter],
  );

  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
      return;
    }
    const cleanInit = (initialPath || "").trim().replace(/^["']+|["']+$/g, "");
    setSelectedPath(cleanInit);
    setInputValue(cleanInit);
    void loadDirectory(cleanInit);
    return () => {
      abortRef.current?.abort();
    };
  }, [open, initialPath, loadDirectory]);

  const filteredEntries = useMemo(() => {
    const entries = data?.entries || [];
    const q = filterQuery.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((e) => e.name.toLowerCase().includes(q));
  }, [data?.entries, filterQuery]);

  const handleConfirm = useCallback(() => {
    const chosen = (inputValue || selectedPath || data?.current_path || "")
      .trim()
      .replace(/^["']+|["']+$/g, "");
    if (!chosen) return;
    onSelect(chosen);
    onOpenChange(false);
  }, [inputValue, selectedPath, data?.current_path, onSelect, onOpenChange]);

  const handleEntryClick = (entry: FsEntry) => {
    setSelectedPath(entry.path);
    setInputValue(entry.path);
  };

  const handleEntryDoubleClick = (entry: FsEntry) => {
    if (entry.is_dir) {
      void loadDirectory(entry.path);
    } else {
      setSelectedPath(entry.path);
      setInputValue(entry.path);
      onSelect(entry.path);
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-2xl"
        onKeyDown={(e) => {
          const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
          if (tag === "input" || tag === "textarea") return;

          if (e.key === "Backspace" && data?.parent_path) {
            e.preventDefault();
            void loadDirectory(data.parent_path);
            return;
          }

          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            if (filteredEntries.length === 0) return;
            const curIdx = filteredEntries.findIndex(
              (entry) => entry.path === selectedPath,
            );
            const delta = e.key === "ArrowDown" ? 1 : -1;
            const nextIdx =
              curIdx === -1
                ? delta > 0
                  ? 0
                  : filteredEntries.length - 1
                : (curIdx + delta + filteredEntries.length) % filteredEntries.length;
            const target = filteredEntries[nextIdx];
            if (target) {
              setSelectedPath(target.path);
              setInputValue(target.path);
            }
            return;
          }

          if (e.key === "Enter") {
            e.preventDefault();
            const chosenEntry = filteredEntries.find(
              (entry) => entry.path === selectedPath,
            );
            if (chosenEntry?.is_dir) {
              void loadDirectory(chosenEntry.path);
            } else {
              handleConfirm();
            }
          }
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Folder className="h-4 w-4 text-primary" />
            <span>{title}</span>
          </DialogTitle>
          <DialogDescription>
            Browse local folders or {fileFilter ? `${fileFilter} ` : ""}files on this machine.
          </DialogDescription>
        </DialogHeader>

        {/* Drives & Quick Locations */}
        <div className="flex flex-col gap-2">
          {data?.drives && data.drives.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {data.drives.map((drv) => {
                const isActive = Boolean(
                  data.current_path?.toUpperCase().startsWith(drv.toUpperCase()),
                );
                return (
                  <Button
                    key={drv}
                    variant={isActive ? "default" : "outline"}
                    size="xs"
                    onClick={() => void loadDirectory(drv)}
                  >
                    <HardDrive className="h-3 w-3" />
                    {drv}
                  </Button>
                );
              })}
            </div>
          )}

          {data?.quick_locations && data.quick_locations.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {data.quick_locations.map((loc) => (
                <Button
                  key={loc.path}
                  variant="secondary"
                  size="xs"
                  onClick={() => void loadDirectory(loc.path)}
                >
                  <MapPin className="h-3 w-3 text-cyan-400" />
                  {loc.name}
                </Button>
              ))}
            </div>
          )}
        </div>

        {/* Breadcrumbs */}
        {data?.breadcrumbs && data.breadcrumbs.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border bg-background/60 px-2.5 py-1.5 font-mono text-xs">
            {data.breadcrumbs.map((crumb, idx) => {
              const isLast = idx === data.breadcrumbs.length - 1;
              return (
                <span key={crumb.path} className="flex items-center gap-1">
                  {idx > 0 && <span className="text-muted-foreground">/</span>}
                  <button
                    type="button"
                    onClick={() => void loadDirectory(crumb.path)}
                    className={cn(
                      "rounded px-1 py-0.5 transition-colors hover:bg-accent cursor-pointer",
                      isLast
                        ? "font-semibold text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {crumb.name}
                  </button>
                </span>
              );
            })}
          </div>
        )}

        {/* Instant Filter */}
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="Quick filter items in this directory..."
            aria-label="Filter directory entries"
            className="h-8 pl-8 text-xs"
          />
        </div>

        {/* Entries list */}
        <div className="relative h-64 overflow-y-auto rounded-lg border border-border bg-background/50">
          {loading && (
            <div className="sticky top-0 z-10 h-0.5 w-full animate-pulse bg-primary" />
          )}

          <div className={cn("divide-y divide-border/50", loading && "opacity-60")}>
            {data?.truncated && (
              <div className="flex items-center gap-2 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                Showing first 1,000 entries. Use filter to narrow results.
              </div>
            )}

            {data?.parent_path && (
              <button
                type="button"
                onClick={() => void loadDirectory(data.parent_path!)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground cursor-pointer"
              >
                <span className="flex items-center gap-2">
                  <CornerLeftUp className="h-3.5 w-3.5" />
                  .. (Parent directory)
                </span>
                <span className="text-[11px]">Open</span>
              </button>
            )}

            {error ? (
              <div className="p-6 text-center text-xs text-rose-400">{error}</div>
            ) : filteredEntries.length === 0 ? (
              <div className="p-8 text-center text-xs text-muted-foreground">
                {loading
                  ? "Loading directory..."
                  : pickerType === "file"
                    ? "No matching files found in this directory."
                    : "This directory contains no subfolders."}
              </div>
            ) : (
              filteredEntries.map((entry) => {
                const isSelected = selectedPath === entry.path;
                const isGguf = entry.name.toLowerCase().endsWith(".gguf");
                return (
                  <div
                    key={entry.path}
                    onClick={() => handleEntryClick(entry)}
                    onDoubleClick={() => handleEntryDoubleClick(entry)}
                    className={cn(
                      "flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-xs transition-colors",
                      isSelected
                        ? "bg-primary/15 text-foreground"
                        : "hover:bg-accent/50 text-foreground/90",
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      {entry.is_dir ? (
                        <Folder className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                      ) : isGguf ? (
                        <FileCode2 className="h-3.5 w-3.5 shrink-0 text-violet-400" />
                      ) : (
                        <FileText className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                      )}
                      <span className="truncate font-medium" title={entry.name}>
                        {entry.name}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground tabular-nums">
                      {entry.size_str && <span>{entry.size_str}</span>}
                      {entry.modified_str && <span>{entry.modified_str}</span>}
                      {entry.is_dir && (
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            void loadDirectory(entry.path);
                          }}
                          className="h-6 px-2 text-[11px]"
                        >
                          Open
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Selected path bar */}
        <div className="flex items-center gap-2">
          <Label htmlFor="path-picker-selected" className="shrink-0">
            Selected Path:
          </Label>
          <Input
            id="path-picker-selected"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const cleaned = inputValue.trim().replace(/^["']+|["']+$/g, "");
                if (!cleaned) return;
                if (cleaned === selectedPath) {
                  handleConfirm();
                } else {
                  void loadDirectory(cleaned);
                }
              }
            }}
            className="h-8 font-mono text-xs"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleConfirm}>Select Path</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
