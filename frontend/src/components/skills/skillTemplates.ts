import { slugifySkillName } from "@/lib/utils";
import type {
  DocumentTypeConfig,
  SkillAction,
  SkillDefinition,
  SkillKind,
  SkillTask,
} from "@/types/api";

export function extractTasksFromSkill(skill: SkillDefinition): SkillTask[] {
  if (Array.isArray(skill.tasks) && skill.tasks.length > 0) {
    return JSON.parse(JSON.stringify(skill.tasks)) as SkillTask[];
  }
  if (Array.isArray(skill.steps) && skill.steps.length > 0) {
    return [
      {
        id: "task_1",
        title: "Execute Action Sequence",
        actions: JSON.parse(JSON.stringify(skill.steps)) as SkillAction[],
      },
    ];
  }
  return [];
}

export function extractAllowedDocTypes(skill: SkillDefinition): string[] {
  if (Array.isArray(skill.document_types)) {
    return skill.document_types.filter((t) => Boolean(t) && t !== "*");
  }
  if (typeof skill.document_types === "string" && skill.document_types.trim()) {
    return skill.document_types
      .split(",")
      .map((s) => s.trim())
      .filter((s) => Boolean(s) && s !== "*");
  }
  return [];
}

export function buildNewSkillTemplate(
  kind: SkillKind,
  copyDefaults: boolean,
  existingSkills: SkillDefinition[],
  effectiveDocTypesMap: Record<string, DocumentTypeConfig>,
): {
  skill: SkillDefinition;
  tasks: SkillTask[];
  importDocTypes: Record<string, DocumentTypeConfig>;
} {
  const baseName =
    kind === "import"
      ? "New Import Pipeline"
      : kind === "gdt"
        ? "PVS GDT Export"
        : "New RPA Skill";
  const existingIds = new Set(existingSkills.map((s) => s.id));
  let slug = slugifySkillName(baseName);
  let n = 2;
  while (existingIds.has(slug)) {
    slug = `${slugifySkillName(baseName)}_${n}`;
    n += 1;
  }
  const finalName = n > 2 ? `${baseName} ${n - 1}` : baseName;

  if (kind === "import") {
    const seedDocs = copyDefaults
      ? (JSON.parse(JSON.stringify(effectiveDocTypesMap)) as Record<
          string,
          DocumentTypeConfig
        >)
      : {};
    return {
      skill: {
        id: slug,
        name: finalName,
        type: "import",
        description: "",
        allowed_extensions: [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
        split_multi_documents: true,
        save_empty_pages: false,
        enabled: true,
        document_types: seedDocs,
      },
      tasks: [],
      importDocTypes: seedDocs,
    };
  }

  if (kind === "gdt") {
    return {
      skill: {
        id: slug,
        name: finalName,
        type: "gdt",
        description: "Exports patient documents via GDT 2.1 Satzart 6310.",
        target_dir: "./PVS_Transfer",
        codepage: "cp437",
        sender_id: "ORDINFLOW",
        receiver_id: "PVS",
        filename_prefix: "ORDINFLOW",
        write_semaphore: false,
        enabled: true,
        document_types: {},
      },
      tasks: [],
      importDocTypes: {},
    };
  }

  const initialTasks: SkillTask[] = [
    {
      id: "task_1",
      title: "Open target application & prepare",
      actions: [
        {
          id: "act_1",
          action_type: "FOCUS_WINDOW",
          description: "Bring target window to foreground",
          window_title: "Remote Desktop*",
        },
      ],
    },
  ];
  return {
    skill: {
      id: slug,
      name: finalName,
      type: "export",
      description: "",
      target_window: "Remote Desktop*",
      rdp_path_prefix: "\\\\tsclient\\C",
      document_types: [],
      enabled: true,
      tasks: initialTasks,
    },
    tasks: initialTasks,
    importDocTypes: {},
  };
}
