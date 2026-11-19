import { useState } from "react";
import {
  GripVertical,
  Pause,
  Play,
  Plus,
  Square,
  Trash2,
  Workflow,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { queueApi } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { SkillDefinition, SkillQueueState } from "@/types/api";

interface SkillQueuePanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  queue: SkillQueueState;
  skills: SkillDefinition[];
  onRefreshQueue: () => Promise<SkillQueueState | null>;
}

export function SkillQueuePanel({
  open,
  onOpenChange,
  queue,
  skills,
  onRefreshQueue,
}: SkillQueuePanelProps) {
  const [selectedSkillToAdd, setSelectedSkillToAdd] = useState<string>(
    () => skills[0]?.id || "",
  );
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const effectiveSkillId =
    selectedSkillToAdd && skills.some((s) => s.id === selectedSkillToAdd)
      ? selectedSkillToAdd
      : skills[0]?.id || "";

  const isRunning = Boolean(queue.is_running);
  const isPaused = Boolean(queue.is_paused);

  const runAction = async (fn: () => Promise<unknown>, successMsg?: string) => {
    setBusy(true);
    try {
      await fn();
      if (successMsg) toast.success(successMsg);
      await onRefreshQueue();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Queue operation failed");
    } finally {
      setBusy(false);
    }
  };

  const handleDrop = async (targetId: string) => {
    setDragOverId(null);
    if (!draggedId || draggedId === targetId) {
      setDraggedId(null);
      return;
    }
    const ids = queue.items.map((i) => i.id);
    const fromIdx = ids.indexOf(draggedId);
    const toIdx = ids.indexOf(targetId);
    setDraggedId(null);
    if (fromIdx === -1 || toIdx === -1) return;

    const reordered = [...ids];
    reordered.splice(fromIdx, 1);
    reordered.splice(toIdx, 0, draggedId);
    await runAction(() => queueApi.reorder(reordered));
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            <span>Skill Execution Queue</span>
          </SheetTitle>
          <SheetDescription>
            {isRunning && !isPaused
              ? `Running: ${queue.active_item?.skill_name || "Executing..."}`
              : isPaused
                ? "Queue paused"
                : queue.auto_repeat_enabled
                  ? "Auto-run enabled (every 5 min)"
                  : "Ready for queued execution"}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          {/* Status Control Card */}
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">
                Status:{" "}
                {isRunning && !isPaused
                  ? "Running"
                  : isPaused
                    ? "Paused"
                    : "Ready"}
              </span>
              <Badge
                variant={
                  isRunning && !isPaused
                    ? "success"
                    : isPaused
                      ? "warning"
                      : "secondary"
                }
              >
                {queue.items.length} Tasks
              </Badge>
            </div>

            <div className="flex gap-2">
              {isRunning && !isPaused ? (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() => void runAction(queueApi.pause, "Queue paused")}
                    className="flex-1"
                  >
                    <Pause className="h-3.5 w-3.5" />
                    Pause
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={busy}
                    onClick={() => void runAction(queueApi.stop, "Queue stopped")}
                    className="flex-1"
                  >
                    <Square className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                </>
              ) : isPaused ? (
                <>
                  <Button
                    variant="default"
                    size="sm"
                    disabled={busy}
                    onClick={() => void runAction(queueApi.resume, "Queue resumed")}
                    className="flex-1"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Resume
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={busy}
                    onClick={() => void runAction(queueApi.stop, "Queue stopped")}
                    className="flex-1"
                  >
                    <Square className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                </>
              ) : (
                <Button
                  variant="default"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    void runAction(async () => {
                      const res = await queueApi.start();
                      if (res.status === "started") {
                        toast.success("Skill queue started");
                      } else {
                        toast.info("No pending tasks in queue");
                      }
                    })
                  }
                  className="w-full"
                >
                  <Play className="h-3.5 w-3.5" />
                  Start Queue
                </Button>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-border pt-2.5">
              <Label htmlFor="queue-auto-repeat" className="cursor-pointer text-xs">
                Auto-run queue every 5 min
              </Label>
              <Switch
                id="queue-auto-repeat"
                checked={Boolean(queue.auto_repeat_enabled)}
                onCheckedChange={(chk) =>
                  void runAction(
                    () => queueApi.setAutoRepeat(chk, 300),
                    chk ? "Auto-run enabled" : "Auto-run disabled",
                  )
                }
              />
            </div>
          </div>

          {/* Add to Queue */}
          <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3.5">
            <Label className="text-xs font-semibold text-foreground">
              Add Skill to Queue
            </Label>
            <div className="flex gap-2">
              <Select
                value={effectiveSkillId}
                onValueChange={setSelectedSkillToAdd}
                disabled={skills.length === 0}
              >
                <SelectTrigger className="h-8 flex-1 text-xs">
                  <SelectValue placeholder="Select skill..." />
                </SelectTrigger>
                <SelectContent>
                  {skills.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name || s.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                size="sm"
                disabled={!effectiveSkillId || busy}
                onClick={() =>
                  void runAction(
                    () => queueApi.add(effectiveSkillId, {}),
                    "Added skill to queue",
                  )
                }
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </Button>
            </div>
          </div>

          {/* Queue Items List */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground">
                Queued Tasks
              </span>
              {queue.items.length > 0 && (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() =>
                    void runAction(queueApi.clear, "Queue cleared")
                  }
                >
                  Clear All
                </Button>
              )}
            </div>

            {queue.items.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
                Queue is empty. Add a skill above or enable auto-run.
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {queue.items.map((item) => {
                  const itemRunning = item.status === "running";
                  const pct = item.progress?.percent ?? 0;
                  return (
                    <div
                      key={item.id}
                      draggable={!itemRunning}
                      onDragStart={(e) => {
                        setDraggedId(item.id);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragOverId(item.id);
                      }}
                      onDragLeave={() => setDragOverId(null)}
                      onDrop={(e) => {
                        e.preventDefault();
                        void handleDrop(item.id);
                      }}
                      onDragEnd={() => {
                        setDraggedId(null);
                        setDragOverId(null);
                      }}
                      className={cn(
                        "rounded-lg border bg-card p-2.5 transition-colors",
                        dragOverId === item.id
                          ? "border-primary bg-primary/10"
                          : "border-border",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <GripVertical className="h-3.5 w-3.5 shrink-0 cursor-grab text-muted-foreground" />
                          <Workflow className="h-3.5 w-3.5 shrink-0 text-primary" />
                          <div className="min-w-0">
                            <div className="truncate text-xs font-medium">
                              {item.skill_name}
                            </div>
                            {itemRunning && item.progress?.message && (
                              <div className="truncate text-[11px] text-muted-foreground">
                                {item.progress.message}
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="flex shrink-0 items-center gap-1.5">
                          <Badge
                            variant={
                              item.status === "completed"
                                ? "success"
                                : item.status === "failed"
                                  ? "destructive"
                                  : item.status === "paused"
                                    ? "warning"
                                    : item.status === "running"
                                      ? "info"
                                      : "secondary"
                            }
                          >
                            {item.status}
                          </Badge>
                          {!itemRunning && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() =>
                                void runAction(() => queueApi.remove(item.id))
                              }
                              aria-label="Remove queue item"
                              className="h-6 w-6 text-rose-400 hover:bg-rose-500/12"
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          )}
                        </div>
                      </div>

                      {itemRunning && pct > 0 && (
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-primary transition-all"
                            style={{ width: `${Math.min(100, pct)}%` }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
