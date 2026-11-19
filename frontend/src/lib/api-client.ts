import type {
  AppConfig,
  CaseDetailResponse,
  CaseSummary,
  DocumentTypeConfig,
  FileMetaSidecar,
  FsListResponse,
  InboxItem,
  LegalDocName,
  LogDeltaResponse,
  LogStats,
  PendingCasesResponse,
  RecorderStatus,
  SkillAction,
  SkillDefinition,
  SkillQueueState,
  SkillSynthesis,
  SplitSubmitPayload,
  SplitSubmitResponse,
  SystemStatus,
  TestRunResponse,
} from "@/types/api";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getSessionToken(): string {
  if (typeof document === "undefined") return "";
  const meta = document.querySelector<HTMLMetaElement>('meta[name="ordinflow-token"]');
  return meta?.content?.trim() || "";
}

export function getAppVersion(): string {
  if (typeof document === "undefined") return "1.0.0";
  const meta = document.querySelector<HTMLMetaElement>('meta[name="ordinflow-version"]');
  return meta?.content?.trim() || "1.0.0";
}

export function encodePathSegments(path: string): string {
  if (!path) return "";
  return String(path)
    .split("/")
    .filter((seg, idx, arr) => seg !== "" || idx === arr.length - 1)
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}

export async function apiRequest<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getSessionToken();
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("X-OrdinFlow-Token", token);
  }

  const res = await fetch(url, {
    ...options,
    credentials: "same-origin",
    headers,
  });

  if (!res.ok) {
    let errorMsg = `HTTP ${res.status}`;
    try {
      const errData = (await res.json()) as Record<string, unknown>;
      const raw = errData.error ?? errData.message ?? errData.detail;
      if (typeof raw === "string" && raw.trim()) {
        errorMsg = raw;
      }
    } catch {
      try {
        const textData = await res.text();
        if (textData) errorMsg = textData.slice(0, 140);
      } catch {
        // Ignore body read error
      }
    }
    throw new ApiError(errorMsg, res.status);
  }

  return (await res.json()) as T;
}

export const systemApi = {
  getStatus: () => apiRequest<SystemStatus>("/api/status"),
  heartbeat: () =>
    apiRequest<{ status: string }>("/api/heartbeat", { method: "POST" }),
  pauseRouter: () =>
    apiRequest<{ status: string }>("/api/router/pause", { method: "POST" }),
  resumeRouter: () =>
    apiRequest<{ status: string }>("/api/router/resume", { method: "POST" }),
  getConfig: () => apiRequest<AppConfig>("/api/config"),
  updateConfig: (
    payload: Partial<AppConfig>,
    options: { signal?: AbortSignal; keepalive?: boolean } = {},
  ) =>
    apiRequest<{ status: string; changed: string[] }>("/api/config", {
      method: "PUT",
      body: JSON.stringify(payload),
      signal: options.signal,
      keepalive: options.keepalive,
    }),
  getLogs: (sinceId = 0, limit = 300) =>
    apiRequest<LogDeltaResponse>(`/api/log?since_id=${sinceId}&limit=${limit}`),
  clearLogs: () =>
    apiRequest<{ status: string }>("/api/log/clear", { method: "POST" }),
  getLogStats: () => apiRequest<LogStats>("/api/log/stats"),
  listFilesystem: (
    params: { path?: string; type?: string; filter?: string },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      path: params.path || "",
      type: params.type || "folder",
      filter: params.filter || "",
    });
    return apiRequest<FsListResponse>(`/api/system/fs_list?${query.toString()}`, {
      signal,
    });
  },
};

export const inboxApi = {
  list: () => apiRequest<InboxItem[]>("/api/inbox"),
  getMeta: (filename: string) =>
    apiRequest<FileMetaSidecar>(`/api/file/meta/inbox/${encodePathSegments(filename)}`),
  retry: (filename: string) =>
    apiRequest<{ status: string; task_id?: string }>(
      `/api/inbox/${encodePathSegments(filename)}/retry`,
      { method: "POST" },
    ),
  autoAssign: (filename: string) =>
    apiRequest<{ status: string }>(
      `/api/inbox/${encodePathSegments(filename)}/auto_assign`,
      { method: "POST" },
    ),
  deleteFile: (filename: string) =>
    apiRequest<{ status: string }>(`/api/inbox/${encodePathSegments(filename)}`, {
      method: "DELETE",
    }),
};

export const casesApi = {
  list: () => apiRequest<CaseSummary[]>("/api/cases"),
  getDetail: (folder: string) =>
    apiRequest<CaseDetailResponse>(`/api/cases/${encodePathSegments(folder)}`),
  approve: (folder: string, approved: boolean) =>
    apiRequest<{ status: string; folder: string; is_approved: boolean }>(
      "/api/cases/approve",
      {
        method: "POST",
        body: JSON.stringify({ folder, approved }),
      },
    ),
  updateFolder: (folder: string, payload: Record<string, string>) =>
    apiRequest<{ status: string; folder: string; message?: string }>(
      `/api/cases/${encodePathSegments(folder)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),
  deleteFolder: (folder: string) =>
    apiRequest<{ status: string }>(`/api/cases/${encodePathSegments(folder)}`, {
      method: "DELETE",
    }),
  deleteFile: (folder: string, filename: string) =>
    apiRequest<{ status: string }>(
      `/api/cases/${encodePathSegments(folder)}/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  getFileMeta: (folder: string, filename: string) =>
    apiRequest<FileMetaSidecar>(
      `/api/file/meta/cases/${encodePathSegments(folder)}/${encodeURIComponent(filename)}`,
    ),
  submitSplitInspector: (payload: SplitSubmitPayload) =>
    apiRequest<SplitSubmitResponse>("/api/split_inspector/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export const skillsApi = {
  list: () => apiRequest<{ skills: SkillDefinition[] }>("/api/skills"),
  save: (skill: Partial<SkillDefinition>) =>
    apiRequest<{ status: string; skill_id: string; name: string }>("/api/skills", {
      method: "POST",
      body: JSON.stringify(skill),
    }),
  deleteSkill: (skillId: string) =>
    apiRequest<{ status: string }>(`/api/skills/${encodeURIComponent(skillId)}`, {
      method: "DELETE",
    }),
  duplicate: (skillId: string) =>
    apiRequest<{ status: string; skill: SkillDefinition }>(
      `/api/skills/${encodeURIComponent(skillId)}/duplicate`,
      { method: "POST" },
    ),
  toYaml: (skill: Partial<SkillDefinition>) =>
    apiRequest<{ status: string; yaml: string }>("/api/skills/to_yaml", {
      method: "POST",
      body: JSON.stringify({ skill }),
    }),
  fromYaml: (yamlText: string) =>
    apiRequest<{ status: string; skill: SkillDefinition }>("/api/skills/from_yaml", {
      method: "POST",
      body: JSON.stringify({ yaml: yamlText }),
    }),
  saveDocTypes: (
    skillId: string,
    documentTypes: Record<string, DocumentTypeConfig>,
  ) =>
    apiRequest<{ status: string; document_types: Record<string, DocumentTypeConfig> }>(
      `/api/skills/${encodeURIComponent(skillId)}/documents`,
      {
        method: "PUT",
        body: JSON.stringify({ document_types: documentTypes }),
      },
    ),
  getDocTypes: (skillId: string) =>
    apiRequest<{ document_types: Record<string, DocumentTypeConfig> }>(
      `/api/skills/${encodeURIComponent(skillId)}/documents`,
    ),
  aiModify: (
    skill: Partial<SkillDefinition>,
    instruction: string,
    history: Array<{ role: string; content: string }>,
  ) =>
    apiRequest<{ status: string; skill: SkillDefinition; reply: string }>(
      "/api/skills/ai_modify",
      {
        method: "POST",
        body: JSON.stringify({ skill, instruction, history }),
      },
    ),
  pickElement: (windowTitle: string, delaySeconds = 1.0) =>
    apiRequest<{
      status: string;
      cursor: [number, number];
      ocr_text: string;
      locator: { type: string; prompt: string; offset: [number, number] };
    }>("/api/skills/pick_element", {
      method: "POST",
      body: JSON.stringify({
        window_title: windowTitle,
        delay_seconds: delaySeconds,
      }),
    }),
  testRun: (
    skill: Partial<SkillDefinition>,
    context: Record<string, unknown> = {},
  ) =>
    apiRequest<TestRunResponse>("/api/skills/test_run", {
      method: "POST",
      body: JSON.stringify({ skill, context }),
    }),
  getPendingCases: (skillId: string) =>
    apiRequest<PendingCasesResponse>(
      `/api/skills/${encodeURIComponent(skillId)}/pending_cases`,
    ),
  runBatch: (skillId: string) =>
    apiRequest<{ status: string; queued_count: number; cases: string[] }>(
      `/api/skills/${encodeURIComponent(skillId)}/run_batch`,
      { method: "POST" },
    ),
  startRecorder: (skillName: string) =>
    apiRequest<{ status: string; skill_id?: string; skill_name?: string }>(
      "/api/skills/recorder/start",
      {
        method: "POST",
        body: JSON.stringify({ skill_name: skillName }),
      },
    ),
  stopRecorder: () =>
    apiRequest<{
      status: string;
      skill?: { steps?: SkillAction[]; [key: string]: unknown };
    }>("/api/skills/recorder/stop", { method: "POST" }),
  getRecorderStatus: () =>
    apiRequest<RecorderStatus>("/api/skills/recorder/status"),
  synthesize: (steps: SkillAction[], userInstruction = "") =>
    apiRequest<{ status: string; synthesis: SkillSynthesis }>(
      "/api/skills/synthesize",
      {
        method: "POST",
        body: JSON.stringify({ steps, user_instruction: userInstruction }),
      },
    ),
};

export const queueApi = {
  get: () => apiRequest<SkillQueueState>("/api/skills/queue"),
  add: (skillId: string, context: Record<string, unknown> = {}) =>
    apiRequest<{ status: string }>("/api/skills/queue/add", {
      method: "POST",
      body: JSON.stringify({ skill_id: skillId, context }),
    }),
  remove: (queueId: string) =>
    apiRequest<{ status: string }>("/api/skills/queue/remove", {
      method: "POST",
      body: JSON.stringify({ queue_id: queueId }),
    }),
  clear: () =>
    apiRequest<{ status: string }>("/api/skills/queue/clear", {
      method: "POST",
    }),
  reorder: (itemIds: string[]) =>
    apiRequest<{ status: string }>("/api/skills/queue/reorder", {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds }),
    }),
  start: () =>
    apiRequest<{ status: string; is_running: boolean; is_paused: boolean }>(
      "/api/skills/queue/start",
      { method: "POST" },
    ),
  pause: () =>
    apiRequest<{ status: string; is_running: boolean; is_paused: boolean }>(
      "/api/skills/queue/pause",
      { method: "POST" },
    ),
  resume: () =>
    apiRequest<{ status: string; is_running: boolean; is_paused: boolean }>(
      "/api/skills/queue/resume",
      { method: "POST" },
    ),
  stop: () =>
    apiRequest<{ status: string; is_running: boolean; is_paused: boolean }>(
      "/api/skills/queue/stop",
      { method: "POST" },
    ),
  setAutoRepeat: (enabled: boolean, intervalSeconds = 300) =>
    apiRequest<{
      status: string;
      auto_repeat_enabled: boolean;
      auto_repeat_interval_seconds: number;
    }>("/api/skills/queue/auto_repeat", {
      method: "POST",
      body: JSON.stringify({ enabled, interval_seconds: intervalSeconds }),
    }),
};

export const legalApi = {
  getDocument: (docName: LegalDocName) =>
    apiRequest<{ status: string; content: string }>(`/api/legal/${docName}`),
};
