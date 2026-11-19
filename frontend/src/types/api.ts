export type NavTab = "inbox" | "cases" | "skills" | "logs" | "settings";

export type ExtractionFieldSpec =
  | string
  | {
      description?: string;
      required?: boolean;
      [key: string]: unknown;
    };

export interface DocumentTypeConfig {
  emoji?: string;
  classification_desc?: string;
  vision_rules?: string;
  dependent?: boolean;
  extraction_fields?: Record<string, ExtractionFieldSpec>;
  routing?: {
    folder_template?: string;
    filename_template?: string;
    archive?: boolean;
    dependent?: boolean;
    match_folder_by?: string[];
    [key: string]: unknown;
  };
  validation?: Record<string, unknown>;
  review_on_inheritance?: boolean;
  [key: string]: unknown;
}

export interface AppConfig {
  watch_dir: string;
  target_base_dir: string;
  keep_inbox_files: boolean;
  dashboard_port: number;
  document_types?: Record<string, DocumentTypeConfig>;
  folder_structure: string[];
  folder_delimiter: string;
  match_folder_by: string[];
  llm_backend: "llama_cpp" | "server" | string;
  server_url?: string;
  server_api_key?: string;
  llm_model_path: string;
  mmproj_path: string;
  n_gpu_layers: number;
  n_batch: number;
  n_ubatch?: number;
  type_k: number;
  type_v: number;
  max_tokens?: number;
  n_threads?: number;
  render_dpi?: number;
  vision_api_timeout: number;
  vision_api_retries: number;
  crop_edge_threshold?: number;
  min_contour_area?: number;
  crop_padding?: number;
  white_border?: number;
  contrast_limit?: number;
  classify_dimension?: number;
  tier1_dimension?: number;
  tier2_dimension?: number;
  tier3_dimension?: number;
  vision_patch_size?: number;
  [key: string]: unknown;
}

export interface PageResultEntry {
  Document?: string;
  document?: string;
  DocumentType?: string;
  pages?: number[] | string;
  [key: string]: unknown;
}

export interface ExtractedMetadata {
  Document?: string;
  document?: string;
  DocumentType?: string;
  Signed?: boolean | string;
  page_results?: PageResultEntry[];
  [key: string]: unknown;
}

export interface InboxItem {
  name: string;
  path: string;
  status: "pending" | "review" | "processed" | string;
  reason?: string;
  grund?: string;
  extracted?: ExtractedMetadata;
  is_review?: boolean;
  is_pruefen?: boolean;
  is_processed?: boolean;
  is_abgearbeitet?: boolean;
  size: number;
  modified: string;
  preview_url?: string;
  file_url: string;
}

export interface FileMetaSidecar {
  status?: string;
  reason?: string;
  grund?: string;
  extracted?: ExtractedMetadata;
  executed_skills?: string[];
  Document?: string;
  Dokument?: string;
  document_type?: string;
  [key: string]: unknown;
}

export interface CaseSummary {
  folder: string;
  display_title: string;
  person: string;
  datum: string;
  produkt: string;
  parts: string[];
  doc_types: string[];
  file_count: number;
  is_approved: boolean;
  export_status: "pending_approval" | "approved" | "partially_exported" | "completed" | string;
  executed_skills: string[];
  total_applicable_tasks: number;
  completed_applicable_tasks: number;
}

export interface CaseFile {
  name: string;
  size: number;
  modified: string;
  has_preview: boolean;
  preview_url: string;
  file_url: string;
  is_preview: boolean;
  doc_type: string;
  executed_skills: string[];
  meta?: FileMetaSidecar;
}

export interface CaseDetailResponse {
  folder: string;
  files: CaseFile[];
}

export interface SplitDocumentSection {
  id: string;
  docType: string;
  pages: string;
  extracted: Record<string, unknown>;
}

export interface SplitSubmitPayload {
  context: "inbox" | "cases";
  filename: string;
  folder?: string | null;
  documents: Array<Record<string, unknown>>;
}

export interface SplitSubmitResponse {
  status: string;
  message?: string;
  results?: Array<{ folder: string; file: string }>;
}

export interface SkillLocator {
  type?: string;
  prompt?: string;
  value?: string;
  target?: string;
  automation_id?: string;
  offset?: [number, number];
  [key: string]: unknown;
}

export interface SkillAction {
  id?: string;
  action_type: string;
  description?: string;
  locator?: SkillLocator;
  text?: string;
  file_path?: string;
  window_title?: string;
  press_enter?: boolean;
  skill_id?: string;
  keys?: string[] | string;
  duration_s?: number;
  delay_ms?: number;
  timeout_s?: number;
  is_secret?: boolean;
  on_error?: string | Record<string, unknown>;
  on_item_error?: string;
  document_types?: string[] | string;
  condition?: string | { expr?: string; [key: string]: unknown };
  max_iterations?: number;
  extract_to_var?: string;
  variable?: string;
  value?: string;
  provider?: string;
  command?: string;
  script?: string;
  on_failure_action?: string;
  on_failure_skill?: string;
  _editing?: boolean;
  _revealed?: boolean;
  [key: string]: unknown;
}

export interface SkillTask {
  id: string;
  title: string;
  actions: SkillAction[];
  [key: string]: unknown;
}

export type SkillKind = "export" | "import" | "gdt" | "gdt_export";

export interface GdtDocTypeMapping {
  target_category?: string;
  [key: string]: unknown;
}

export interface SkillDefinition {
  id: string;
  name: string;
  type: SkillKind | string;
  description?: string;
  enabled?: boolean;
  target_window?: string;
  rdp_path_prefix?: string;
  launch_skill_id?: string;
  executable_path?: string;
  maximize_window?: boolean;
  recover_hung_process?: boolean;
  allowed_extensions?: string[] | string;
  split_multi_documents?: boolean;
  save_empty_pages?: boolean;
  document_types?:
    | string[]
    | string
    | Record<string, DocumentTypeConfig | GdtDocTypeMapping>;
  tasks?: SkillTask[];
  steps?: SkillAction[];
  actions?: SkillAction[];
  target_dir?: string;
  codepage?: string;
  sender_id?: string;
  receiver_id?: string;
  filename_prefix?: string;
  write_semaphore?: boolean;
  original_name?: string;
  [key: string]: unknown;
}

export interface QueueItemProgress {
  current?: number;
  total?: number;
  message?: string;
  percent?: number;
}

export interface SkillQueueItem {
  id: string;
  skill_id: string;
  skill_name: string;
  skill_type: string;
  status: "pending" | "running" | "completed" | "failed" | "paused" | "cancelled" | string;
  context?: Record<string, unknown>;
  progress?: QueueItemProgress;
  created_at?: number;
  started_at?: number | null;
  finished_at?: number | null;
  error?: string | null;
}

export interface SkillQueueState {
  is_running: boolean;
  is_paused: boolean;
  auto_repeat_enabled?: boolean;
  auto_repeat_interval_seconds?: number;
  active_item: SkillQueueItem | null;
  items: SkillQueueItem[];
}

export interface RecorderStatus {
  is_recording: boolean;
  skill_id?: string;
  skill_name?: string;
  step_count?: number;
  elapsed_seconds?: number;
  duration_seconds?: number;
  last_action?: string;
}

export interface SynthesisVariable {
  original?: string;
  variable?: string;
  label?: string;
}

export interface SkillSynthesis {
  name?: string;
  description?: string;
  suggested_document_types?: string[];
  detected_variables?: SynthesisVariable[];
  tasks?: SkillTask[];
}

export interface TestRunProgressEntry {
  current?: number;
  total?: number;
  message?: string;
  percent?: number;
}

export interface TestRunResponse {
  status: string;
  success: boolean;
  error?: string;
  step_id?: string;
  action_type?: string;
  duration_seconds: number;
  total_actions?: number;
  progress_log?: TestRunProgressEntry[];
}

export interface PendingCaseInfo {
  folder_name: string;
  folder_path: string;
}

export interface PendingCasesResponse {
  skill_id: string;
  count: number;
  cases: PendingCaseInfo[];
}

export interface SystemStatus {
  total?: number;
  success?: number;
  failed?: number;
  skipped?: number;
  avg_duration?: number;
  paused?: boolean;
  queue_size?: number;
  processed_count?: number;
  skill_queue?: SkillQueueState;
}

export interface LogEntry {
  id: number;
  time?: string;
  level?: string;
  message?: string;
}

export interface LogDeltaResponse {
  logs: LogEntry[];
  max_id: number;
}

export interface LogStats {
  recordsCount: number;
  totalFiles: number;
  completedFiles: number;
  manualReviewFiles: number;
  abortedFiles: number;
  emptyFiles: number;
  splitBatches: number;
  partialDocsSaved: number;
  directDocsMoved: number;
  totalArchivedDocs: number;
  successRate: string;
  totalProcessingTime: string;
  maxProcessingTime: string;
  avgTimePerFile: string;
  avgTimePerPage: string;
  totalPages: number;
  categoryCounts: Record<string, number>;
  tier1Count: number;
  tier1DirectConsensus: number;
  tier2Count: number;
  tier2Resolved: number;
  tier3Count: number;
  tier3Resolved: number;
  earlyStopCount: number;
  infoCount: number;
  warnCount: number;
  errorCount: number;
}

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  type: "folder" | "file" | string;
  size_str?: string;
  modified_str?: string;
}

export interface FsBreadcrumb {
  name: string;
  path: string;
}

export interface FsListResponse {
  status: string;
  current_path: string;
  parent_path: string | null;
  breadcrumbs: FsBreadcrumb[];
  drives: string[];
  quick_locations: Array<{ name: string; path: string }>;
  entries: FsEntry[];
  truncated: boolean;
}

export type LegalDocName = "privacy" | "license" | "thirdparty" | "checklist";

export type InspectorState =
  | { mode: "inbox"; filename: string }
  | { mode: "cases"; folder: string; filename: string }
  | { mode: "folder_edit"; folder: string };

export interface CopilotMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  time: string;
}
