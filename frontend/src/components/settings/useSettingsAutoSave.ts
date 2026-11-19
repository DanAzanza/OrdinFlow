import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useAppState } from "@/hooks/use-app-state";
import { systemApi } from "@/lib/api-client";
import { stripBraces } from "@/lib/utils";
import type { AppConfig } from "@/types/api";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

const INT_FIELDS = new Set<keyof AppConfig>([
  "dashboard_port",
  "n_gpu_layers",
  "n_batch",
  "type_k",
  "type_v",
  "vision_api_retries",
]);

const FLOAT_FIELDS = new Set<keyof AppConfig>(["vision_api_timeout"]);

export interface SettingsFormValues {
  watch_dir: string;
  target_base_dir: string;
  keep_inbox_files: boolean;
  dashboard_port: string;
  folder_structure: string;
  folder_delimiter: string;
  match_folder_by: string;
  llm_backend: string;
  server_url: string;
  server_api_key: string;
  llm_model_path: string;
  mmproj_path: string;
  n_gpu_layers: string;
  n_batch: string;
  type_k: string;
  type_v: string;
  vision_api_timeout: string;
  vision_api_retries: string;
}

function configToForm(cfg: AppConfig): SettingsFormValues {
  return {
    watch_dir: cfg.watch_dir || "",
    target_base_dir: cfg.target_base_dir || "",
    keep_inbox_files: Boolean(cfg.keep_inbox_files),
    dashboard_port: String(cfg.dashboard_port ?? 8080),
    folder_structure: Array.isArray(cfg.folder_structure)
      ? cfg.folder_structure.join(", ")
      : String(cfg.folder_structure || ""),
    folder_delimiter: cfg.folder_delimiter || "__",
    match_folder_by: Array.isArray(cfg.match_folder_by)
      ? cfg.match_folder_by.join(", ")
      : String(cfg.match_folder_by || ""),
    llm_backend: cfg.llm_backend || "llama_cpp",
    server_url: cfg.server_url || "",
    server_api_key: cfg.server_api_key || "",
    llm_model_path: cfg.llm_model_path || "",
    mmproj_path: cfg.mmproj_path || "",
    n_gpu_layers: String(cfg.n_gpu_layers ?? -1),
    n_batch: String(cfg.n_batch ?? 512),
    type_k: String(cfg.type_k ?? 8),
    type_v: String(cfg.type_v ?? 8),
    vision_api_timeout: String(cfg.vision_api_timeout ?? 120),
    vision_api_retries: String(cfg.vision_api_retries ?? 3),
  };
}

export function useSettingsAutoSave() {
  const { config, setConfig, refreshConfig, registerFlushConfigSave } =
    useAppState();

  const [form, setForm] = useState<SettingsFormValues | null>(null);
  const [invalidFields, setInvalidFields] = useState<Set<string>>(new Set());
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState("");
  const [apiKeyDirty, setApiKeyDirty] = useState(false);

  const lastSavedRef = useRef<Partial<AppConfig> | null>(null);
  const formRef = useRef<SettingsFormValues | null>(null);
  formRef.current = form;
  const apiKeyDirtyRef = useRef(apiKeyDirty);
  apiKeyDirtyRef.current = apiKeyDirty;

  const timerRef = useRef<number | null>(null);
  const statusTimerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadFromServer = useCallback(async () => {
    try {
      const cfg = await systemApi.getConfig();
      setConfig(cfg);
      lastSavedRef.current = cfg;
      setForm(configToForm(cfg));
      setApiKeyDirty(false);
      setInvalidFields(new Set());
      setSaveStatus("idle");
      setSaveError("");
    } catch {
      toast.error("Failed to load configuration");
    }
  }, [setConfig]);

  useEffect(() => {
    if (config && !form) {
      lastSavedRef.current = config;
      setForm(configToForm(config));
    } else if (!config) {
      void loadFromServer();
    }
  }, [config, form, loadFromServer]);

  const buildDelta = useCallback((): {
    payload: Partial<AppConfig>;
    invalid: Set<string>;
  } => {
    const current = formRef.current;
    const prev = lastSavedRef.current;
    const payload: Partial<AppConfig> = {};
    const invalid = new Set<string>();
    if (!current || !prev) return { payload, invalid };

    const checkScalar = <K extends keyof SettingsFormValues & keyof AppConfig>(
      key: K,
    ) => {
      const raw = current[key];
      if (key === "keep_inbox_files") {
        if (Boolean(raw) !== Boolean(prev.keep_inbox_files)) {
          payload.keep_inbox_files = Boolean(raw);
        }
        return;
      }

      if (key === "server_api_key") {
        if (!apiKeyDirtyRef.current || raw === "********") return;
        if (raw !== (prev.server_api_key || "")) {
          payload.server_api_key = String(raw).trim();
        }
        return;
      }

      if (key === "folder_structure" || key === "match_folder_by") {
        const arr = String(raw)
          .split(",")
          .map((s) => stripBraces(s))
          .filter(Boolean);
        const prevArr = Array.isArray(prev[key])
          ? (prev[key] as string[])
              .map((s) => stripBraces(String(s)))
              .filter(Boolean)
          : [];
        if (JSON.stringify(arr) !== JSON.stringify(prevArr)) {
          (payload as Record<string, unknown>)[key] =
            key === "folder_structure"
              ? String(raw)
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean)
              : arr;
        }
        return;
      }

      if (INT_FIELDS.has(key)) {
        const str = String(raw).trim();
        if (
          !str ||
          str === "-" ||
          Number.isNaN(Number(str)) ||
          !Number.isInteger(Number(str))
        ) {
          invalid.add(key);
          return;
        }
        const parsed = parseInt(str, 10);
        if (parsed !== prev[key]) {
          (payload as Record<string, unknown>)[key] = parsed;
        }
        return;
      }

      if (FLOAT_FIELDS.has(key)) {
        const str = String(raw).trim();
        if (!str || str === "-" || Number.isNaN(Number(str))) {
          invalid.add(key);
          return;
        }
        const parsed = parseFloat(str);
        if (parsed !== prev[key]) {
          (payload as Record<string, unknown>)[key] = parsed;
        }
        return;
      }

      const trimmed = String(raw).trim();
      if (trimmed !== String(prev[key] ?? "")) {
        (payload as Record<string, unknown>)[key] = trimmed;
      }
    };

    (Object.keys(current) as Array<keyof SettingsFormValues>).forEach((k) => {
      checkScalar(k as keyof SettingsFormValues & keyof AppConfig);
    });

    return { payload, invalid };
  }, []);

  const executeSave = useCallback(
    async (keepalive = false) => {
      const { payload, invalid } = buildDelta();
      setInvalidFields(invalid);

      if (Object.keys(payload).length === 0) return;

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      setSaveStatus("saving");
      setSaveError("");

      try {
        await systemApi.updateConfig(payload, {
          signal: keepalive ? undefined : ctrl.signal,
          keepalive,
        });

        lastSavedRef.current = { ...(lastSavedRef.current || {}), ...payload };
        setConfig((prev) => (prev ? { ...prev, ...payload } : prev));
        setApiKeyDirty(false);
        setSaveStatus("saved");
        if (statusTimerRef.current !== null) {
          window.clearTimeout(statusTimerRef.current);
        }
        statusTimerRef.current = window.setTimeout(() => {
          setSaveStatus("idle");
        }, 2400);

        if (
          "folder_structure" in payload ||
          "folder_delimiter" in payload ||
          "match_folder_by" in payload
        ) {
          void refreshConfig();
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        const msg =
          e instanceof Error ? e.message : "Failed to persist settings";
        setSaveStatus("error");
        setSaveError(msg);
        toast.error(`Settings save failed: ${msg}`);
      }
    },
    [buildDelta, setConfig, refreshConfig],
  );

  const scheduleSave = useCallback(
    (immediate = false) => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (immediate) {
        void executeSave(false);
      } else {
        timerRef.current = window.setTimeout(() => {
          timerRef.current = null;
          void executeSave(false);
        }, 500);
      }
    },
    [executeSave],
  );

  useEffect(() => {
    const flush = () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
        void executeSave(true);
      }
    };
    registerFlushConfigSave(flush);
    window.addEventListener("beforeunload", flush);
    return () => {
      registerFlushConfigSave(null);
      window.removeEventListener("beforeunload", flush);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      if (statusTimerRef.current !== null) {
        window.clearTimeout(statusTimerRef.current);
      }
    };
  }, [executeSave, registerFlushConfigSave]);

  const updateField = <K extends keyof SettingsFormValues>(
    key: K,
    value: SettingsFormValues[K],
    immediate = false,
  ) => {
    setForm((prev) => {
      if (!prev) return prev;
      const next = { ...prev, [key]: value };
      formRef.current = next;
      return next;
    });
    if (formRef.current) {
      formRef.current = { ...formRef.current, [key]: value };
    }
    if (key === "server_api_key") {
      apiKeyDirtyRef.current = true;
      setApiKeyDirty(true);
    }
    scheduleSave(immediate);
  };

  return {
    form,
    invalidFields,
    saveStatus,
    saveError,
    loadFromServer,
    scheduleSave,
    updateField,
  };
}
