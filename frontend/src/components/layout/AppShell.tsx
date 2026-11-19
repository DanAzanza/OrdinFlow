import { useState, type ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { LegalModal } from "@/components/common/LegalModal";
import { useAppState } from "@/hooks/use-app-state";
import type { ThemeMode } from "@/hooks/use-theme";
import type { LegalDocName } from "@/types/api";

interface AppShellProps {
  theme: ThemeMode;
  onToggleTheme: () => void;
  commandPaletteOpen: boolean;
  onCommandPaletteOpenChange: (open: boolean) => void;
  onJumpToCase: (folder: string) => void;
  inspector: ReactNode;
  floatingOverlay?: ReactNode;
  children: ReactNode;
}

export function AppShell({
  theme,
  onToggleTheme,
  commandPaletteOpen,
  onCommandPaletteOpenChange,
  onJumpToCase,
  inspector,
  floatingOverlay,
  children,
}: AppShellProps) {
  const {
    activeTab,
    setActiveTab,
    inbox,
    cases,
    skills,
    queue,
    status,
    sseConnected,
    queueDrawerOpen,
    setQueueDrawerOpen,
    setSelectedSkillId,
    toggleEnginePause,
  } = useAppState();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [legalDoc, setLegalDoc] = useState<LegalDocName | null>(null);

  const reviewInboxCount = inbox.filter((item) =>
    Boolean(item.is_review ?? item.is_pruefen),
  ).length;
  const unprocessedInboxCount = inbox.filter(
    (item) => !item.is_processed && !item.is_abgearbeitet,
  ).length;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        unprocessedInboxCount={unprocessedInboxCount}
        reviewInboxCount={reviewInboxCount}
        casesCount={cases.length}
        queue={queue}
        enginePaused={Boolean(status?.paused)}
        onToggleEnginePause={() => void toggleEnginePause()}
        theme={theme}
        onToggleTheme={onToggleTheme}
        onOpenLegal={setLegalDoc}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar
          activeTab={activeTab}
          sseConnected={sseConnected}
          onOpenCommandPalette={() => onCommandPaletteOpenChange(true)}
          queue={queue}
          queueDrawerOpen={queueDrawerOpen}
          onToggleQueueDrawer={() => setQueueDrawerOpen((o) => !o)}
        />

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <main className="skill-studio-container flex min-w-0 flex-1 flex-col overflow-y-auto p-4 lg:p-5">
            {children}
          </main>

          {inspector}
        </div>
      </div>

      {floatingOverlay}

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={onCommandPaletteOpenChange}
        onNavigateTab={setActiveTab}
        cases={cases}
        skills={skills}
        onSelectCase={onJumpToCase}
        onSelectSkill={(skillId) => {
          setSelectedSkillId(skillId);
          setActiveTab("skills");
        }}
        enginePaused={Boolean(status?.paused)}
        onToggleEnginePause={() => void toggleEnginePause()}
        theme={theme}
        onToggleTheme={onToggleTheme}
        onOpenLegal={setLegalDoc}
      />

      <LegalModal docName={legalDoc} onClose={() => setLegalDoc(null)} />
    </div>
  );
}
