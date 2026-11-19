import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InboxView } from "@/components/inbox/InboxView";
import type { InboxItem } from "@/types/api";

const mockSetReviewOnly = vi.fn();
const mockSetInspectorState = vi.fn();
const mockRefreshInbox = vi.fn().mockResolvedValue(undefined);
const mockRefreshCases = vi.fn().mockResolvedValue(undefined);

const SAMPLE_INBOX: InboxItem[] = [
  {
    name: "Mueller_Anna_LabReport.pdf",
    path: "Mueller_Anna_LabReport.pdf",
    status: "review",
    file_url: "/api/file/inbox/Mueller_Anna_LabReport.pdf",
    size: 20480,
    modified: "2025-05-01 10:15",
    is_review: true,
    reason: "Missing date on page 2",
  },
  {
    name: "Schmidt__Ben__Referral.pdf",
    path: "Schmidt__Ben__Referral.pdf",
    status: "processed",
    file_url: "/api/file/inbox/Schmidt__Ben__Referral.pdf",
    size: 40960,
    modified: "2025-05-01 11:00",
    is_processed: true,
  },
];

let mockReviewOnly = false;

vi.mock("@/hooks/use-app-state", () => ({
  useAppState: () => ({
    inbox: SAMPLE_INBOX,
    config: {
      watch_dir: "C:/Inbox",
      folder_delimiter: "__",
      folder_structure: ["{LastName}", "{FirstName}", "{DocType}"],
    },
    isLoadingInitial: false,
    reviewOnly: mockReviewOnly,
    setReviewOnly: mockSetReviewOnly,
    setInspectorState: mockSetInspectorState,
    refreshInbox: mockRefreshInbox,
    refreshCases: mockRefreshCases,
  }),
}));

const mockDeleteFile = vi.fn().mockResolvedValue({ status: "ok" });
const mockAutoAssign = vi.fn().mockResolvedValue({ status: "ok" });
const mockRetry = vi.fn().mockResolvedValue({ status: "ok" });

vi.mock("@/lib/api-client", () => ({
  inboxApi: {
    deleteFile: (...args: unknown[]) => mockDeleteFile(...args),
    autoAssign: (...args: unknown[]) => mockAutoAssign(...args),
    retry: (...args: unknown[]) => mockRetry(...args),
  },
}));

describe("InboxView", () => {
  beforeEach(() => {
    mockReviewOnly = false;
    vi.clearAllMocks();
  });

  it("filters inbox files by search query and toggles Review Only filter", async () => {
    const user = userEvent.setup();
    render(
      <InboxView
        selectedIndex={0}
        onSelectIndex={vi.fn()}
        deleteTarget={null}
        onDeleteTargetChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Mueller_Anna_LabReport")).toBeInTheDocument();
    expect(screen.getByText("Schmidt__Ben__Referral")).toBeInTheDocument();

    const searchInput = screen.getByLabelText("Search documents in inbox");
    await user.type(searchInput, "Mueller");

    expect(screen.getByText("Mueller_Anna_LabReport")).toBeInTheDocument();
    expect(screen.queryByText("Schmidt__Ben__Referral")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Review Only/i }));
    expect(mockSetReviewOnly).toHaveBeenCalledTimes(1);
  });

  it("renders review-only subset when reviewOnly is enabled and opens inspector on click", async () => {
    mockReviewOnly = true;
    const user = userEvent.setup();
    const onSelectIndex = vi.fn();

    render(
      <InboxView
        selectedIndex={-1}
        onSelectIndex={onSelectIndex}
        deleteTarget={null}
        onDeleteTargetChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Mueller_Anna_LabReport")).toBeInTheDocument();
    expect(screen.queryByText("Schmidt__Ben__Referral")).not.toBeInTheDocument();

    await user.click(screen.getByText("Mueller_Anna_LabReport"));
    expect(onSelectIndex).toHaveBeenCalledWith(0);
    expect(mockSetInspectorState).toHaveBeenCalledWith({
      mode: "inbox",
      filename: "Mueller_Anna_LabReport.pdf",
    });
  });

  it("deletes inbox file through ConfirmDialog without window.confirm", async () => {
    const user = userEvent.setup();
    const onDeleteTargetChange = vi.fn();

    render(
      <InboxView
        selectedIndex={0}
        onSelectIndex={vi.fn()}
        deleteTarget={SAMPLE_INBOX[0] ?? null}
        onDeleteTargetChange={onDeleteTargetChange}
      />,
    );

    expect(screen.getByText("Move document to recycle bin?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Move to Trash" }));

    await waitFor(() => {
      expect(mockDeleteFile).toHaveBeenCalledWith("Mueller_Anna_LabReport.pdf");
    });
    expect(mockRefreshInbox).toHaveBeenCalled();
  });

  it("handles API deletion rejection without auto-closing and renders empty search state", async () => {
    const user = userEvent.setup();
    mockDeleteFile.mockRejectedValueOnce(new Error("Access denied"));
    const onDeleteTargetChange = vi.fn();

    const { rerender } = render(
      <InboxView
        selectedIndex={0}
        onSelectIndex={vi.fn()}
        deleteTarget={SAMPLE_INBOX[0] ?? null}
        onDeleteTargetChange={onDeleteTargetChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Move to Trash" }));
    await waitFor(() => {
      expect(mockDeleteFile).toHaveBeenCalledTimes(1);
    });
    expect(onDeleteTargetChange).not.toHaveBeenCalledWith(null);

    rerender(
      <InboxView
        selectedIndex={0}
        onSelectIndex={vi.fn()}
        deleteTarget={null}
        onDeleteTargetChange={onDeleteTargetChange}
      />,
    );

    await user.type(
      screen.getByLabelText("Search documents in inbox"),
      "NonExistentPatternXYZ",
    );
    expect(screen.getByText("The inbox folder is empty")).toBeInTheDocument();
  });
});
