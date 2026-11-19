import { useState } from "react";
import {
  Copy,
  FileCode2,
  Play,
  Plus,
  Rocket,
  Save,
  Sparkles,
  Trash2,
  Workflow,
} from "lucide-react";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { AiSynthesisDialog } from "@/components/skills/AiSynthesisDialog";
import { CreateSkillDialog } from "@/components/skills/CreateSkillDialog";
import { GdtSkillEditor } from "@/components/skills/GdtSkillEditor";
import { ImportSkillEditor } from "@/components/skills/ImportSkillEditor";
import { SkillCopilotChat } from "@/components/skills/SkillCopilotChat";
import { SkillFlowEditor } from "@/components/skills/SkillFlowEditor";
import { SkillGeneralSettings } from "@/components/skills/SkillGeneralSettings";
import { SkillQueuePanel } from "@/components/skills/SkillQueuePanel";
import { SkillSidebarList } from "@/components/skills/SkillSidebarList";
import { SkillYamlEditor } from "@/components/skills/SkillYamlEditor";
import { TestRunDialog } from "@/components/skills/TestRunDialog";
import {
  extractAllowedDocTypes,
  extractTasksFromSkill,
  useSkillEditor,
  type EditorViewMode,
} from "@/components/skills/useSkillEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppState } from "@/hooks/use-app-state";
import { cn } from "@/lib/utils";

export function SkillsView() {
  const { queue, queueDrawerOpen, setQueueDrawerOpen, refreshQueue } =
    useAppState();
  const editor = useSkillEditor();

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [testRunOpen, setTestRunOpen] = useState(false);

  return (
    <div className="grid h-full min-h-0 gap-4 lg:grid-cols-[248px_1fr]">
      <SkillSidebarList
        skills={editor.skills}
        selectedSkillId={editor.selectedSkillId}
        isNewCreation={editor.isNewCreation}
        onSelectSkill={(id) => {
          editor.setIsNewCreation(false);
          editor.setSelectedSkillId(id);
        }}
        onOpenCreate={() => setCreateDialogOpen(true)}
      />

      <div className="skill-studio-container flex min-w-0 flex-col gap-3 overflow-y-auto pr-0.5">
        {!editor.draftSkill ? (
          <EmptyState
            icon={Workflow}
            title="Select a skill or create a new pipeline"
            description="Build hybrid OCR/VLM import schemas, GUI RPA workflows, or GDT 2.1 medical exports."
            action={
              <Button size="sm" onClick={() => setCreateDialogOpen(true)}>
                <Plus className="h-3.5 w-3.5" />
                Create Skill
              </Button>
            }
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-4 py-2.5">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold text-foreground">
                  {editor.draftSkill.name || "Untitled Skill"}
                </h3>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Tabs
                  value={editor.viewMode}
                  onValueChange={(v) => {
                    const next = v as EditorViewMode;
                    editor.setViewMode(next);
                    if (next === "yaml") void editor.syncYamlFromVisual();
                  }}
                >
                  <TabsList>
                    {editor.draftSkill.type === "export" && (
                      <TabsTrigger value="copilot">
                        <Sparkles className="h-3 w-3" />
                        Copilot + Flow
                      </TabsTrigger>
                    )}
                    <TabsTrigger value="flow">
                      <Workflow className="h-3 w-3" />
                      Form
                    </TabsTrigger>
                    <TabsTrigger value="yaml">
                      <FileCode2 className="h-3 w-3" />
                      YAML
                    </TabsTrigger>
                  </TabsList>
                </Tabs>

                {editor.draftSkill.type === "export" && !editor.isNewCreation && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void editor.handleBatchRun()}
                    title="Queue all approved pending cases for this export skill"
                  >
                    <Rocket className="h-3.5 w-3.5 text-cyan-400" />
                    Run Batch
                    {editor.pendingCount > 0 && (
                      <Badge variant="info" className="px-1.5 py-0 text-[10px]">
                        {editor.pendingCount}
                      </Badge>
                    )}
                  </Button>
                )}

                {editor.draftSkill.type === "export" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setTestRunOpen(true)}
                  >
                    <Play className="h-3.5 w-3.5 text-emerald-400" />
                    Test Run
                  </Button>
                )}

                {!editor.isNewCreation && (
                  <>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => void editor.handleDuplicate()}
                      title="Duplicate skill"
                      aria-label="Duplicate skill"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        editor.setDeleteSkillTarget(editor.draftSkill?.id || null)
                      }
                      title="Delete skill"
                      aria-label="Delete skill"
                      className="text-rose-400 hover:bg-rose-500/12"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </>
                )}

                <Button
                  size="sm"
                  disabled={editor.saving}
                  onClick={() => void editor.handleSave()}
                >
                  <Save className="h-3.5 w-3.5" />
                  {editor.saving ? "Saving..." : "Save Skill"}
                </Button>
              </div>
            </div>

            {editor.viewMode === "yaml" ? (
              <SkillYamlEditor
                yamlText={editor.yamlText}
                loading={editor.yamlBusy}
                onChangeYaml={editor.setYamlText}
                onReloadFromVisual={() => void editor.syncYamlFromVisual()}
                onApplyAndSave={() => void editor.handleApplyYamlAndSave()}
              />
            ) : (
              <div
                className={cn(
                  "skill-studio-split grid gap-3",
                  editor.draftSkill.type === "export" &&
                    editor.viewMode === "copilot"
                    ? "grid-cols-1 xl:grid-cols-[360px_1fr]"
                    : "grid-cols-1",
                )}
              >
                {editor.draftSkill.type === "export" &&
                  editor.viewMode === "copilot" && (
                    <SkillCopilotChat
                      skillId={editor.draftSkill.id}
                      currentPayload={editor.buildPayload() || editor.draftSkill}
                      onSkillUpdated={(updated) => {
                        editor.setDraftSkill((prev) => ({
                          ...(prev || {}),
                          ...updated,
                        }));
                        editor.setDraftTasks(extractTasksFromSkill(updated));
                        if (updated.document_types !== undefined) {
                          editor.setDraftAllowedDocTypes(
                            extractAllowedDocTypes(updated),
                          );
                        }
                      }}
                    />
                  )}

                <div className="flex min-w-0 flex-col gap-3">
                  <SkillGeneralSettings
                    skill={editor.draftSkill}
                    allSkills={editor.skills}
                    availableDocTypes={editor.knownDocTypeNames}
                    selectedDocTypes={editor.draftAllowedDocTypes}
                    onChangeSkill={(patch) =>
                      editor.setDraftSkill((prev) =>
                        prev ? { ...prev, ...patch } : prev,
                      )
                    }
                    onChangeDocTypes={editor.setDraftAllowedDocTypes}
                  />

                  {editor.draftSkill.type === "import" ? (
                    <ImportSkillEditor
                      skill={editor.draftSkill}
                      docTypes={editor.draftImportDocTypes}
                      onChangeSkill={(patch) =>
                        editor.setDraftSkill((prev) =>
                          prev ? { ...prev, ...patch } : prev,
                        )
                      }
                      onChangeDocTypes={editor.setDraftImportDocTypes}
                    />
                  ) : editor.draftSkill.type === "gdt" ||
                    editor.draftSkill.type === "gdt_export" ? (
                    <GdtSkillEditor
                      skill={editor.draftSkill}
                      onChangeSkill={(patch) =>
                        editor.setDraftSkill((prev) =>
                          prev ? { ...prev, ...patch } : prev,
                        )
                      }
                    />
                  ) : (
                    <SkillFlowEditor
                      tasks={editor.draftTasks}
                      availableVars={editor.availableVars}
                      onChangeTasks={editor.setDraftTasks}
                      onStartRecording={() => void editor.handleStartRecording()}
                      onPickElement={(tIdx, aIdx) =>
                        void editor.handlePickElement(tIdx, aIdx)
                      }
                    />
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <SkillQueuePanel
        open={queueDrawerOpen}
        onOpenChange={setQueueDrawerOpen}
        queue={queue}
        skills={editor.skills}
        onRefreshQueue={refreshQueue}
      />

      <CreateSkillDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreate={editor.handleCreateSkill}
      />

      <TestRunDialog
        open={testRunOpen}
        onOpenChange={setTestRunOpen}
        skillPayload={editor.buildPayload()}
      />

      <AiSynthesisDialog
        open={editor.synthesisModalOpen}
        onOpenChange={editor.setSynthesisModalOpen}
        recordedSteps={editor.recordedSteps}
        knownDocTypes={editor.knownDocTypeNames}
        defaultSkillName={editor.draftSkill?.name || "New Skill"}
        onApply={editor.handleApplySynthesis}
      />

      <ConfirmDialog
        open={editor.deleteSkillTarget !== null}
        onOpenChange={(open) => !open && editor.setDeleteSkillTarget(null)}
        title="Delete skill configuration?"
        description="Permanently deletes this skill YAML file from disk."
        targetName={editor.deleteSkillTarget || undefined}
        confirmLabel="Delete Skill"
        busy={editor.deleting}
        onConfirm={editor.handleDelete}
      />
    </div>
  );
}
