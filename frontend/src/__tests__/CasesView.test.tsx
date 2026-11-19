import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CasesView } from "@/components/cases/CasesView";
import type { CaseSummary } from "@/types/api";

const mockSetInspectorState = vi.fn();
const mockRefreshCases = vi.fn().mockResolvedValue(undefined);

const SAMPLE_CASES: CaseSummary[] = [
  {
    folder: "Zeta__Anna__1980-01-01",
    display_title: "Zeta Anna",
    person: "Zeta, Anna",
    datum: "1980-01-01",
    produkt: "LabReport",
    parts: ["Zeta", "Anna", "1980-01-01"],
    doc_types: ["LabReport"],
    file_count: 2,
    is_approved: false,
    export_status: "pending_approval",
    executed_skills: [],
    completed_applicable_tasks: 0,
    total_applicable_tasks: 1,
  },
  {
    folder: "Alpha__Ben__1992-07-12",
    display_title: "Alpha Ben",
    person: "Alpha, Ben",
    datum: "1992-07-12",
    produkt: "Referral",
    parts: ["Alpha", "Ben", "1992-07-12"],
    doc_types: ["Referral"],
    file_count: 1,
    is_approved: true,
    export_status: "completed",
    executed_skills: ["pvs_export"],
    completed_applicable_tasks: 1,
    total_applicable_tasks: 1,
  },
];

vi.mock("@/hooks/use-app-state", () => ({
  useAppState: () => ({
    cases: SAMPLE_CASES,
    config: {
      folder_structure: ["{LastName}", "{FirstName}", "{BirthDate}"],
    },
    skills: [],
    isLoadingInitial: false,
    setInspectorState: mockSetInspectorState,
    refreshCases: mockRefreshCases,
  }),
}));

const mockApprove = vi.fn().mockResolvedValue({ status: "ok", folder: "", is_approved: true });
const mockGetDetail = vi.fn().mockResolvedValue({
  folder: "Alpha__Ben__1992-07-12",
  files: [
    {
      name: "Referral_Alpha.pdf",
      size: 1024,
      modified: "2025-05-01",
      doc_type: "Referral",
      preview_url: null,
    },
  ],
});

vi.mock("@/lib/api-client", () => ({
  casesApi: {
    approve: (...args: unknown[]) => mockApprove(...args),
    getDetail: (...args: unknown[]) => mockGetDetail(...args),
    deleteFolder: vi.fn().mockResolvedValue({ status: "ok" }),
    deleteFile: vi.fn().mockResolvedValue({ status: "ok" }),
  },
}));

describe("CasesView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("toggles aria-sort when clicking sortable column headers", async () => {
    const user = userEvent.setup();
    render(<CasesView expandedFolder={null} onExpandedFolderChange={vi.fn()} />);

    const colHeader = screen.getByRole("columnheader", { name: "LastName" });
    expect(colHeader).toHaveAttribute("aria-sort", "ascending");

    await user.click(screen.getByRole("button", { name: "LastName" }));
    expect(colHeader).toHaveAttribute("aria-sort", "descending");

    const birthHeader = screen.getByRole("columnheader", { name: "BirthDate" });
    await user.click(screen.getByRole("button", { name: "BirthDate" }));
    expect(birthHeader).toHaveAttribute("aria-sort", "ascending");
  });

  it("filters cases via search input and invokes casesApi.approve", async () => {
    const user = userEvent.setup();
    render(<CasesView expandedFolder={null} onExpandedFolderChange={vi.fn()} />);

    const searchInput = screen.getByLabelText("Search archived cases");
    await user.type(searchInput, "Zeta");
    expect(screen.getByText("Zeta")).toBeInTheDocument();
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Approve/i }));
    await waitFor(() => {
      expect(mockApprove).toHaveBeenCalledWith("Zeta__Anna__1980-01-01", true);
    });
  });

  it("loads folder detail when expandedFolder prop matches a case", async () => {
    render(
      <CasesView
        expandedFolder="Alpha__Ben__1992-07-12"
        onExpandedFolderChange={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetDetail).toHaveBeenCalledWith("Alpha__Ben__1992-07-12");
    });
    expect(await screen.findByText("Referral_Alpha")).toBeInTheDocument();
  });

  it("renders empty search state and stays resilient when approve or detail API rejects", async () => {
    const user = userEvent.setup();
    mockApprove.mockRejectedValueOnce(new Error("Server unavailable"));
    mockGetDetail.mockRejectedValueOnce(new Error("Folder missing"));

    render(
      <CasesView
        expandedFolder="Zeta__Anna__1980-01-01"
        onExpandedFolderChange={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetDetail).toHaveBeenCalledWith("Zeta__Anna__1980-01-01");
    });

    await user.click(screen.getAllByRole("button", { name: /Approve/i })[0]!);
    await waitFor(() => {
      expect(mockApprove).toHaveBeenCalledTimes(1);
    });
    expect(mockRefreshCases).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Search archived cases"), "NoMatchXYZ");
    expect(screen.getByText("No archived cases found")).toBeInTheDocument();
  });
});
