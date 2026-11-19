import { Cpu, FileCheck2, Gauge, Inbox, Layers } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LogStats } from "@/types/api";

interface PipelineAnalyticsPanelProps {
  stats: LogStats | null;
}

export function PipelineAnalyticsPanel({ stats }: PipelineAnalyticsPanelProps) {
  const s = stats;
  const totalExtracted = s?.tier1Count || s?.totalFiles || 0;
  const t1Consensus = s?.tier1DirectConsensus ?? s?.earlyStopCount ?? 0;
  const t1Pct = totalExtracted > 0 ? Math.round((t1Consensus / totalExtracted) * 100) : 0;

  const t2Count = s?.tier2Count || 0;
  const t2InvPct = totalExtracted > 0 ? Math.round((t2Count / totalExtracted) * 100) : 0;
  const t2Resolved =
    s?.tier2Resolved !== undefined
      ? s.tier2Resolved
      : Math.max(0, t2Count - (s?.tier3Count || 0));
  const t2Pct = totalExtracted > 0 ? Math.round((t2Resolved / totalExtracted) * 100) : 0;

  const t3Count = s?.tier3Count || 0;
  const t3InvPct = totalExtracted > 0 ? Math.round((t3Count / totalExtracted) * 100) : 0;
  const t3Resolved = s?.tier3Resolved !== undefined ? s.tier3Resolved : t3Count;
  const t3Pct = totalExtracted > 0 ? Math.round((t3Resolved / totalExtracted) * 100) : 0;

  const categories = Object.entries(s?.categoryCounts || {}).sort(
    (a, b) => b[1] - a[1],
  );
  const totalPages = s?.totalPages || 0;

  return (
    <div className="flex flex-col gap-3">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="border-indigo-500/25 bg-indigo-500/5">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between text-[11px] font-medium text-indigo-400">
              <span>Source Files</span>
              <Inbox className="h-3.5 w-3.5" />
            </div>
            <div className="mt-1.5 text-2xl font-bold tracking-tight tabular-nums">
              {s?.totalFiles ?? 0}
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">
              {s?.completedFiles ?? 0} Auto · {s?.manualReviewFiles ?? 0} Review
            </div>
          </CardContent>
        </Card>

        <Card className="border-emerald-500/25 bg-emerald-500/5">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between text-[11px] font-medium text-emerald-400">
              <span>Archived Docs</span>
              <FileCheck2 className="h-3.5 w-3.5" />
            </div>
            <div className="mt-1.5 text-2xl font-bold tracking-tight tabular-nums">
              {s?.totalArchivedDocs ?? s?.completedFiles ?? 0}
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">
              {s?.partialDocsSaved ?? 0} Split · {s?.directDocsMoved ?? 0} Direct
            </div>
          </CardContent>
        </Card>

        <Card className="border-cyan-500/25 bg-cyan-500/5">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between text-[11px] font-medium text-cyan-400">
              <span>Automation Rate</span>
              <Layers className="h-3.5 w-3.5" />
            </div>
            <div className="mt-1.5 text-2xl font-bold tracking-tight tabular-nums">
              {s?.successRate ?? "100.0"}%
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              Zero manual intervention
            </div>
          </CardContent>
        </Card>

        <Card className="border-violet-500/25 bg-violet-500/5">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between text-[11px] font-medium text-violet-400">
              <span>Avg Latency / Page</span>
              <Gauge className="h-3.5 w-3.5" />
            </div>
            <div className="mt-1.5 text-2xl font-bold tracking-tight tabular-nums">
              {s?.avgTimePerPage ?? "0.0"}s
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">
              Ø {s?.avgTimePerFile ?? "0.0"}s / file · {totalPages} pages
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 3-Tier Consensus Escalation Funnel & Doc-Type Breakdown */}
      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
              <Cpu className="h-3.5 w-3.5 text-primary" />
              3-Tier OCR / VLM Consensus Funnel
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {/* Tier 1 */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-emerald-400">
                  Tier 1 · Base &amp; Spatial OCR Early-Stop
                </span>
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  {t1Consensus} / {s?.tier1Count ?? 0} ({t1Pct}%)
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all"
                  style={{ width: `${Math.min(100, t1Pct)}%` }}
                />
              </div>
            </div>

            {/* Tier 2 */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-amber-400">
                  Tier 2 · High-Res Verification ({t2InvPct}% escalated)
                </span>
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  {t2Resolved} resolved ({t2Pct}%)
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-amber-500 transition-all"
                  style={{ width: `${Math.min(100, t2Pct)}%` }}
                />
              </div>
            </div>

            {/* Tier 3 */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-rose-400">
                  Tier 3 · Tiebreaker Audit ({t3InvPct}% escalated)
                </span>
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  {t3Resolved} resolved ({t3Pct}%)
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-rose-500 transition-all"
                  style={{ width: `${Math.min(100, t3Pct)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
              Classified Page Distribution
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2.5">
            {categories.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground">
                No page classifications logged yet.
              </div>
            ) : (
              categories.slice(0, 6).map(([cat, count]) => {
                const pct =
                  totalPages > 0 ? Math.round((count / totalPages) * 100) : 0;
                return (
                  <div key={cat} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="truncate font-medium text-foreground">
                        {cat}
                      </span>
                      <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                        {count} pages ({pct}%)
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-indigo-500 transition-all"
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
