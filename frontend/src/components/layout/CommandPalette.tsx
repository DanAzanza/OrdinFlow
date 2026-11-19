import { Command } from "cmdk";
import {
  Activity,
  FolderKanban,
  Inbox,
  Moon,
  Pause,
  Play,
  Scale,
  Search,
  Settings,
  Sun,
  Workflow,
} from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import type { ThemeMode } from "@/hooks/use-theme";
import type {
  CaseSummary,
  LegalDocName,
  NavTab,
  SkillDefinition,
} from "@/types/api";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigateTab: (tab: NavTab) => void;
  cases: CaseSummary[];
  skills: SkillDefinition[];
  onSelectCase: (folder: string) => void;
  onSelectSkill: (skillId: string) => void;
  enginePaused: boolean;
  onToggleEnginePause: () => void;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onOpenLegal: (doc: LegalDocName) => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  onNavigateTab,
  cases,
  skills,
  onSelectCase,
  onSelectSkill,
  enginePaused,
  onToggleEnginePause,
  theme,
  onToggleTheme,
  onOpenLegal,
}: CommandPaletteProps) {
  const runAndClose = (fn: () => void) => {
    onOpenChange(false);
    fn();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl overflow-hidden p-0" hideCloseButton>
        <DialogTitle className="sr-only">Command Palette</DialogTitle>
        <Command className="flex flex-col bg-popover text-popover-foreground">
          <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
            <Command.Input
              autoFocus
              placeholder="Jump to view, case folder, skill, or system action..."
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              Esc
            </kbd>
          </div>

          <Command.List className="max-h-[360px] overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-xs text-muted-foreground">
              No matching commands, skills, or cases found.
            </Command.Empty>

            <Command.Group
              heading="Navigation"
              className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground"
            >
              {(
                [
                  { id: "inbox", label: "Go to Inbox", icon: Inbox },
                  { id: "cases", label: "Go to Cases Explorer", icon: FolderKanban },
                  { id: "skills", label: "Go to Skills Studio", icon: Workflow },
                  { id: "logs", label: "Go to Pipeline & Logs", icon: Activity },
                  { id: "settings", label: "Go to System Settings", icon: Settings },
                ] as const
              ).map((nav) => {
                const Icon = nav.icon;
                return (
                  <Command.Item
                    key={nav.id}
                    value={nav.label}
                    onSelect={() => runAndClose(() => onNavigateTab(nav.id))}
                    className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-foreground aria-selected:bg-accent"
                  >
                    <Icon className="h-3.5 w-3.5 text-primary" />
                    <span>{nav.label}</span>
                  </Command.Item>
                );
              })}
            </Command.Group>

            <Command.Group
              heading="System Actions"
              className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground"
            >
              <Command.Item
                value="Toggle processing engine pause resume"
                onSelect={() => runAndClose(onToggleEnginePause)}
                className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-foreground aria-selected:bg-accent"
              >
                {enginePaused ? (
                  <Play className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Pause className="h-3.5 w-3.5 text-amber-400" />
                )}
                <span>
                  {enginePaused ? "Resume Processing Engine" : "Pause Processing Engine"}
                </span>
              </Command.Item>

              <Command.Item
                value="Toggle dark light theme mode"
                onSelect={() => runAndClose(onToggleTheme)}
                className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-foreground aria-selected:bg-accent"
              >
                {theme === "dark" ? (
                  <Sun className="h-3.5 w-3.5 text-amber-300" />
                ) : (
                  <Moon className="h-3.5 w-3.5 text-indigo-500" />
                )}
                <span>
                  {theme === "dark" ? "Switch to Light Theme" : "Switch to Dark Theme"}
                </span>
              </Command.Item>

              <Command.Item
                value="Open compliance privacy license legal"
                onSelect={() => runAndClose(() => onOpenLegal("privacy"))}
                className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-foreground aria-selected:bg-accent"
              >
                <Scale className="h-3.5 w-3.5 text-cyan-400" />
                <span>View Privacy Policy & Compliance</span>
              </Command.Item>
            </Command.Group>

            {skills.length > 0 && (
              <Command.Group
                heading="Skills"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {skills.slice(0, 12).map((s) => (
                  <Command.Item
                    key={s.id}
                    value={`skill ${s.name} ${s.id} ${s.type}`}
                    onSelect={() => runAndClose(() => onSelectSkill(s.id))}
                    className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-xs text-foreground aria-selected:bg-accent"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <Workflow className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                      <span className="truncate">{s.name || s.id}</span>
                    </div>
                    <span className="shrink-0 font-mono text-[10px] uppercase text-muted-foreground">
                      {s.type}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {cases.length > 0 && (
              <Command.Group
                heading="Cases"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {cases.slice(0, 12).map((c) => (
                  <Command.Item
                    key={c.folder}
                    value={`case ${c.folder} ${c.person} ${c.produkt}`}
                    onSelect={() => runAndClose(() => onSelectCase(c.folder))}
                    className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-xs text-foreground aria-selected:bg-accent"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <FolderKanban className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                      <span className="truncate">{c.display_title || c.folder}</span>
                    </div>
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                      {c.file_count} files
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
