import { FileText, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getDocTypeConfig, normalizeDateForInput } from "@/lib/utils";
import type { AppConfig, DocumentTypeConfig, SplitDocumentSection } from "@/types/api";

const IGNORED_META_KEYS = new Set([
  "raw",
  "status",
  "confidence",
  "_confidence",
  "pages",
  "page_results",
  "document",
  "documenttype",
  "document_type",
  "dokument",
  "dokumentart",
  "dok_arts",
  "vision_description",
  "is_pruefen",
  "file_url",
  "preview_url",
  "images",
  "raw_images",
  "_img",
  "zeit",
  "timestamp",
  "filename",
  "dateiname",
  "grund",
  "reason",
]);

export function resolveSectionFieldKeys(
  docType: string,
  extracted: Record<string, unknown>,
  docTypes: Record<string, DocumentTypeConfig>,
  config: AppConfig | null,
): string[] {
  const docCfg = getDocTypeConfig(docType, docTypes);
  const extractionFields = docCfg?.extraction_fields;
  const isDependent = Boolean(docCfg?.dependent || docCfg?.routing?.dependent);
  const keys = new Set<string>();

  if (extractionFields && typeof extractionFields === "object") {
    for (const k of Object.keys(extractionFields)) {
      if (!IGNORED_META_KEYS.has(k.toLowerCase())) {
        keys.add(k);
      }
    }
  }

  if (isDependent) {
    const matchFolderBy = Array.isArray(config?.match_folder_by) && config.match_folder_by.length > 0
      ? config.match_folder_by
      : Array.isArray(docCfg?.routing?.match_folder_by) && docCfg.routing.match_folder_by.length > 0
        ? docCfg.routing.match_folder_by
        : ["Nachname", "Vorname", "Titel"];
    for (const k of matchFolderBy) {
      if (!IGNORED_META_KEYS.has(k.toLowerCase())) {
        keys.add(k);
      }
    }
  }

  if (keys.size === 0 && extracted && typeof extracted === "object") {
    for (const k of Object.keys(extracted)) {
      const lower = k.toLowerCase();
      if (!IGNORED_META_KEYS.has(lower) && !lower.startsWith("_")) {
        keys.add(k);
      }
    }
  }

  return Array.from(keys);
}

export function getCaseInsensitiveValue(
  obj: Record<string, unknown>,
  key: string,
): unknown {
  if (obj[key] !== undefined && obj[key] !== null) return obj[key];
  const lower = key.toLowerCase();
  const matched = Object.keys(obj).find((k) => k.toLowerCase() === lower);
  return matched ? obj[matched] : "";
}

interface SplitSectionCardProps {
  section: SplitDocumentSection;
  index: number;
  canRemove: boolean;
  docTypeOptions: string[];
  docTypes: Record<string, DocumentTypeConfig>;
  config: AppConfig | null;
  onChangeDocType: (docType: string) => void;
  onChangePages: (pages: string) => void;
  onChangeField: (key: string, value: string) => void;
  onRemove: () => void;
}

export function SplitSectionCard({
  section,
  index,
  canRemove,
  docTypeOptions,
  docTypes,
  config,
  onChangeDocType,
  onChangePages,
  onChangeField,
  onRemove,
}: SplitSectionCardProps) {
  const optionsList = docTypeOptions.includes(section.docType)
    ? docTypeOptions
    : section.docType
      ? [section.docType, ...docTypeOptions]
      : docTypeOptions;

  const fieldKeys = resolveSectionFieldKeys(
    section.docType,
    section.extracted,
    docTypes,
    config,
  );

  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-xs">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-300">
          <FileText className="h-3.5 w-3.5" />
          <span>
            Section {index + 1} ({section.docType || "Document"})
          </span>
        </div>
        {canRemove && (
          <Button
            variant="ghost"
            size="xs"
            onClick={onRemove}
            className="text-rose-400 hover:bg-rose-500/12 hover:text-rose-300"
          >
            <Trash2 className="h-3 w-3" />
            Remove
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <div className="flex flex-col gap-1">
          <Label htmlFor={`sec-type-${section.id}`}>Document Type *</Label>
          <Select value={section.docType} onValueChange={onChangeDocType}>
            <SelectTrigger id={`sec-type-${section.id}`} className="h-8 text-xs">
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              {optionsList.length > 0 ? (
                optionsList.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))
              ) : (
                <SelectItem value="Document">Document</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <Label htmlFor={`sec-pages-${section.id}`}>Pages *</Label>
          <Input
            id={`sec-pages-${section.id}`}
            value={section.pages}
            onChange={(e) => onChangePages(e.target.value)}
            placeholder="all, 1, 2-3"
            className="h-8 text-xs font-mono"
          />
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-2.5 border-t border-border/70 pt-3">
        {fieldKeys.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
            No extraction fields configured for this type.
          </div>
        ) : (
          fieldKeys.map((key) => {
            const rawVal = getCaseInsensitiveValue(section.extracted, key);
            const strVal = rawVal !== null && rawVal !== undefined ? String(rawVal) : "";
            const isDate =
              key.toLowerCase().includes("datum") || key.toLowerCase().includes("date");
            const isBool =
              typeof rawVal === "boolean" || key.toLowerCase() === "signed";
            const inputId = `sec-${section.id}-field-${key}`;

            return (
              <div key={key} className="flex flex-col gap-1">
                <Label htmlFor={inputId}>{key}</Label>
                {isDate ? (
                  (() => {
                    const iso = normalizeDateForInput(strVal);
                    if (iso !== null || !strVal) {
                      return (
                        <Input
                          id={inputId}
                          type="date"
                          value={iso ?? ""}
                          onChange={(e) => onChangeField(key, e.target.value)}
                          className="h-8 text-xs"
                        />
                      );
                    }
                    return (
                      <Input
                        id={inputId}
                        value={strVal}
                        onChange={(e) => onChangeField(key, e.target.value)}
                        title="Non-standard date format"
                        className="h-8 text-xs"
                      />
                    );
                  })()
                ) : isBool ? (
                  <Select
                    value={
                      strVal === "true" || strVal === "Yes" || rawVal === true
                        ? "true"
                        : "false"
                    }
                    onValueChange={(v) => onChangeField(key, v)}
                  >
                    <SelectTrigger id={inputId} className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true">Yes / Signed</SelectItem>
                      <SelectItem value="false">No / Not signed</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id={inputId}
                    value={strVal}
                    onChange={(e) => onChangeField(key, e.target.value)}
                    placeholder={key}
                    className="h-8 text-xs"
                  />
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
