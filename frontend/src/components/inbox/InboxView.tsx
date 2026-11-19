import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Inbox as InboxIcon, Keyboard, Search } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { InboxCard } from "@/components/inbox/InboxCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppState } from "@/hooks/use-app-state";
import { inboxApi } from "@/lib/api-client";
import type { InboxItem } from "@/types/api";

interface InboxViewProps {
  selectedIndex: number;
  onSelectIndex: (index: number) => void;
  deleteTarget: InboxItem | null;
  onDeleteTargetChange: (item: InboxItem | null) => void;
  registerShortcuts?: (handlers: {
    moveSelection: (delta: 1 | -1) => void;
    openSelected: () => void;
    deleteSelected: () => void;
  } | null) => void;
}

export function InboxView({
  selectedIndex,
  onSelectIndex,
  deleteTarget,
  onDeleteTargetChange,
  registerShortcuts,
}: InboxViewProps) {
  const {
    inbox,
    config,
    isLoadingInitial,
    reviewOnly,
    setReviewOnly,
    setInspectorState,
    refreshInbox,
    refreshCases,
  } = useAppState();

  const [search, setSearch] = useState("");
  const [renderedCount, setRenderedCount] = useState(48);
  const [deleting, setDeleting] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return inbox.filter((item) => {
      if (reviewOnly && !Boolean(item.is_review ?? item.is_pruefen)) {
        return false;
      }
      if (q && !(item.name || "").toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [inbox, reviewOnly, search]);

  useEffect(() => {
    setRenderedCount(48);
  }, [search, reviewOnly]);

  useEffect(() => {
    if (selectedIndex >= renderedCount && renderedCount < filtered.length) {
      setRenderedCount((prev) => Math.min(filtered.length, Math.max(prev + 36, selectedIndex + 12)));
    }
  }, [selectedIndex, renderedCount, filtered.length]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || renderedCount >= filtered.length || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setRenderedCount((prev) => Math.min(filtered.length, prev + 36));
        }
      },
      { rootMargin: "320px 0px", threshold: 0.01 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [renderedCount, filtered.length]);

  const reviewCount = useMemo(
    () => inbox.filter((f) => Boolean(f.is_review ?? f.is_pruefen)).length,
    [inbox],
  );

  useEffect(() => {
    if (!registerShortcuts) return;
    registerShortcuts({
      moveSelection: (delta) => {
        if (filtered.length === 0) return;
        const base = selectedIndex < 0 ? (delta > 0 ? -1 : 0) : selectedIndex;
        const next = Math.max(0, Math.min(filtered.length - 1, base + delta));
        onSelectIndex(next);
      },
      openSelected: () => {
        const target = filtered[selectedIndex];
        if (target) {
          setInspectorState({ mode: "inbox", filename: target.path });
        }
      },
      deleteSelected: () => {
        const target = filtered[selectedIndex];
        if (target) {
          onDeleteTargetChange(target);
        }
      },
    });
    return () => registerShortcuts(null);
  }, [
    registerShortcuts,
    filtered,
    selectedIndex,
    onSelectIndex,
    setInspectorState,
    onDeleteTargetChange,
  ]);

  const visibleSlice = filtered.slice(0, renderedCount);

  const handleRetry = async (path: string) => {
    try {
      await inboxApi.retry(path);
      toast.success(`Reprocessing queued: ${path}`);
      await refreshInbox();
    } catch (e) {
      toast.error(`Reprocess failed: ${e instanceof Error ? e.message : "Error"}`);
    }
  };

  const handleAutoAssign = async (path: string) => {
    try {
      await inboxApi.autoAssign(path);
      toast.success("Document assigned to case folder");
      await Promise.all([refreshInbox(), refreshCases()]);
    } catch (e) {
      toast.error(`Assignment error: ${e instanceof Error ? e.message : "Error"}`);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await inboxApi.deleteFile(deleteTarget.path);
      toast.success(`Moved to recycle bin: ${deleteTarget.name}`);
      onDeleteTargetChange(null);
      await refreshInbox();
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
        <div className="flex min-w-[240px] flex-1 items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search inbox files..."
              aria-label="Search documents in inbox"
              className="pl-8"
            />
          </div>

          <Button
            variant={reviewOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setReviewOnly((r) => !r)}
            className="gap-1.5"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>Review Only</span>
            {reviewCount > 0 && (
              <Badge variant={reviewOnly ? "secondary" : "warning"} className="px-1.5 py-0 text-[10px]">
                {reviewCount}
              </Badge>
            )}
          </Button>
        </div>

        <div className="hidden items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-1.5 text-[11px] text-muted-foreground xl:flex">
          <Keyboard className="h-3.5 w-3.5 text-primary" />
          <span>
            <kbd className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">↑↓</kbd> Select
          </span>
          <span>
            <kbd className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">↵</kbd> Inspect
          </span>
          <span>
            <kbd className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">Ctrl+↵</kbd> Approve
          </span>
          <span>
            <kbd className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">F</kbd> Review
          </span>
          <span>
            <kbd className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">Del</kbd> Trash
          </span>
        </div>
      </div>

      {/* Grid / Loading / Empty */}
      {isLoadingInitial ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, idx) => (
            <Skeleton key={idx} className="h-60 rounded-xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={InboxIcon}
          title={reviewOnly ? "No documents awaiting manual review" : "The inbox folder is empty"}
          description={
            config?.watch_dir
              ? `Monitoring: ${config.watch_dir}`
              : "Drop PDFs or scanned documents into the Inbox folder to trigger Dual-Pass VLM extraction."
          }
          action={
            reviewOnly ? (
              <Button variant="outline" size="sm" onClick={() => setReviewOnly(false)}>
                Show all inbox files
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visibleSlice.map((item, idx) => (
              <InboxCard
                key={item.path}
                item={item}
                config={config}
                selected={idx === selectedIndex}
                onInspect={(path) => {
                  onSelectIndex(idx);
                  setInspectorState({ mode: "inbox", filename: path });
                }}
                onRetry={handleRetry}
                onAutoAssign={handleAutoAssign}
                onDelete={(target) => onDeleteTargetChange(target)}
              />
            ))}
          </div>

          {renderedCount < filtered.length && (
            <div
              ref={sentinelRef}
              className="py-4 text-center text-xs text-muted-foreground tabular-nums"
            >
              Showing {renderedCount} of {filtered.length} files...
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && onDeleteTargetChange(null)}
        title="Move document to recycle bin?"
        description="This moves the inbox document and any sidecar metadata to the system recycle bin."
        targetName={deleteTarget?.name}
        confirmLabel="Move to Trash"
        busy={deleting}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}
