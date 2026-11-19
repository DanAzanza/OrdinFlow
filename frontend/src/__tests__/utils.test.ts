import { describe, expect, it } from "vitest";
import {
  extractFieldsFromFilenameAndFolder,
  formatDateString,
  getAvailableSkillVariables,
  isActionSensitive,
  normalizeDateForInput,
  parseDateToTimestamp,
  stripBraces,
  stripInternalActionFlags,
} from "@/lib/utils";
import type { AppConfig, SkillDefinition, SkillTask } from "@/types/api";

describe("utils", () => {
  it("normalizes ISO, German DD.MM.YYYY, and 2-digit dates while rejecting invalid dates", () => {
    expect(normalizeDateForInput("2025-03-09T14:20:00Z")).toBe("2025-03-09");
    expect(normalizeDateForInput("9.3.2025")).toBe("2025-03-09");
    expect(normalizeDateForInput("14.05.98")).toBe("1998-05-14");
    expect(normalizeDateForInput("05.01.24")).toBe("2024-01-05");
    expect(normalizeDateForInput("30.02.2025")).toBeNull();
    expect(normalizeDateForInput("")).toBeNull();
  });

  it("formats dates cleanly and parses ISO/German timestamps", () => {
    expect(formatDateString("2025-04-02")).toBe("02.04.2025");
    expect(formatDateString("–")).toBe("–");
    const tsIso = parseDateToTimestamp("2025-04-02");
    const tsDe = parseDateToTimestamp("02.04.2025");
    expect(tsIso).not.toBeNull();
    expect(tsIso).toBe(tsDe);
    expect(parseDateToTimestamp("invalid")).toBeNull();
  });

  it("extracts fields from filename templates, delimiters, and folder hierarchy", () => {
    const config = {
      watch_dir: "C:/Inbox",
      target_base_dir: "C:/Cases",
      keep_inbox_files: false,
      dashboard_port: 8080,
      folder_structure: ["{LastName}", "{FirstName}", "{BirthDate}"],
      folder_delimiter: "__",
      match_folder_by: ["LastName", "FirstName"],
      llm_backend: "llama_cpp",
      llm_model_path: "",
      mmproj_path: "",
      n_gpu_layers: -1,
      n_batch: 512,
      type_k: 8,
      type_v: 8,
      vision_api_timeout: 120,
      vision_api_retries: 3,
    } satisfies AppConfig;
    const docTypes = {
      LabReport: {
        routing: { filename_template: "{Document}_{Date}_{LabId}" },
      },
    };
    const extracted = extractFieldsFromFilenameAndFolder(
      "LabReport",
      "LabReport_2025-02-01_LAB99_2.pdf",
      "Mueller__Anna__1985-06-15",
      docTypes,
      config,
    );
    expect(extracted).toEqual({
      Document: "LabReport",
      Date: "2025-02-01",
      LabId: "LAB99",
      LastName: "Mueller",
      FirstName: "Anna",
      BirthDate: "1985-06-15",
    });
  });

  it("collects available skill variables filtered by docType", () => {
    const skills: SkillDefinition[] = [
      {
        id: "import_1",
        name: "Import",
        type: "import",
        document_types: {
          Invoice: {
            extraction_fields: { InvoiceNo: {}, Total: {} },
          },
          Referral: {
            extraction_fields: { Physician: {} },
          },
        },
      },
    ];
    const config: AppConfig = {
      watch_dir: "C:/Inbox",
      target_base_dir: "C:/Cases",
      keep_inbox_files: false,
      dashboard_port: 8080,
      folder_structure: ["{Client}", "{CaseId}"],
      folder_delimiter: "__",
      match_folder_by: [],
      llm_backend: "llama_cpp",
      llm_model_path: "",
      mmproj_path: "",
      n_gpu_layers: -1,
      n_batch: 512,
      type_k: 8,
      type_v: 8,
      vision_api_timeout: 120,
      vision_api_retries: 3,
    };

    const invoiceVars = getAvailableSkillVariables(skills, config, ["Invoice"]);
    expect(invoiceVars).toContain("{InvoiceNo}");
    expect(invoiceVars).toContain("{Total}");
    expect(invoiceVars).toContain("{Client}");
    expect(invoiceVars).not.toContain("{Physician}");
  });

  it("strips internal _editing/_revealed flags immutably and detects sensitive actions", () => {
    const tasks: SkillTask[] = [
      {
        id: "t1",
        title: "Step 1",
        actions: [
          {
            action_type: "type",
            text: "secret_value",
            _editing: true,
            _revealed: true,
          },
        ],
      },
    ];
    const cleaned = stripInternalActionFlags(tasks);
    expect(cleaned[0]?.actions?.[0]).toEqual({
      action_type: "type",
      text: "secret_value",
    });
    expect(tasks[0]?.actions?.[0]?._editing).toBe(true);

    expect(stripBraces("{LastName}")).toBe("LastName");
    expect(isActionSensitive({ action_type: "type", is_secret: true })).toBe(true);
    expect(
      isActionSensitive({ action_type: "type", description: "Enter API_KEY" }),
    ).toBe(true);
    expect(
      isActionSensitive({ action_type: "type", description: "Enter Passwort" }),
    ).toBe(true);
    expect(
      isActionSensitive({ action_type: "click", description: "Click Save" }),
    ).toBe(false);
  });
});
