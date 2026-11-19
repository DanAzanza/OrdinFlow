import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  getCaseInsensitiveValue,
  resolveSectionFieldKeys,
} from "@/components/inspector/SplitSectionCard";
import { useAppState } from "@/hooks/use-app-state";
import { casesApi, encodePathSegments, inboxApi } from "@/lib/api-client";
import {
  extractFieldsFromFilenameAndFolder,
  formatPageRange,
  getEffectiveDocTypes,
  splitByDelimiter,
  stripBraces,
} from "@/lib/utils";
import type { InspectorState, SplitDocumentSection } from "@/types/api";

export function useInspectorData(
  inspectorState: InspectorState,
  onClose: () => void,
) {
  const { inbox, config, skills, refreshInbox, refreshCases } = useAppState();

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [previewFileUrl, setPreviewFileUrl] = useState("");
  const [previewThumbUrl, setPreviewThumbUrl] = useState("");
  const [previewFileName, setPreviewFileName] = useState("");

  const [sections, setSections] = useState<SplitDocumentSection[]>([]);
  const [baseExtracted, setBaseExtracted] = useState<Record<string, unknown>>({});
  const [folderFields, setFolderFields] = useState<Record<string, string>>({});

  const docTypes = useMemo(
    () => getEffectiveDocTypes(skills, config),
    [skills, config],
  );
  const docTypeOptions = useMemo(() => Object.keys(docTypes).sort(), [docTypes]);

  const folderFieldKeys = useMemo(() => {
    const set = new Set<string>();
    const struct = Array.isArray(config?.folder_structure)
      ? config.folder_structure
      : [];
    const matchBy = Array.isArray(config?.match_folder_by)
      ? config.match_folder_by
      : [];
    for (const comp of struct) {
      const k = stripBraces(String(comp));
      if (k) set.add(k);
    }
    for (const f of matchBy) {
      if (f) set.add(f);
    }
    return Array.from(set);
  }, [config]);

  useEffect(() => {
    let active = true;
    setLoading(true);

    const load = async () => {
      if (inspectorState.mode === "folder_edit") {
        const folder = inspectorState.folder;
        const delimiter = config?.folder_delimiter || "--";
        const struct = Array.isArray(config?.folder_structure)
          ? config.folder_structure
          : [];
        const leaf = folder.split("/").pop() || folder;
        const parts = leaf.split(delimiter);
        const parsed: Record<string, string> = {};

        struct.forEach((comp, idx) => {
          const k = stripBraces(String(comp));
          if (k) {
            let val = (parts[idx] ?? "").trim();
            if (val === "----" || val.toUpperCase() === "MISSING") val = "";
            parsed[k] = val;
          }
        });
        for (const k of folderFieldKeys) {
          if (parsed[k] === undefined) parsed[k] = "";
        }

        let fUrl = "";
        let pUrl = "";
        let fName = folder;
        try {
          const detail = await casesApi.getDetail(folder);
          const first = detail.files?.find((f) => f.has_preview) || detail.files?.[0];
          if (first) {
            fUrl = `/api/file/cases/${encodePathSegments(folder)}/${encodeURIComponent(first.name)}`;
            pUrl =
              first.preview_url ||
              `/api/preview/Cases/${encodePathSegments(folder)}/${encodeURIComponent(first.name)}`;
            fName = first.name;
          }
        } catch {
          // Folder may contain no previewable files
        }

        if (!active) return;
        setFolderFields(parsed);
        setPreviewFileUrl(fUrl);
        setPreviewThumbUrl(pUrl);
        setPreviewFileName(fName);
        setSections([]);
        setLoading(false);
        return;
      }

      const isCases = inspectorState.mode === "cases";
      const targetFile = inspectorState.filename;
      const folder = isCases ? inspectorState.folder : "";

      let fUrl = "";
      let pUrl = "";
      let extracted: Record<string, unknown> = {};
      let hasMeta = false;

      if (isCases) {
        fUrl = `/api/file/cases/${encodePathSegments(folder)}/${encodeURIComponent(targetFile)}`;
        pUrl = `/api/preview/Cases/${encodePathSegments(folder)}/${encodeURIComponent(targetFile)}`;
        try {
          const meta = await casesApi.getFileMeta(folder, targetFile);
          if (meta.extracted && Object.keys(meta.extracted).length > 0) {
            extracted = { ...meta.extracted };
            hasMeta = true;
          }
        } catch {
          // Sidecar optional
        }
      } else {
        const inboxObj = inbox.find(
          (i) => i.path === targetFile || i.name === targetFile,
        );
        fUrl =
          inboxObj?.file_url ||
          `/api/file/inbox/${encodePathSegments(targetFile)}`;
        pUrl = inboxObj?.preview_url || fUrl;
        if (inboxObj?.extracted && Object.keys(inboxObj.extracted).length > 0) {
          extracted = { ...inboxObj.extracted };
          hasMeta = true;
        } else {
          try {
            const meta = await inboxApi.getMeta(targetFile);
            if (meta.extracted && Object.keys(meta.extracted).length > 0) {
              extracted = { ...meta.extracted };
              hasMeta = true;
            }
          } catch {
            // Sidecar optional
          }
        }
      }

      let docType = String(
        extracted.Document ||
          extracted.DocumentType ||
          splitByDelimiter(targetFile, config?.folder_delimiter)[0] ||
          "",
      );

      if (!hasMeta) {
        const parsed = extractFieldsFromFilenameAndFolder(
          docType,
          targetFile,
          folder,
          docTypes,
          config,
        );
        extracted = { ...parsed, ...extracted };
        if (!docType && parsed.Document) {
          docType = String(parsed.Document);
        }
      }

      const pageResults = Array.isArray(extracted.page_results)
        ? extracted.page_results
        : null;
      let builtSections: SplitDocumentSection[];

      if (pageResults && pageResults.length > 0) {
        builtSections = pageResults.map((pr, idx) => {
          const prType = String(
            pr.Document ||
              pr.document ||
              pr.DocumentType ||
              docType ||
              docTypeOptions[0] ||
              "Document",
          );
          return {
            id: `sec_${Date.now()}_${idx}`,
            docType: prType,
            pages: formatPageRange(
              pr.pages || (pageResults.length === 1 ? "all" : idx + 1),
            ),
            extracted: { ...extracted, ...pr },
          };
        });
      } else if (docType.includes("+") && !docTypeOptions.includes(docType)) {
        const parts = docType
          .split("+")
          .map((s) => s.trim())
          .filter(Boolean);
        builtSections =
          parts.length > 1
            ? parts.map((pt, idx) => ({
                id: `sec_${Date.now()}_${idx}`,
                docType: pt,
                pages: String(idx + 1),
                extracted: { ...extracted, Document: pt, document: pt },
              }))
            : [
                {
                  id: `sec_${Date.now()}_0`,
                  docType: docType || docTypeOptions[0] || "Document",
                  pages: "all",
                  extracted: { ...extracted },
                },
              ];
      } else {
        builtSections = [
          {
            id: `sec_${Date.now()}_0`,
            docType: docType || docTypeOptions[0] || "Document",
            pages: "all",
            extracted: { ...extracted },
          },
        ];
      }

      if (!active) return;
      setPreviewFileUrl(fUrl);
      setPreviewThumbUrl(pUrl);
      setPreviewFileName(targetFile);
      setBaseExtracted(extracted);
      setSections(builtSections);
      setLoading(false);
    };

    void load();
    return () => {
      active = false;
    };
  }, [inspectorState, config, docTypes, docTypeOptions, folderFieldKeys, inbox]);

  const handleSubmit = useCallback(async () => {
    if (submitting || loading) return;

    if (inspectorState.mode === "folder_edit") {
      setSubmitting(true);
      try {
        await casesApi.updateFolder(inspectorState.folder, folderFields);
        toast.success("Case folder updated");
        onClose();
        await refreshCases();
      } catch (e) {
        toast.error(
          `Error saving folder: ${e instanceof Error ? e.message : "Error"}`,
        );
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (sections.length === 0) return;

    const documentsPayload = sections.map((sec) => {
      const payload: Record<string, unknown> = {
        Document: sec.docType || "Document",
        document: sec.docType || "Document",
        pages: sec.pages || "all",
      };
      const keys = resolveSectionFieldKeys(
        sec.docType,
        sec.extracted,
        docTypes,
        config,
      );
      for (const k of keys) {
        const val = getCaseInsensitiveValue(sec.extracted, k);
        payload[k] = val !== undefined && val !== null ? String(val).trim() : "";
      }
      return payload;
    });

    setSubmitting(true);
    try {
      const res = await casesApi.submitSplitInspector({
        context: inspectorState.mode,
        filename: inspectorState.filename,
        folder: inspectorState.mode === "cases" ? inspectorState.folder : null,
        documents: documentsPayload,
      });
      toast.success(res.message || "Document approved and routed");
      onClose();
      await Promise.all([refreshInbox(), refreshCases()]);
    } catch (e) {
      toast.error(
        `Approval error: ${e instanceof Error ? e.message : "Error"}`,
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    submitting,
    loading,
    inspectorState,
    folderFields,
    sections,
    docTypes,
    config,
    onClose,
    refreshCases,
    refreshInbox,
  ]);

  const handleDelete = useCallback(async () => {
    setDeleting(true);
    try {
      if (inspectorState.mode === "folder_edit") {
        await casesApi.deleteFolder(inspectorState.folder);
        toast.success(`Case deleted: ${inspectorState.folder}`);
      } else if (inspectorState.mode === "cases") {
        await casesApi.deleteFile(inspectorState.folder, inspectorState.filename);
        toast.success(`Moved to trash: ${inspectorState.filename}`);
      } else {
        await inboxApi.deleteFile(inspectorState.filename);
        toast.success(`Moved to trash: ${inspectorState.filename}`);
      }
      onClose();
      await Promise.all([refreshInbox(), refreshCases()]);
    } catch (e) {
      toast.error(`Delete failed: ${e instanceof Error ? e.message : "Error"}`);
    } finally {
      setDeleting(false);
    }
  }, [inspectorState, onClose, refreshInbox, refreshCases]);

  return {
    config,
    loading,
    submitting,
    deleting,
    previewFileUrl,
    previewThumbUrl,
    previewFileName,
    sections,
    setSections,
    baseExtracted,
    folderFields,
    setFolderFields,
    folderFieldKeys,
    docTypes,
    docTypeOptions,
    handleSubmit,
    handleDelete,
  };
}
