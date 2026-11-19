import { ListTodo, Radio, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NavTab, SkillQueueState } from "@/types/api";

const TAB_META: Record<NavTab, { title: string; subtitle: string }> = {
  inbox: {
    title: "Document Inbox",
    subtitle: "Review incoming scans, verify VLM extractions, and route files",
  },
  cases: {
    title: "Cases Explorer",
    subtitle: "Structured client folders, approvals, and RPA export tracking",
  },
  skills: {
    title: "Agentic Skill Studio",
    subtitle: "Visual RPA timelines, AI Copilot authoring, and document schemas",
  },
  logs: {
    title: "Pipeline Telemetry & Logs",
    subtitle: "3-Tier OCR/VLM consensus metrics and live diagnostic stream",
  },
  settings: {
    title: "System Configuration",
    subtitle: "Storage roots, archiving hierarchy, and local inference parameters",
  },
};

interface TopBarProps {
  activeTab: NavTab;
  sseConnected: boolean;
  onOpenCommandPalette: () => void;
  queue: SkillQueueState;
  queueDrawerOpen: boolean;
  onToggleQueueDrawer: () => void;
}

export function TopBar({
  activeTab,
  sseConnected,
  onOpenCommandPalette,
  queue,
  queueDrawerOpen,
  onToggleQueueDrawer,
}: TopBarProps) {
  const meta = TAB_META[activeTab];

  return (
    <header className="flex h-[52px] shrink-0 items-center justify-between gap-4 border-b border-border bg-surface/75 px-4 backdrop-blur-xs">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <h1 className="truncate text-sm font-semibold tracking-tight text-foreground">
            {meta.title}
          </h1>
          <span className="hidden text-xs text-muted-foreground lg:inline">
            · {meta.subtitle}
          </span>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Badge
          variant={sseConnected ? "success" : "warning"}
          className="hidden sm:inline-flex"
          title={
            sseConnected
              ? "Connected to real-time SSE stream"
              : "SSE reconnecting..."
          }
        >
          <Radio
            className={cn("h-3 w-3", sseConnected && "animate-pulse")}
          />
          {sseConnected ? "Live Stream" : "Syncing"}
        </Badge>

        {activeTab === "skills" && (
          <Button
            variant={queueDrawerOpen ? "default" : "outline"}
            size="sm"
            onClick={onToggleQueueDrawer}
            className="gap-1.5"
          >
            <ListTodo className="h-3.5 w-3.5" />
            <span>Skill Queue</span>
            <Badge
              variant={
                queue.is_running && !queue.is_paused
                  ? "success"
                  : queue.is_paused
                    ? "warning"
                    : "secondary"
              }
              className="ml-0.5 px-1.5 py-0 text-[10px]"
            >
              {queue.items.length}
            </Badge>
          </Button>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={onOpenCommandPalette}
          className="gap-2 text-muted-foreground"
        >
          <Search className="h-3.5 w-3.5" />
          <span className="hidden md:inline text-xs">Quick Jump</span>
          <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:inline">
            Ctrl+K
          </kbd>
        </Button>
      </div>
    </header>
  );
}
