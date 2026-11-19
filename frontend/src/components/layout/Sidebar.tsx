import {
  Activity,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  Inbox,
  Moon,
  Pause,
  Play,
  Scale,
  Settings,
  Sun,
  Workflow,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { getAppVersion } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { ThemeMode } from "@/hooks/use-theme";
import type { LegalDocName, NavTab, SkillQueueState } from "@/types/api";

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  unprocessedInboxCount: number;
  reviewInboxCount: number;
  casesCount: number;
  queue: SkillQueueState;
  enginePaused: boolean;
  onToggleEnginePause: () => void;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onOpenLegal: (doc: LegalDocName) => void;
}

const NAV_ITEMS: Array<{
  id: NavTab;
  label: string;
  icon: typeof Inbox;
}> = [
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "cases", label: "Cases", icon: FolderKanban },
  { id: "skills", label: "Skills Studio", icon: Workflow },
  { id: "logs", label: "Pipeline & Logs", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
];

function OrdinFlowLogo() {
  return (
    <svg
      viewBox="0 0 28 28"
      className="h-7 w-7 shrink-0"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="ofGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <rect width="28" height="28" rx="7" fill="url(#ofGrad)" />
      <path
        d="M8.5 9.5h11M8.5 14h7.5M8.5 18.5h11"
        stroke="#ffffff"
        strokeWidth="2.1"
        strokeLinecap="round"
      />
      <circle cx="19.5" cy="14" r="2.1" fill="#ffffff" />
    </svg>
  );
}

export function Sidebar({
  activeTab,
  onSelectTab,
  collapsed,
  onToggleCollapse,
  unprocessedInboxCount,
  reviewInboxCount,
  casesCount,
  queue,
  enginePaused,
  onToggleEnginePause,
  theme,
  onToggleTheme,
  onOpenLegal,
}: SidebarProps) {
  const version = getAppVersion();

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200",
        collapsed ? "w-16" : "w-[228px]",
      )}
    >
      {/* Brand header */}
      <div className="flex h-[52px] items-center justify-between border-b border-border px-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <OrdinFlowLogo />
          {!collapsed && (
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-sm font-bold tracking-tight text-foreground">
                OrdinFlow
              </span>
              <span className="rounded bg-primary/15 px-1.5 py-0.5 font-mono text-[10px] font-medium text-indigo-600 dark:text-indigo-300">
                v{version}
              </span>
            </div>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          title={collapsed ? "Expand navigation" : "Collapse navigation"}
          className="h-7 w-7 shrink-0 text-muted-foreground"
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Navigation items */}
      <nav className="flex flex-1 flex-col gap-1 p-2" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          const button = (
            <button
              key={item.id}
              type="button"
              data-tab={item.id}
              onClick={() => onSelectTab(item.id)}
              className={cn(
                "group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium transition-colors cursor-pointer",
                isActive
                  ? "bg-primary/14 text-foreground ring-1 ring-primary/30"
                  : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                collapsed && "justify-center px-0",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                )}
              />
              {!collapsed && (
                <>
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.id === "inbox" && (
                    <div className="flex items-center gap-1">
                      <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                        {unprocessedInboxCount}
                      </Badge>
                      {reviewInboxCount > 0 && (
                        <Badge variant="warning" className="px-1.5 py-0 text-[10px]">
                          {reviewInboxCount}
                        </Badge>
                      )}
                    </div>
                  )}
                  {item.id === "cases" && (
                    <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                      {casesCount}
                    </Badge>
                  )}
                  {item.id === "skills" && (queue.is_running || queue.is_paused) && (
                    <Badge
                      variant={queue.is_paused ? "warning" : "success"}
                      className="px-1.5 py-0 text-[10px]"
                    >
                      {queue.is_paused ? "Paused" : "Run"}
                    </Badge>
                  )}
                </>
              )}
            </button>
          );

          if (collapsed) {
            return (
              <Tooltip key={item.id}>
                <TooltipTrigger asChild>{button}</TooltipTrigger>
                <TooltipContent side="right">{item.label}</TooltipContent>
              </Tooltip>
            );
          }

          return button;
        })}
      </nav>

      {/* Engine state + Theme + Legal */}
      <div className="flex flex-col gap-2 border-t border-border p-2.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onToggleEnginePause}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-xs font-medium transition-colors cursor-pointer",
                enginePaused
                  ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/18"
                  : "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/16",
                collapsed && "justify-center px-0",
              )}
            >
              <span
                className={cn(
                  "h-2 w-2 shrink-0 rounded-full",
                  enginePaused ? "bg-amber-400" : "bg-emerald-400 animate-pulse",
                )}
              />
              {!collapsed && (
                <>
                  <span className="flex-1 truncate text-left">
                    {enginePaused ? "Engine Paused" : "Engine Active"}
                  </span>
                  {enginePaused ? (
                    <Play className="h-3.5 w-3.5 shrink-0" />
                  ) : (
                    <Pause className="h-3.5 w-3.5 shrink-0" />
                  )}
                </>
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {enginePaused ? "Resume processing engine" : "Pause processing engine"}
          </TooltipContent>
        </Tooltip>

        <div
          className={cn(
            "flex items-center gap-1.5",
            collapsed ? "flex-col" : "justify-between",
          )}
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            className={cn("text-xs text-muted-foreground", collapsed ? "w-9 px-0" : "flex-1 justify-start")}
          >
            {theme === "dark" ? (
              <Sun className="h-3.5 w-3.5" />
            ) : (
              <Moon className="h-3.5 w-3.5" />
            )}
            {!collapsed && (
              <span>{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>
            )}
          </Button>

          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Legal & Compliance"
                title="Legal & Compliance"
                className="h-8 w-8 text-muted-foreground"
              >
                <Scale className="h-3.5 w-3.5" />
              </Button>
            </PopoverTrigger>
            <PopoverContent side="right" align="end" className="w-52 p-1.5">
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Compliance & Legal
              </div>
              {(
                [
                  { id: "privacy", label: "Privacy Policy" },
                  { id: "license", label: "License (AGPL v3)" },
                  { id: "thirdparty", label: "Third-Party Licenses" },
                  { id: "checklist", label: "Compliance Checklist" },
                ] as Array<{ id: LegalDocName; label: string }>
              ).map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => onOpenLegal(doc.id)}
                  className="flex w-full items-center rounded-md px-2 py-1.5 text-left text-xs text-foreground transition-colors hover:bg-accent cursor-pointer"
                >
                  {doc.label}
                </button>
              ))}
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </aside>
  );
}
