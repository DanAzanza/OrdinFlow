import { useEffect, useMemo, useRef, useState } from "react";
import { Eraser, Search } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { PipelineAnalyticsPanel } from "@/components/logs/PipelineAnalyticsPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAppState } from "@/hooks/use-app-state";
import { systemApi } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type LevelFilter = "ALL" | "INFO" | "WARN" | "ERROR";

export function LogsView() {
  const { logRecords, logStats, clearLocalLogs, refreshLogStats } = useAppState();

  const [levelFilter, setLevelFilter] = useState<LevelFilter>("ALL");
  const [search, setSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  const consoleRef = useRef<HTMLDivElement>(null);

  const filteredLogs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return logRecords.filter((item) => {
      const lvl = (item.level || "").toUpperCase();
      if (levelFilter === "INFO" && lvl !== "INFO") return false;
      if (levelFilter === "WARN" && lvl !== "WARN" && lvl !== "WARNING") return false;
      if (levelFilter === "ERROR" && lvl !== "ERROR" && lvl !== "CRITICAL") return false;
      if (q) {
        const full = `${item.time || ""} ${lvl} ${item.message || ""}`.toLowerCase();
        return full.includes(q);
      }
      return true;
    });
  }, [logRecords, levelFilter, search]);

  useEffect(() => {
    if (autoScroll && consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [filteredLogs, autoScroll]);

  const handleClearLog = async () => {
    setClearing(true);
    try {
      await systemApi.clearLogs();
      clearLocalLogs();
      await refreshLogStats(true);
      setClearConfirmOpen(false);
      toast.success("Logs cleared");
    } catch (e) {
      clearLocalLogs();
      setClearConfirmOpen(false);
      toast.error(`Error clearing logs: ${e instanceof Error ? e.message : "Error"}`);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4">
      <PipelineAnalyticsPanel stats={logStats} />

      {/* Log Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-3.5 py-2.5">
        <div className="flex min-w-[240px] flex-1 flex-wrap items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter log stream..."
              aria-label="Search system logs"
              className="h-8 pl-8 text-xs"
            />
          </div>

          <div className="flex items-center gap-1">
            {(
              [
                { id: "ALL", label: "All" },
                { id: "INFO", label: "Info" },
                { id: "WARN", label: "Warnings" },
                { id: "ERROR", label: "Errors" },
              ] as const
            ).map((btn) => (
              <Button
                key={btn.id}
                variant={levelFilter === btn.id ? "default" : "outline"}
                size="xs"
                onClick={() => setLevelFilter(btn.id)}
              >
                {btn.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="default">{filteredLogs.length} entries</Badge>
          <Badge variant="info">INFO: {logStats?.infoCount ?? 0}</Badge>
          <Badge variant="warning">WARN: {logStats?.warnCount ?? 0}</Badge>
          <Badge variant="destructive">ERR: {logStats?.errorCount ?? 0}</Badge>

          <div className="flex items-center gap-1.5 pl-2">
            <Switch
              id="log-autoscroll"
              checked={autoScroll}
              onCheckedChange={setAutoScroll}
            />
            <Label htmlFor="log-autoscroll" className="cursor-pointer text-xs">
              Auto-scroll
            </Label>
          </div>

          <Button
            variant="destructive"
            size="xs"
            onClick={() => setClearConfirmOpen(true)}
          >
            <Eraser className="h-3 w-3" />
            Clear
          </Button>
        </div>
      </div>

      {/* Console output */}
      <div
        ref={consoleRef}
        className="min-h-[260px] flex-1 overflow-y-auto rounded-xl border border-border bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-200"
      >
        {filteredLogs.length === 0 ? (
          <div className="py-12 text-center text-zinc-500">
            Waiting for pipeline events...
          </div>
        ) : (
          filteredLogs.map((entry) => {
            const lvl = (entry.level || "INFO").toUpperCase();
            const isErr = lvl === "ERROR" || lvl === "CRITICAL";
            const isWarn = lvl.includes("WARN");
            return (
              <div
                key={entry.id}
                className={cn(
                  "flex gap-2 rounded px-1.5 py-0.5 hover:bg-white/5",
                  isErr
                    ? "text-rose-300"
                    : isWarn
                      ? "text-amber-300"
                      : "text-zinc-200",
                )}
              >
                <span className="shrink-0 text-zinc-500 tabular-nums">
                  [{entry.time || "--:--:--"}]
                </span>
                <span
                  className={cn(
                    "w-14 shrink-0 font-semibold",
                    isErr
                      ? "text-rose-400"
                      : isWarn
                        ? "text-amber-400"
                        : "text-cyan-400",
                  )}
                >
                  [{lvl}]
                </span>
                <span className="break-all">{entry.message || ""}</span>
              </div>
            );
          })
        )}
      </div>

      <ConfirmDialog
        open={clearConfirmOpen}
        onOpenChange={setClearConfirmOpen}
        title="Clear system logs?"
        description="This clears the in-memory stream buffer and truncates active local log files."
        confirmLabel="Clear Logs"
        busy={clearing}
        onConfirm={handleClearLog}
      />
    </div>
  );
}
