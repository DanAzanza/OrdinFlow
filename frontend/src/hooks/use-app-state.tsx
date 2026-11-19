import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import {
  casesApi,
  inboxApi,
  skillsApi,
  systemApi,
  queueApi,
} from "@/lib/api-client";
import { useServerEvents } from "@/lib/sse";
import type {
  AppConfig,
  CaseSummary,
  InboxItem,
  InspectorState,
  LogEntry,
  LogStats,
  NavTab,
  RecorderStatus,
  SkillDefinition,
  SkillQueueState,
  SystemStatus,
} from "@/types/api";

const VALID_TABS: NavTab[] = ["inbox", "cases", "skills", "logs", "settings"];

function parseTabFromHash(): NavTab {
  if (typeof window === "undefined") return "inbox";
  const raw = window.location.hash.replace(/^#\/?/, "").trim().toLowerCase();
  return VALID_TABS.includes(raw as NavTab) ? (raw as NavTab) : "inbox";
}

interface AppContextValue {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  config: AppConfig | null;
  setConfig: React.Dispatch<React.SetStateAction<AppConfig | null>>;
  status: SystemStatus | null;
  inbox: InboxItem[];
  cases: CaseSummary[];
  skills: SkillDefinition[];
  queue: SkillQueueState;
  sseConnected: boolean;
  recorderStatus: RecorderStatus;
  setRecorderStatus: React.Dispatch<React.SetStateAction<RecorderStatus>>;
  isLoadingInitial: boolean;
  inspectorState: InspectorState | null;
  setInspectorState: React.Dispatch<React.SetStateAction<InspectorState | null>>;
  queueDrawerOpen: boolean;
  setQueueDrawerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  selectedSkillId: string | null;
  setSelectedSkillId: React.Dispatch<React.SetStateAction<string | null>>;
  reviewOnly: boolean;
  setReviewOnly: React.Dispatch<React.SetStateAction<boolean>>;
  logRecords: LogEntry[];
  logStats: LogStats | null;
  clearLocalLogs: () => void;
  refreshInbox: () => Promise<void>;
  refreshCases: () => Promise<void>;
  refreshSkills: () => Promise<SkillDefinition[]>;
  refreshConfig: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshQueue: () => Promise<SkillQueueState | null>;
  refreshLogStats: (force?: boolean) => Promise<void>;
  toggleEnginePause: () => Promise<void>;
  registerFlushConfigSave: (fn: (() => void) | null) => void;
}

const DEFAULT_QUEUE: SkillQueueState = {
  is_running: false,
  is_paused: false,
  auto_repeat_enabled: false,
  auto_repeat_interval_seconds: 300,
  active_item: null,
  items: [],
};

const AppContext = createContext<AppContextValue | null>(null);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [activeTab, setActiveTabState] = useState<NavTab>(parseTabFromHash);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [queue, setQueue] = useState<SkillQueueState>(DEFAULT_QUEUE);
  const [recorderStatus, setRecorderStatus] = useState<RecorderStatus>({
    is_recording: false,
  });
  const [isLoadingInitial, setIsLoadingInitial] = useState(true);
  const [inspectorState, setInspectorState] = useState<InspectorState | null>(null);
  const [queueDrawerOpen, setQueueDrawerOpen] = useState(false);
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [logRecords, setLogRecords] = useState<LogEntry[]>([]);
  const [logStats, setLogStats] = useState<LogStats | null>(null);

  const lastLogIdRef = useRef(0);
  const lastLogStatsFetchRef = useRef(0);
  const flushConfigFnRef = useRef<(() => void) | null>(null);
  const syncingRef = useRef(false);
  const activeTabRef = useRef(activeTab);
  activeTabRef.current = activeTab;

  const registerFlushConfigSave = useCallback((fn: (() => void) | null) => {
    flushConfigFnRef.current = fn;
  }, []);

  const setActiveTab = useCallback((tab: NavTab) => {
    if (activeTabRef.current === "settings" && tab !== "settings") {
      flushConfigFnRef.current?.();
    }
    setActiveTabState(tab);
    if (typeof window !== "undefined") {
      const targetHash = `#/${tab}`;
      if (window.location.hash !== targetHash) {
        window.location.hash = targetHash;
      }
    }
    if (tab !== "inbox" && tab !== "cases") {
      setInspectorState(null);
    }
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const next = parseTabFromHash();
      setActiveTabState(next);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await systemApi.getConfig();
      setConfig(cfg);
    } catch (e) {
      console.error("Failed to fetch config:", e);
    }
  }, []);

  const refreshInbox = useCallback(async () => {
    try {
      const data = await inboxApi.list();
      setInbox(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to fetch inbox:", e);
    }
  }, []);

  const refreshCases = useCallback(async () => {
    try {
      const data = await casesApi.list();
      setCases(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to fetch cases:", e);
    }
  }, []);

  const refreshSkills = useCallback(async () => {
    try {
      const data = await skillsApi.list();
      const list = Array.isArray(data.skills) ? data.skills : [];
      setSkills(list);
      return list;
    } catch (e) {
      console.error("Failed to fetch skills:", e);
      return [];
    }
  }, []);

  const refreshQueue = useCallback(async () => {
    try {
      const q = await queueApi.get();
      setQueue(q);
      return q;
    } catch (e) {
      console.error("Failed to fetch queue:", e);
      return null;
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const st = await systemApi.getStatus();
      setStatus(st);
      if (st.skill_queue) {
        setQueue(st.skill_queue);
      }
    } catch (e) {
      console.error("Failed to fetch status:", e);
    }
  }, []);

  const refreshLogStats = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastLogStatsFetchRef.current < 4000) {
      return;
    }
    lastLogStatsFetchRef.current = now;
    try {
      const stats = await systemApi.getLogStats();
      setLogStats(stats);
    } catch (e) {
      console.error("Failed to fetch log stats:", e);
    }
  }, []);

  const clearLocalLogs = useCallback(() => {
    lastLogIdRef.current = 0;
    setLogRecords([]);
  }, []);

  const handleLogEvent = useCallback((entry: LogEntry) => {
    if (entry.id === undefined || entry.id <= lastLogIdRef.current) return;
    lastLogIdRef.current = entry.id;
    setLogRecords((prev) => {
      const next = [...prev, entry];
      return next.length > 1500 ? next.slice(-1500) : next;
    });
  }, []);

  const { connected: sseConnected, reconnect: reconnectSse } =
    useServerEvents(handleLogEvent);

  const syncAll = useCallback(async () => {
    if (syncingRef.current) return;
    syncingRef.current = true;
    try {
      await Promise.allSettled([
        refreshStatus(),
        refreshCases(),
        refreshInbox(),
        refreshSkills(),
      ]);
    } finally {
      syncingRef.current = false;
    }
  }, [refreshStatus, refreshCases, refreshInbox, refreshSkills]);

  // Initial mount bootstrap
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      refreshConfig(),
      refreshSkills(),
      refreshStatus(),
      refreshCases(),
      refreshInbox(),
      skillsApi.getRecorderStatus().then((rs) => {
        if (active && rs) setRecorderStatus(rs);
      }),
    ]).finally(() => {
      if (active) setIsLoadingInitial(false);
    });
    return () => {
      active = false;
    };
  }, [refreshConfig, refreshSkills, refreshStatus, refreshCases, refreshInbox]);

  // Always-active 12s heartbeat (never pause on hidden tab so backend does not auto-terminate)
  useEffect(() => {
    const timer = window.setInterval(() => {
      systemApi.heartbeat().catch(() => {});
    }, 12000);
    return () => window.clearInterval(timer);
  }, []);

  // Visibility-aware polling + focus/visibility resync
  useEffect(() => {
    let statusTimer: number | null = null;
    let syncTimer: number | null = null;
    let debounceTimer: number | null = null;

    const startPolling = () => {
      if (statusTimer === null) {
        statusTimer = window.setInterval(() => {
          void refreshStatus();
        }, 6000);
      }
      if (syncTimer === null) {
        syncTimer = window.setInterval(() => {
          void syncAll();
        }, 10000);
      }
    };

    const stopPolling = () => {
      if (statusTimer !== null) {
        window.clearInterval(statusTimer);
        statusTimer = null;
      }
      if (syncTimer !== null) {
        window.clearInterval(syncTimer);
        syncTimer = null;
      }
    };

    const triggerDebouncedSync = () => {
      if (debounceTimer !== null) window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        void syncAll();
      }, 300);
    };

    if (document.visibilityState === "visible") {
      startPolling();
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        systemApi.heartbeat().catch(() => {});
        reconnectSse();
        startPolling();
        triggerDebouncedSync();
      } else {
        stopPolling();
      }
    };

    const onFocus = () => {
      systemApi.heartbeat().catch(() => {});
      triggerDebouncedSync();
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", onFocus);

    return () => {
      stopPolling();
      if (debounceTimer !== null) window.clearTimeout(debounceTimer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", onFocus);
    };
  }, [refreshStatus, syncAll, reconnectSse]);

  // Delta log polling when on Logs tab
  useEffect(() => {
    if (activeTab !== "logs") return;

    let cancelled = false;
    let inFlight = false;

    const fetchDelta = async () => {
      if (inFlight || cancelled) return;
      inFlight = true;
      try {
        const res = await systemApi.getLogs(lastLogIdRef.current, 300);
        if (cancelled) return;
        if (res.max_id !== undefined && res.max_id < lastLogIdRef.current) {
          lastLogIdRef.current = res.max_id;
          setLogRecords(res.logs || []);
        } else if (res.logs && res.logs.length > 0) {
          lastLogIdRef.current = res.max_id ?? lastLogIdRef.current;
          setLogRecords((prev) => {
            const seen = new Set(prev.map((l) => l.id));
            const additions = res.logs.filter((l) => !seen.has(l.id));
            if (additions.length === 0) return prev;
            const merged = [...prev, ...additions];
            return merged.length > 1500 ? merged.slice(-1500) : merged;
          });
        } else if (res.max_id !== undefined) {
          lastLogIdRef.current = res.max_id;
        }
      } catch (e) {
        console.error("Failed to fetch log delta:", e);
      } finally {
        inFlight = false;
      }
    };

    void fetchDelta();
    void refreshLogStats(true);

    const deltaTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void fetchDelta();
        void refreshLogStats(false);
      }
    }, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(deltaTimer);
    };
  }, [activeTab, refreshLogStats]);

  // Queue polling when running/paused or queue drawer is open
  useEffect(() => {
    const shouldPoll = queueDrawerOpen || queue.is_running || queue.is_paused;
    if (!shouldPoll) return;

    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refreshQueue();
      }
    }, 1500);

    return () => window.clearInterval(timer);
  }, [queueDrawerOpen, queue.is_running, queue.is_paused, refreshQueue]);

  // Recorder status polling while recording
  useEffect(() => {
    if (!recorderStatus.is_recording) return;
    const timer = window.setInterval(() => {
      skillsApi
        .getRecorderStatus()
        .then((rs) => {
          setRecorderStatus(rs);
        })
        .catch(() => {});
    }, 1000);
    return () => window.clearInterval(timer);
  }, [recorderStatus.is_recording]);

  const toggleEnginePause = useCallback(async () => {
    const currentlyPaused = Boolean(status?.paused);
    try {
      if (currentlyPaused) {
        await systemApi.resumeRouter();
        toast.success("Processing engine resumed");
      } else {
        await systemApi.pauseRouter();
        toast.info("Processing engine paused");
      }
      await refreshStatus();
    } catch (e) {
      toast.error(
        `Failed to toggle engine: ${e instanceof Error ? e.message : "Unknown error"}`,
      );
    }
  }, [status?.paused, refreshStatus]);

  return (
    <AppContext.Provider
      value={{
        activeTab,
        setActiveTab,
        config,
        setConfig,
        status,
        inbox,
        cases,
        skills,
        queue,
        sseConnected,
        recorderStatus,
        setRecorderStatus,
        isLoadingInitial,
        inspectorState,
        setInspectorState,
        queueDrawerOpen,
        setQueueDrawerOpen,
        selectedSkillId,
        setSelectedSkillId,
        reviewOnly,
        setReviewOnly,
        logRecords,
        logStats,
        clearLocalLogs,
        refreshInbox,
        refreshCases,
        refreshSkills,
        refreshConfig,
        refreshStatus,
        refreshQueue,
        refreshLogStats,
        toggleEnginePause,
        registerFlushConfigSave,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppState(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useAppState must be used within AppStateProvider");
  }
  return ctx;
}
