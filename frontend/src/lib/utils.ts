import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type {
  AppConfig,
  DocumentTypeConfig,
  SkillAction,
  SkillDefinition,
  SkillTask,
} from "@/types/api";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatSize(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export function splitFilenameExt(filename: string): { base: string; ext: string } {
  const clean = filename || "";
  const lastDot = clean.lastIndexOf(".");
  if (lastDot <= 0 || lastDot === clean.length - 1) {
    return { base: clean, ext: "" };
  }
  return {
    base: clean.slice(0, lastDot),
    ext: clean.slice(lastDot),
  };
}

export function isPdfUrl(urlOrPath: string | null | undefined): boolean {
  if (!urlOrPath) return false;
  const clean = String(urlOrPath).split(/[?#]/)[0]?.toLowerCase() ?? "";
  return clean.endsWith(".pdf");
}

export function stripBraces(value: string): string {
  return String(value || "")
    .trim()
    .replace(/^\{+|\}+$/g, "")
    .trim();
}

export function cleanHeaderLabel(str: string): string {
  if (!str) return "";
  return str.replace(/\}\{/g, "} {").replace(/[{}]/g, "").trim();
}

export function splitByDelimiter(
  folderName: string,
  delimiter?: string,
): string[] {
  if (!folderName) return [];
  const delim = delimiter || "--";
  if (folderName.includes(delim)) return folderName.split(delim);
  if (folderName.includes("__")) return folderName.split("__");
  return [folderName];
}

export function formatDateString(dateStr: string | null | undefined): string {
  if (!dateStr || dateStr === "–") return "–";
  const s = String(dateStr).trim();
  const mYmd = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (mYmd) return `${mYmd[3]}.${mYmd[2]}.${mYmd[1]}`;
  const mDmy = s.match(/^(\d{1,2})[.-](\d{1,2})[.-](\d{4})$/);
  if (mDmy && mDmy[1] && mDmy[2] && mDmy[3]) {
    return `${mDmy[1].padStart(2, "0")}.${mDmy[2].padStart(2, "0")}.${mDmy[3]}`;
  }
  return dateStr;
}

export function parseDateToTimestamp(
  dateStr: string | null | undefined,
): number | null {
  if (!dateStr || dateStr === "–" || dateStr === "-") return null;
  const s = String(dateStr).trim();
  const mIso = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (mIso) {
    return new Date(Number(mIso[1]), Number(mIso[2]) - 1, Number(mIso[3])).getTime();
  }
  const mDe = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (mDe) {
    return new Date(Number(mDe[3]), Number(mDe[2]) - 1, Number(mDe[1])).getTime();
  }
  return null;
}

export function isValidCalendarDate(
  year: number,
  month: number,
  day: number,
): boolean {
  if (year < 1900 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) {
    return false;
  }
  const d = new Date(Date.UTC(year, month - 1, day));
  return (
    d.getUTCFullYear() === year &&
    d.getUTCMonth() === month - 1 &&
    d.getUTCDate() === day
  );
}

export function normalizeDateForInput(val: unknown): string | null {
  if (val === null || val === undefined) return null;
  let s = String(val).trim();
  if (!s) return null;

  s = s.split(/[T\s]/)[0]?.trim() ?? "";
  let y: number | undefined;
  let m: number | undefined;
  let d: number | undefined;

  let match = s.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/);
  if (match && match[1] && match[2] && match[3]) {
    y = parseInt(match[1], 10);
    m = parseInt(match[2], 10);
    d = parseInt(match[3], 10);
  } else {
    match = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/);
    if (match && match[1] && match[2] && match[3]) {
      d = parseInt(match[1], 10);
      m = parseInt(match[2], 10);
      const rawYear = parseInt(match[3], 10);
      y = rawYear < 100 ? (rawYear <= 50 ? 2000 + rawYear : 1900 + rawYear) : rawYear;
    }
  }

  if (y && m && d && isValidCalendarDate(y, m, d)) {
    return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }
  return null;
}

export function getEffectiveDocTypes(
  skills: SkillDefinition[],
  config: AppConfig | null,
): Record<string, DocumentTypeConfig> {
  const docTypes: Record<string, DocumentTypeConfig> = {};

  for (const skill of skills) {
    if (
      skill.type === "import" &&
      skill.enabled !== false &&
      skill.document_types &&
      !Array.isArray(skill.document_types) &&
      typeof skill.document_types === "object"
    ) {
      for (const [dtName, dtConfig] of Object.entries(skill.document_types)) {
        docTypes[dtName] = dtConfig as DocumentTypeConfig;
      }
    }
  }

  if (Object.keys(docTypes).length === 0 && config?.document_types) {
    return config.document_types;
  }

  return docTypes;
}

export function getDocTypeConfig(
  name: string | null | undefined,
  docTypes: Record<string, DocumentTypeConfig>,
): DocumentTypeConfig | null {
  if (!name) return null;
  if (docTypes[name]) return docTypes[name] ?? null;
  const lower = String(name).toLowerCase();
  for (const [k, v] of Object.entries(docTypes)) {
    if (k.toLowerCase() === lower) return v;
  }
  return null;
}

export function extractFieldsFromFilenameAndFolder(
  docType: string,
  filename: string,
  folderName: string,
  docTypes: Record<string, DocumentTypeConfig>,
  config: AppConfig | null,
): Record<string, unknown> {
  const extracted: Record<string, unknown> = {};
  const rawName = (filename || "").split("/").pop() || "";
  const baseName = rawName.replace(/\.[^/.]+$/, "");
  const docCfg = getDocTypeConfig(docType, docTypes);

  const filenameTemplate = docCfg?.routing?.filename_template || "";
  if (filenameTemplate && filenameTemplate.includes("{")) {
    const paramNames: string[] = [];
    const templateParts = filenameTemplate.split(/\{(\w+)\}/g);

    let patternStr = "^";
    for (let i = 0; i < templateParts.length; i++) {
      const part = templateParts[i] ?? "";
      if (i % 2 === 1) {
        paramNames.push(part);
        patternStr += "(.*?)";
      } else {
        patternStr += part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }
    }
    patternStr += "(?:_[\\d]+)?$";

    try {
      const rx = new RegExp(patternStr, "i");
      const match = baseName.match(rx);
      if (match && match.length > 1) {
        paramNames.forEach((param, idx) => {
          const val = match[idx + 1];
          if (val && val !== "----") {
            extracted[param] = val;
          }
        });
      }
    } catch {
      // Ignore invalid regex template
    }
  }

  const delimiter = baseName.includes("__")
    ? "__"
    : baseName.includes("--")
      ? "--"
      : "_";
  const parts = baseName
    .split(delimiter)
    .map((p) => p.trim())
    .filter(Boolean);

  if (parts.length > 0 && !extracted.Document && parts[0] !== "----") {
    extracted.Document = parts[0];
  }

  if (folderName) {
    const folderStruct = Array.isArray(config?.folder_structure)
      ? config.folder_structure
      : [];
    const fDelimiter =
      config?.folder_delimiter ||
      (folderName.includes("--") ? "--" : folderName.includes("__") ? "__" : "-");
    const leafFolder = folderName.split("/").pop() || folderName;
    const fParts = leafFolder.split(fDelimiter).map((p) => p.trim());

    folderStruct.forEach((comp, idx) => {
      if (idx >= fParts.length) return;
      const val = fParts[idx];
      const fieldKey = stripBraces(String(comp));
      if (fieldKey && val && val !== "----" && val !== "MISSING" && !extracted[fieldKey]) {
        extracted[fieldKey] = val;
      }
    });
  }

  return extracted;
}

export function formatPageRange(pages: unknown): string {
  if (!pages || pages === "all" || pages === "*") return "all";
  if (Array.isArray(pages)) {
    if (pages.length === 0) return "all";
    const nums = pages
      .map(Number)
      .filter((n) => !Number.isNaN(n))
      .sort((a, b) => a - b);
    if (nums.length === 0) return "all";
    const isContiguous = nums.every((n, i) => i === 0 || n === (nums[i - 1] ?? 0) + 1);
    if (isContiguous && nums.length > 1) {
      return `${nums[0]}-${nums[nums.length - 1]}`;
    }
    return nums.join(", ");
  }
  return String(pages).trim();
}

export function isActionSensitive(act: SkillAction | null | undefined): boolean {
  if (!act) return false;
  if (act.is_secret) return true;
  const text = `${act.description || ""} ${act.text || ""}`.toLowerCase();
  return /\b(password|passwort|kennwort|geheim|secret|pin|api_key|token|access_key|auth_token|bearer)\b/i.test(
    text,
  );
}

export function stripInternalActionFlags(tasks: SkillTask[]): SkillTask[] {
  return tasks.map((task) => ({
    ...task,
    actions: (task.actions || []).map((act) => {
      const clean: SkillAction = { ...act };
      delete clean._editing;
      delete clean._revealed;
      return clean;
    }),
  }));
}

export function getAvailableSkillVariables(
  skills: SkillDefinition[],
  config: AppConfig | null,
  filterDocTypes: string[] | null = null,
): string[] {
  const vars = new Set<string>([
    "{document_fullpath}",
    "{document_filename}",
    "{document_basename}",
    "{document_extension}",
    "{case_folder}",
    "{Datum}",
  ]);

  const activeFilter =
    filterDocTypes && filterDocTypes.length > 0 ? filterDocTypes : null;

  const collectFromDocTypes = (
    docTypes: Record<string, DocumentTypeConfig> | undefined,
  ) => {
    if (!docTypes || typeof docTypes !== "object") return;
    for (const [dtName, dtConfig] of Object.entries(docTypes)) {
      if (activeFilter && !activeFilter.includes(dtName) && !activeFilter.includes("*")) {
        continue;
      }
      if (dtConfig?.extraction_fields && typeof dtConfig.extraction_fields === "object") {
        for (const fieldName of Object.keys(dtConfig.extraction_fields)) {
          if (fieldName) vars.add(`{${fieldName}}`);
        }
      }
    }
  };

  for (const skill of skills) {
    if (
      skill.type === "import" &&
      skill.document_types &&
      !Array.isArray(skill.document_types) &&
      typeof skill.document_types === "object"
    ) {
      collectFromDocTypes(skill.document_types as Record<string, DocumentTypeConfig>);
    }
  }

  collectFromDocTypes(config?.document_types);

  if (Array.isArray(config?.folder_structure)) {
    for (const segment of config.folder_structure) {
      if (typeof segment === "string") {
        const matches = segment.match(/\{([^{}]+)\}/g);
        if (matches) {
          matches.forEach((m) => vars.add(m));
        }
      }
    }
  }

  vars.add("{category}");
  vars.add("{Jahr}");
  vars.add("{Zeit}");

  return Array.from(vars);
}

export function slugifySkillName(name: string): string {
  return (
    (name || "")
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9_]+/g, "_")
      .replace(/^_+|_+$/g, "") || "skill"
  );
}
