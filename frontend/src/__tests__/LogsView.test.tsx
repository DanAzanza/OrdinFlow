import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LogsView } from "@/components/logs/LogsView";
import type { LogEntry, LogStats } from "@/types/api";

const mockClearLocalLogs = vi.fn();
const mockRefreshLogStats = vi.fn().mockResolvedValue(undefined);
const mockClearLogs = vi.fn().mockResolvedValue({ status: "ok" });

const SAMPLE_LOGS: LogEntry[] = [
  { id: 1, time: "10:00:01", level: "INFO", message: "Processed document A" },
  { id: 2, time: "10:00:02", level: "WARNING", message: "Confidence drop on field Date" },
  { id: 3, time: "10:00:03", level: "ERROR", message: "VLM timeout during Tier 3 check" },
];

const SAMPLE_STATS: LogStats = {
  recordsCount: 10,
  totalFiles: 10,
  completedFiles: 9,
  manualReviewFiles: 1,
  abortedFiles: 0,
  emptyFiles: 0,
  splitBatches: 2,
  partialDocsSaved: 11,
  directDocsMoved: 1,
  totalArchivedDocs: 12,
  successRate: "90%",
  totalProcessingTime: "24.0s",
  maxProcessingTime: "4.1s",
  avgTimePerFile: "2.4s",
  avgTimePerPage: "0.6s",
  totalPages: 40,
  categoryCounts: { LabReport: 24, Referral: 16 },
  tier1Count: 10,
  tier1DirectConsensus: 7,
  tier2Count: 3,
  tier2Resolved: 2,
  tier3Count: 1,
  tier3Resolved: 1,
  earlyStopCount: 7,
  infoCount: 25,
  warnCount: 3,
  errorCount: 1,
};

vi.mock("@/hooks/use-app-state", () => ({
  useAppState: () => ({
    logRecords: SAMPLE_LOGS,
    logStats: SAMPLE_STATS,
    clearLocalLogs: mockClearLocalLogs,
    refreshLogStats: mockRefreshLogStats,
  }),
}));

vi.mock("@/lib/api-client", () => ({
  systemApi: {
    clearLogs: (...args: unknown[]) => mockClearLogs(...args),
  },
}));

describe("LogsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders 3-Tier OCR/VLM Consensus Funnel and classified distribution", () => {
    render(<LogsView />);
    expect(screen.getByText(/3-Tier OCR \/ VLM Consensus Funnel/i)).toBeInTheDocument();
    expect(screen.getByText("7 / 10 (70%)")).toBeInTheDocument();
    expect(screen.getByText("2 resolved (20%)")).toBeInTheDocument();
    expect(screen.getByText("1 resolved (10%)")).toBeInTheDocument();
    expect(screen.getByText("LabReport")).toBeInTheDocument();
  });

  it("filters log stream by severity level and search query", async () => {
    const user = userEvent.setup();
    render(<LogsView />);

    await user.click(screen.getByRole("button", { name: "Errors" }));
    expect(screen.getByText(/VLM timeout/)).toBeInTheDocument();
    expect(screen.queryByText(/Processed document A/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "All" }));
    await user.type(screen.getByLabelText("Search system logs"), "Confidence");
    expect(screen.getByText(/Confidence drop/)).toBeInTheDocument();
    expect(screen.queryByText(/VLM timeout/)).not.toBeInTheDocument();
  });

  it("clears logs via ConfirmDialog without window.confirm", async () => {
    const user = userEvent.setup();
    render(<LogsView />);

    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("Clear system logs?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear Logs" }));

    await waitFor(() => {
      expect(mockClearLogs).toHaveBeenCalledTimes(1);
    });
    expect(mockClearLocalLogs).toHaveBeenCalled();
  });

  it("handles clearLogs API rejection and empty search filter cleanly", async () => {
    const user = userEvent.setup();
    mockClearLogs.mockRejectedValueOnce(new Error("Permission error"));

    render(<LogsView />);

    await user.click(screen.getByRole("button", { name: "Clear" }));
    await user.click(screen.getByRole("button", { name: "Clear Logs" }));

    await waitFor(() => {
      expect(mockClearLogs).toHaveBeenCalledTimes(1);
    });
    expect(mockClearLocalLogs).toHaveBeenCalled();

    await user.type(screen.getByLabelText("Search system logs"), "ZZZNoMatch");
    expect(screen.getByText("Waiting for pipeline events...")).toBeInTheDocument();
  });
});
