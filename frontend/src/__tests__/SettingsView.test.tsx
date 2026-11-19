import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsView } from "@/components/settings/SettingsView";
import type { AppConfig } from "@/types/api";

const { INITIAL_CONFIG, mockSetConfig, mockRefreshConfig, mockRegisterFlush, mockUpdateConfig } =
  vi.hoisted(() => ({
    INITIAL_CONFIG: {
      watch_dir: "C:/Inbox",
      target_base_dir: "C:/Cases",
      keep_inbox_files: false,
      dashboard_port: 8080,
      folder_structure: ["{LastName}", "{FirstName}"],
      folder_delimiter: "__",
      match_folder_by: ["LastName", "FirstName"],
      llm_backend: "llama_cpp",
      server_url: "http://127.0.0.1:8081/v1",
      server_api_key: "********",
      llm_model_path: "models/qwen.gguf",
      mmproj_path: "models/mmproj.gguf",
      n_gpu_layers: -1,
      n_batch: 512,
      type_k: 8,
      type_v: 8,
      vision_api_timeout: 120,
      vision_api_retries: 3,
    } as AppConfig,
    mockSetConfig: vi.fn(),
    mockRefreshConfig: vi.fn().mockResolvedValue(undefined),
    mockRegisterFlush: vi.fn(),
    mockUpdateConfig: vi.fn().mockResolvedValue({ status: "ok", changed: [] }),
  }));

vi.mock("@/hooks/use-app-state", () => ({
  useAppState: () => ({
    config: INITIAL_CONFIG,
    setConfig: mockSetConfig,
    refreshConfig: mockRefreshConfig,
    registerFlushConfigSave: mockRegisterFlush,
  }),
}));

vi.mock("@/lib/api-client", () => ({
  systemApi: {
    getConfig: vi.fn().mockResolvedValue(INITIAL_CONFIG),
    updateConfig: (...args: unknown[]) => mockUpdateConfig(...args),
    listFilesystem: vi.fn().mockResolvedValue({ current: "", entries: [] }),
  },
}));

describe("SettingsView", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    INITIAL_CONFIG.llm_backend = "llama_cpp";
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces scalar edits, persists payload, and never echoes masked server_api_key", async () => {
    render(<SettingsView />);

    const portInput = screen.getByLabelText("Dashboard Web Port");
    fireEvent.change(portInput, { target: { value: "9090" } });

    await act(async () => {
      vi.advanceTimersByTime(550);
    });

    expect(mockUpdateConfig).toHaveBeenCalledTimes(1);
    const [payload] = mockUpdateConfig.mock.calls[0] as [Partial<AppConfig>];
    expect(payload).toEqual({ dashboard_port: 9090 });
    expect(payload).not.toHaveProperty("server_api_key");
  });

  it("flags invalid integer input and suppresses persistence for invalid field", async () => {
    render(<SettingsView />);

    const batchInput = screen.getByLabelText("Prompt Batch Size");
    fireEvent.change(batchInput, { target: { value: "not-a-number" } });

    await act(async () => {
      vi.advanceTimersByTime(550);
    });

    expect(mockUpdateConfig).not.toHaveBeenCalled();
    expect(batchInput.className).toContain("border-rose-500");
  });

  it("reveals server URL and masked API key inputs when switching llm_backend to server", async () => {
    render(<SettingsView />);

    expect(screen.queryByLabelText(/Local Loopback Server URL/i)).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("combobox", { name: /LLM Inference Backend/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("option", { name: /server \(Local Loopback OpenAI API\)/i }));
    });

    expect(screen.getByLabelText(/Local Loopback Server URL/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Local Server API Key/i)).toBeInTheDocument();
    expect(mockUpdateConfig).toHaveBeenCalledWith(
      { llm_backend: "server" },
      expect.any(Object),
    );
  });
});
