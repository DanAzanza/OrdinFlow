import { Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { RecorderStatus } from "@/types/api";

interface LiveRecorderBarProps {
  status: RecorderStatus;
  onStop: () => void;
}

export function LiveRecorderBar({ status, onStop }: LiveRecorderBarProps) {
  if (!status.is_recording) return null;

  const totalSec = Math.floor(
    status.elapsed_seconds ?? status.duration_seconds ?? 0,
  );
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  const timerStr = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;

  return (
    <div className="fixed bottom-5 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-popover/95 px-4 py-2.5 shadow-2xl backdrop-blur-md">
      <div className="flex min-w-0 items-center gap-3">
        <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-rose-500 animate-ping" />
        <span className="shrink-0 text-xs font-bold tracking-wide text-rose-400">
          LIVE RECORDING
        </span>
        <span className="shrink-0 font-mono text-xs font-semibold text-foreground tabular-nums">
          {timerStr}
        </span>
        <Badge variant="destructive" className="shrink-0">
          {status.step_count ?? 0} actions
        </Badge>
        <span className="hidden truncate text-xs text-muted-foreground sm:inline">
          {status.last_action || "Capturing mouse clicks & keyboard input..."}
        </span>
      </div>

      <Button
        variant="destructive"
        size="sm"
        onClick={onStop}
        className="shrink-0"
      >
        <Square className="h-3 w-3 fill-current" />
        Stop Recording
      </Button>
    </div>
  );
}
