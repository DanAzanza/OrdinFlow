import { useRef, useState } from "react";
import { Toaster } from "sonner";
import { CasesView } from "@/components/cases/CasesView";
import { InboxView } from "@/components/inbox/InboxView";
import { DocumentInspector } from "@/components/inspector/DocumentInspector";
import { AppShell } from "@/components/layout/AppShell";
import { LogsView } from "@/components/logs/LogsView";
import { SettingsView } from "@/components/settings/SettingsView";
import { LiveRecorderBar } from "@/components/skills/LiveRecorderBar";
import { SkillsView } from "@/components/skills/SkillsView";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppStateProvider, useAppState } from "@/hooks/use-app-state";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { useTheme } from "@/hooks/use-theme";
import type { InboxItem } from "@/types/api";

function DashboardRoot() {
  const {
    activeTab,
    setActiveTab,
    inspectorState,
    setInspectorState,
    recorderStatus,
    setReviewOnly,
  } = useAppState();
  const { theme, toggleTheme } = useTheme();

  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [selectedInboxIdx, setSelectedInboxIdx] = useState(-1);
  const [inboxDeleteTarget, setInboxDeleteTarget] = useState<InboxItem | null>(
    null,
  );
  const [expandedCaseFolder, setExpandedCaseFolder] = useState<string | null>(
    null,
  );

  const inspectorActionsRef = useRef<{
    submit: () => void;
    requestDelete: () => void;
  } | null>(null);
  const inboxShortcutsRef = useRef<{
    moveSelection: (delta: 1 | -1) => void;
    openSelected: () => void;
    deleteSelected: () => void;
  } | null>(null);

  useKeyboardShortcuts({
    commandPaletteOpen,
    onToggleCommandPalette: () => setCommandPaletteOpen((o) => !o),
    inspectorOpen: inspectorState !== null,
    onSubmitInspector: () => inspectorActionsRef.current?.submit(),
    onCloseInspector: () => setInspectorState(null),
    onDeleteInspector: () => inspectorActionsRef.current?.requestDelete(),
    onInboxArrow: (delta) => inboxShortcutsRef.current?.moveSelection(delta),
    onInboxOpenSelected: () => inboxShortcutsRef.current?.openSelected(),
    onInboxDeleteSelected: () => inboxShortcutsRef.current?.deleteSelected(),
    onInboxToggleReviewFilter: () => setReviewOnly((r) => !r),
    activeTab,
  });

  const inspectorNode =
    inspectorState && (activeTab === "inbox" || activeTab === "cases") ? (
      <DocumentInspector
        inspectorState={inspectorState}
        onClose={() => setInspectorState(null)}
        registerActions={(actions) => {
          inspectorActionsRef.current = actions;
        }}
      />
    ) : null;

  return (
    <AppShell
      theme={theme}
      onToggleTheme={toggleTheme}
      commandPaletteOpen={commandPaletteOpen}
      onCommandPaletteOpenChange={setCommandPaletteOpen}
      onJumpToCase={(folder) => {
        setExpandedCaseFolder(folder);
        setActiveTab("cases");
      }}
      inspector={inspectorNode}
      floatingOverlay={
        <LiveRecorderBar
          status={recorderStatus}
          onStop={() =>
            window.dispatchEvent(new CustomEvent("ordinflow:stop-recording"))
          }
        />
      }
    >
      {activeTab === "inbox" && (
        <InboxView
          selectedIndex={selectedInboxIdx}
          onSelectIndex={setSelectedInboxIdx}
          deleteTarget={inboxDeleteTarget}
          onDeleteTargetChange={setInboxDeleteTarget}
          registerShortcuts={(handlers) => {
            inboxShortcutsRef.current = handlers;
          }}
        />
      )}
      {activeTab === "cases" && (
        <CasesView
          expandedFolder={expandedCaseFolder}
          onExpandedFolderChange={setExpandedCaseFolder}
        />
      )}
      {activeTab === "skills" && <SkillsView />}
      {activeTab === "logs" && <LogsView />}
      {activeTab === "settings" && <SettingsView />}

      <Toaster theme={theme} position="bottom-right" richColors closeButton />
    </AppShell>
  );
}

export function App() {
  return (
    <TooltipProvider delayDuration={250}>
      <AppStateProvider>
        <DashboardRoot />
      </AppStateProvider>
    </TooltipProvider>
  );
}
export default App;
