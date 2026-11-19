import { ArrowDown, ArrowUp, CircleDot, Layers, Plus, Trash2 } from "lucide-react";
import { SkillActionRow } from "@/components/skills/SkillActionRow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SkillAction, SkillTask } from "@/types/api";

interface SkillFlowEditorProps {
  tasks: SkillTask[];
  availableVars: string[];
  onChangeTasks: (tasks: SkillTask[]) => void;
  onStartRecording: () => void;
  onPickElement: (taskIdx: number, actIdx: number) => void;
}

export function SkillFlowEditor({
  tasks,
  availableVars,
  onChangeTasks,
  onStartRecording,
  onPickElement,
}: SkillFlowEditorProps) {
  const totalActions = tasks.reduce(
    (sum, t) => sum + (t.actions ? t.actions.length : 0),
    0,
  );

  const addTask = () => {
    const idx = tasks.length + 1;
    onChangeTasks([
      ...tasks,
      {
        id: `task_${idx}_${Date.now()}`,
        title: `Task ${idx}`,
        actions: [
          {
            id: `act_${Date.now()}_1`,
            action_type: "CLICK",
            description: "Click on element",
            locator: { type: "auto", prompt: "" },
            delay_ms: 300,
          },
        ],
      },
    ]);
  };

  const removeTask = (taskIdx: number) => {
    onChangeTasks(tasks.filter((_, idx) => idx !== taskIdx));
  };

  const moveTask = (taskIdx: number, delta: -1 | 1) => {
    const target = taskIdx + delta;
    if (target < 0 || target >= tasks.length) return;
    const copy = [...tasks];
    const current = copy[taskIdx];
    const swap = copy[target];
    if (!current || !swap) return;
    copy[taskIdx] = swap;
    copy[target] = current;
    onChangeTasks(copy);
  };

  const updateTaskTitle = (taskIdx: number, title: string) => {
    onChangeTasks(
      tasks.map((t, idx) => (idx === taskIdx ? { ...t, title } : t)),
    );
  };

  const addAction = (taskIdx: number) => {
    onChangeTasks(
      tasks.map((t, idx) => {
        if (idx !== taskIdx) return t;
        const newAction: SkillAction = {
          id: `act_${Date.now()}_${(t.actions?.length || 0) + 1}`,
          action_type: "CLICK",
          description: "Click on element",
          locator: { type: "auto", prompt: "" },
          delay_ms: 300,
        };
        return { ...t, actions: [...(t.actions || []), newAction] };
      }),
    );
  };

  const updateAction = (
    taskIdx: number,
    actIdx: number,
    updated: SkillAction,
  ) => {
    onChangeTasks(
      tasks.map((t, tIdx) => {
        if (tIdx !== taskIdx) return t;
        return {
          ...t,
          actions: (t.actions || []).map((a, aIdx) =>
            aIdx === actIdx ? updated : a,
          ),
        };
      }),
    );
  };

  const moveAction = (taskIdx: number, actIdx: number, delta: -1 | 1) => {
    onChangeTasks(
      tasks.map((t, tIdx) => {
        if (tIdx !== taskIdx) return t;
        const actions = [...(t.actions || [])];
        const target = actIdx + delta;
        if (target < 0 || target >= actions.length) return t;
        const cur = actions[actIdx];
        const swap = actions[target];
        if (!cur || !swap) return t;
        actions[actIdx] = swap;
        actions[target] = cur;
        return { ...t, actions };
      }),
    );
  };

  const removeAction = (taskIdx: number, actIdx: number) => {
    onChangeTasks(
      tasks.map((t, tIdx) =>
        tIdx === taskIdx
          ? {
              ...t,
              actions: (t.actions || []).filter((_, aIdx) => aIdx !== actIdx),
            }
          : t,
      ),
    );
  };

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-primary" />
          <h4 className="text-sm font-semibold">Tasks &amp; Actions Timeline</h4>
          <Badge variant="outline" className="tabular-nums">
            {tasks.length} Tasks · {totalActions} Actions
          </Badge>
        </div>

        <Button variant="destructive" size="sm" onClick={onStartRecording}>
          <CircleDot className="h-3.5 w-3.5" />
          Start Live Recording
        </Button>
      </div>

      {tasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-background/40 px-4 py-10 text-center">
          <p className="text-xs font-medium text-foreground">
            No automation tasks configured yet
          </p>
          <p className="max-w-md text-[11px] text-muted-foreground">
            Start a Live Recording on your desktop, ask the AI Copilot, or add a task manually below.
          </p>
          <div className="mt-2 flex gap-2">
            <Button variant="destructive" size="sm" onClick={onStartRecording}>
              <CircleDot className="h-3.5 w-3.5" />
              Live Record
            </Button>
            <Button variant="outline" size="sm" onClick={addTask}>
              <Plus className="h-3.5 w-3.5" />
              Add Task
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {tasks.map((task, taskIdx) => {
            const actions = task.actions || [];
            return (
              <div
                key={task.id || taskIdx}
                className="rounded-xl border border-border bg-surface/60 p-3"
              >
                <div className="mb-2.5 flex items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <Badge variant="default" className="shrink-0">
                      Task {taskIdx + 1}
                    </Badge>
                    <Input
                      value={task.title || ""}
                      onChange={(e) => updateTaskTitle(taskIdx, e.target.value)}
                      placeholder="Task title..."
                      className="h-8 text-xs font-medium"
                    />
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={taskIdx === 0}
                      onClick={() => moveTask(taskIdx, -1)}
                      aria-label="Move task up"
                      className="h-7 w-7"
                    >
                      <ArrowUp className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={taskIdx === tasks.length - 1}
                      onClick={() => moveTask(taskIdx, 1)}
                      aria-label="Move task down"
                      className="h-7 w-7"
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeTask(taskIdx)}
                      aria-label="Delete task"
                      className="h-7 w-7 text-rose-400 hover:bg-rose-500/12 hover:text-rose-300"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                <div className="ml-2 flex flex-col gap-2 border-l-2 border-primary/25 pl-3">
                  {actions.length === 0 ? (
                    <div className="py-2 text-xs text-muted-foreground">
                      No actions in this task yet.
                    </div>
                  ) : (
                    actions.map((act, actIdx) => (
                      <SkillActionRow
                        key={act.id || `${taskIdx}-${actIdx}`}
                        action={act}
                        index={actIdx}
                        total={actions.length}
                        availableVars={availableVars}
                        onChange={(updated) =>
                          updateAction(taskIdx, actIdx, updated)
                        }
                        onMove={(delta) => moveAction(taskIdx, actIdx, delta)}
                        onRemove={() => removeAction(taskIdx, actIdx)}
                        onPickElement={() => onPickElement(taskIdx, actIdx)}
                      />
                    ))
                  )}

                  <Button
                    variant="outline"
                    size="xs"
                    onClick={() => addAction(taskIdx)}
                    className="self-start"
                  >
                    <Plus className="h-3 w-3" />
                    Add Action to Task {taskIdx + 1}
                  </Button>
                </div>
              </div>
            );
          })}

          <Button variant="outline" size="sm" onClick={addTask} className="self-start">
            <Plus className="h-3.5 w-3.5" />
            Add New Task
          </Button>
        </div>
      )}
    </div>
  );
}
