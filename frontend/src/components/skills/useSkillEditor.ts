import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  buildNewSkillTemplate,
  extractAllowedDocTypes,
  extractTasksFromSkill,
} from "@/components/skills/skillTemplates";
import { useAppState } from "@/hooks/use-app-state";
import { skillsApi } from "@/lib/api-client";
import {
  getAvailableSkillVariables,
  getEffectiveDocTypes,
  stripInternalActionFlags,
} from "@/lib/utils";
import type {
  DocumentTypeConfig,
  SkillAction,
  SkillDefinition,
  SkillKind,
  SkillSynthesis,
  SkillTask,
} from "@/types/api";

const FORBIDDEN_NAME_CHARS = /[\\/:*?"<>|]/;

export type EditorViewMode = "flow" | "copilot" | "yaml";
export { extractAllowedDocTypes, extractTasksFromSkill };

export function useSkillEditor() {
  const {
    skills,
    config,
    selectedSkillId,
    setSelectedSkillId,
    setQueueDrawerOpen,
    setRecorderStatus,
    refreshSkills,
    refreshQueue,
    refreshConfig,
  } = useAppState();

  const [viewMode, setViewMode] = useState<EditorViewMode>("copilot");
  const [draftSkill, setDraftSkill] = useState<SkillDefinition | null>(null);
  const [draftTasks, setDraftTasks] = useState<SkillTask[]>([]);
  const [draftAllowedDocTypes, setDraftAllowedDocTypes] = useState<string[]>([]);
  const [draftImportDocTypes, setDraftImportDocTypes] = useState<
    Record<string, DocumentTypeConfig>
  >({});
  const [originalName, setOriginalName] = useState<string | null>(null);
  const [isNewCreation, setIsNewCreation] = useState(false);

  const [yamlText, setYamlText] = useState("");
  const [yamlBusy, setYamlBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  const [deleteSkillTarget, setDeleteSkillTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [synthesisModalOpen, setSynthesisModalOpen] = useState(false);
  const [recordedSteps, setRecordedSteps] = useState<SkillAction[]>([]);

  const effectiveDocTypesMap = useMemo(
    () => getEffectiveDocTypes(skills, config),
    [skills, config],
  );
  const knownDocTypeNames = useMemo(
    () => Object.keys(effectiveDocTypesMap).sort(),
    [effectiveDocTypesMap],
  );
  const availableVars = useMemo(
    () => getAvailableSkillVariables(skills, config, draftAllowedDocTypes),
    [skills, config, draftAllowedDocTypes],
  );

  useEffect(() => {
    if (skills.length === 0 || isNewCreation) return;
    if (selectedSkillId && skills.some((s) => s.id === selectedSkillId)) return;
    const first = skills[0];
    if (first) setSelectedSkillId(first.id);
  }, [skills, selectedSkillId, isNewCreation, setSelectedSkillId]);

  useEffect(() => {
    if (isNewCreation || !selectedSkillId) return;
    const found = skills.find((s) => s.id === selectedSkillId);
    if (!found) return;

    setDraftSkill(JSON.parse(JSON.stringify(found)) as SkillDefinition);
    setDraftTasks(extractTasksFromSkill(found));
    setDraftAllowedDocTypes(extractAllowedDocTypes(found));
    setOriginalName(found.name || found.id);
    setViewMode((prev) => (prev === "yaml" ? "copilot" : prev));

    if (found.type === "import") {
      skillsApi
        .getDocTypes(found.id)
        .then((res) => setDraftImportDocTypes(res.document_types || {}))
        .catch(() => {
          if (
            found.document_types &&
            !Array.isArray(found.document_types) &&
            typeof found.document_types === "object"
          ) {
            setDraftImportDocTypes(
              found.document_types as Record<string, DocumentTypeConfig>,
            );
          } else {
            setDraftImportDocTypes({});
          }
        });
    } else if (found.type === "export") {
      skillsApi
        .getPendingCases(found.id)
        .then((res) => setPendingCount(res.count || 0))
        .catch(() => setPendingCount(0));
    } else {
      setPendingCount(0);
    }
  }, [selectedSkillId, skills, isNewCreation]);

  const buildPayload = useCallback((): SkillDefinition | null => {
    if (!draftSkill) return null;
    const name = (draftSkill.name || "").trim() || "Untitled Skill";
    const cleanedTasks = stripInternalActionFlags(draftTasks);
    const flatSteps = cleanedTasks.flatMap((t) => t.actions || []);

    const payload: SkillDefinition = {
      ...draftSkill,
      id: name,
      name,
      enabled: draftSkill.enabled !== false,
    };

    if (originalName && originalName !== name && !isNewCreation) {
      payload.original_name = originalName;
    } else {
      delete payload.original_name;
    }

    if (draftSkill.type === "import") {
      payload.document_types = draftImportDocTypes;
    } else if (draftSkill.type === "export") {
      const explicitWin = (draftSkill.target_window || "").trim();
      const firstFocusWin =
        flatSteps
          .find((s) => s.action_type === "FOCUS_WINDOW")
          ?.window_title?.trim() || "";
      payload.target_window = explicitWin || firstFocusWin || "Remote Desktop*";
      payload.rdp_path_prefix =
        (draftSkill.rdp_path_prefix || "").trim() || "\\\\tsclient\\C";
      payload.document_types = draftAllowedDocTypes;
      payload.tasks = cleanedTasks;
      payload.steps = flatSteps;
    }

    return payload;
  }, [
    draftSkill,
    draftTasks,
    draftAllowedDocTypes,
    draftImportDocTypes,
    originalName,
    isNewCreation,
  ]);

  const syncYamlFromVisual = useCallback(async () => {
    const payload = buildPayload();
    if (!payload) return;
    setYamlBusy(true);
    try {
      const res = await skillsApi.toYaml(payload);
      if (res.yaml) setYamlText(res.yaml);
    } catch (e) {
      toast.error(
        `Failed to generate YAML: ${e instanceof Error ? e.message : "Error"}`,
      );
    } finally {
      setYamlBusy(false);
    }
  }, [buildPayload]);

  const handleSave = async () => {
    const payload = buildPayload();
    if (!payload) return;
    if (FORBIDDEN_NAME_CHARS.test(payload.name)) {
      toast.error('Skill name cannot contain :, /, \\, *, ?, ", <, >, |');
      return;
    }

    setSaving(true);
    try {
      const res = await skillsApi.save(payload);
      const finalName = res.name || res.skill_id || payload.name;
      if (payload.type === "import") {
        await skillsApi.saveDocTypes(finalName, draftImportDocTypes);
        await refreshConfig();
      }
      toast.success(`Skill '${finalName}' saved`);
      setIsNewCreation(false);
      setOriginalName(finalName);
      setSelectedSkillId(finalName);
      await refreshSkills();
    } catch (e) {
      toast.error(`Save failed: ${e instanceof Error ? e.message : "Error"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleApplyYamlAndSave = async () => {
    if (!yamlText.trim()) {
      toast.error("YAML content cannot be empty");
      return;
    }
    setYamlBusy(true);
    try {
      const parsedRes = await skillsApi.fromYaml(yamlText);
      const parsed = parsedRes.skill;
      const savedRes = await skillsApi.save(parsed);
      const finalId = savedRes.skill_id || parsed.id || parsed.name;
      setIsNewCreation(false);
      setSelectedSkillId(finalId);
      await refreshSkills();
      setViewMode("copilot");
      toast.success(`Saved YAML for '${parsed.name || finalId}'`);
    } catch (e) {
      toast.error(
        `YAML error: ${e instanceof Error ? e.message : "Invalid YAML"}`,
      );
    } finally {
      setYamlBusy(false);
    }
  };

  const handleCreateSkill = (kind: SkillKind, copyDefaults: boolean) => {
    const tpl = buildNewSkillTemplate(
      kind,
      copyDefaults,
      skills,
      effectiveDocTypesMap,
    );
    setDraftImportDocTypes(tpl.importDocTypes);
    setDraftTasks(tpl.tasks);
    setDraftAllowedDocTypes([]);
    setIsNewCreation(true);
    setOriginalName(null);
    setSelectedSkillId(tpl.skill.name);
    setDraftSkill(tpl.skill);
    setViewMode("copilot");
  };

  const handleDuplicate = async () => {
    const id = draftSkill?.id || selectedSkillId;
    if (!id) return;
    try {
      const res = await skillsApi.duplicate(id);
      const nextId = res.skill?.name || res.skill?.id || id;
      toast.success(`Duplicated skill: ${nextId}`);
      setIsNewCreation(false);
      setSelectedSkillId(nextId);
      await refreshSkills();
    } catch (e) {
      toast.error(
        `Duplicate failed: ${e instanceof Error ? e.message : "Error"}`,
      );
    }
  };

  const handleDelete = async () => {
    if (!deleteSkillTarget) return;
    setDeleting(true);
    try {
      await skillsApi.deleteSkill(deleteSkillTarget);
      toast.success(`Deleted skill '${deleteSkillTarget}'`);
      setDeleteSkillTarget(null);
      setDraftSkill(null);
      setSelectedSkillId(null);
      setIsNewCreation(false);
      await refreshSkills();
    } catch (e) {
      toast.error(`Delete failed: ${e instanceof Error ? e.message : "Error"}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleBatchRun = async () => {
    if (!draftSkill?.id) return;
    try {
      const res = await skillsApi.runBatch(draftSkill.id);
      if (res.queued_count > 0) {
        toast.success(`Queued ${res.queued_count} pending case(s) for execution`);
        await refreshQueue();
        setQueueDrawerOpen(true);
      } else {
        toast.info("No pending approved cases matched this export skill");
      }
    } catch (e) {
      toast.error(
        `Batch run failed: ${e instanceof Error ? e.message : "Error"}`,
      );
    }
  };

  const handleStartRecording = async () => {
    try {
      await skillsApi.startRecorder(draftSkill?.name || "New Recorded Skill");
      setRecorderStatus({
        is_recording: true,
        step_count: 0,
        elapsed_seconds: 0,
        last_action: "Demonstrate actions on your desktop...",
      });
      toast.success("Live recording started");
    } catch (e) {
      toast.error(
        `Recorder failed: ${e instanceof Error ? e.message : "Error"}`,
      );
    }
  };

  useEffect(() => {
    const onStopEvent = () => {
      skillsApi
        .stopRecorder()
        .then((res) => {
          setRecorderStatus({ is_recording: false });
          const steps = res.skill?.steps || [];
          if (steps.length > 0) {
            setRecordedSteps(steps);
            setSynthesisModalOpen(true);
          } else {
            toast.info("Recording stopped (no actions captured)");
          }
        })
        .catch((e) => {
          setRecorderStatus({ is_recording: false });
          toast.error(
            `Stop recording error: ${e instanceof Error ? e.message : "Error"}`,
          );
        });
    };
    window.addEventListener("ordinflow:stop-recording", onStopEvent);
    return () =>
      window.removeEventListener("ordinflow:stop-recording", onStopEvent);
  }, [setRecorderStatus]);

  const handlePickElement = async (taskIdx: number, actIdx: number) => {
    toast.info("Move cursor over target element (capturing in 1s)...");
    try {
      const res = await skillsApi.pickElement(
        draftSkill?.target_window || "",
        1.0,
      );
      setDraftTasks((prev) =>
        prev.map((t, tI) => {
          if (tI !== taskIdx) return t;
          return {
            ...t,
            actions: (t.actions || []).map((a, aI) =>
              aI === actIdx
                ? {
                    ...a,
                    locator: {
                      ...(a.locator || {}),
                      type: res.locator.type,
                      prompt: res.locator.prompt,
                      offset: res.locator.offset || [0, 0],
                    },
                  }
                : a,
            ),
          };
        }),
      );
      toast.success(`Picked element: "${res.locator.prompt}"`);
    } catch (e) {
      toast.error(
        `Element pick failed: ${e instanceof Error ? e.message : "Error"}`,
      );
    }
  };

  const handleApplySynthesis = (
    syn: SkillSynthesis,
    name: string,
    docType: string,
  ) => {
    setIsNewCreation(true);
    setDraftSkill((prev) => ({
      ...(prev || { id: name, name, type: "export" }),
      id: name,
      name,
      type: "export",
      description: syn.description || prev?.description || "",
    }));
    setDraftAllowedDocTypes(docType && docType !== "*" ? [docType] : []);
    if (Array.isArray(syn.tasks) && syn.tasks.length > 0) {
      setDraftTasks(syn.tasks);
    }
    toast.success(`Loaded synthesized skill '${name}' into editor`);
  };

  return {
    skills,
    selectedSkillId,
    setSelectedSkillId,
    viewMode,
    setViewMode,
    draftSkill,
    setDraftSkill,
    draftTasks,
    setDraftTasks,
    draftAllowedDocTypes,
    setDraftAllowedDocTypes,
    draftImportDocTypes,
    setDraftImportDocTypes,
    isNewCreation,
    setIsNewCreation,
    yamlText,
    setYamlText,
    yamlBusy,
    saving,
    pendingCount,
    deleteSkillTarget,
    setDeleteSkillTarget,
    deleting,
    synthesisModalOpen,
    setSynthesisModalOpen,
    recordedSteps,
    knownDocTypeNames,
    availableVars,
    buildPayload,
    syncYamlFromVisual,
    handleSave,
    handleApplyYamlAndSave,
    handleCreateSkill,
    handleDuplicate,
    handleDelete,
    handleBatchRun,
    handleStartRecording,
    handlePickElement,
    handleApplySynthesis,
  };
}
