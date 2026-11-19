import { CheckCircle2, Clock, FileText, Trash2, Zap } from "lucide-react";
import { FileNameTruncate } from "@/components/common/FileNameTruncate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatSize } from "@/lib/utils";
import type { CaseFile } from "@/types/api";

interface CaseFilesGridProps {
  files: CaseFile[];
  loading: boolean;
  onInspectFile: (filename: string) => void;
  onDeleteFile: (filename: string) => void;
}

export function CaseFilesGrid({
  files,
  loading,
  onInspectFile,
  onDeleteFile,
}: CaseFilesGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-lg" />
        ))}
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="py-6 text-center text-xs text-muted-foreground">
        No documents inside this case folder.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {files.map((file) => {
        const hasExecuted =
          Array.isArray(file.executed_skills) && file.executed_skills.length > 0;

        return (
          <div
            key={file.name}
            className={cn(
              "group flex flex-col overflow-hidden rounded-lg border bg-card transition-colors",
              hasExecuted
                ? "border-emerald-500/35 hover:border-emerald-400/60"
                : "border-border hover:border-primary/40",
            )}
          >
            <button
              type="button"
              onClick={() => onInspectFile(file.name)}
              className="flex h-28 w-full items-center justify-center overflow-hidden border-b border-border bg-black/25 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {file.has_preview && file.preview_url ? (
                <img
                  src={file.preview_url}
                  alt={`Preview of ${file.name}`}
                  loading="lazy"
                  className="h-full w-full object-cover object-top transition-transform duration-200 group-hover:scale-[1.02]"
                />
              ) : (
                <FileText className="h-6 w-6 text-muted-foreground/60" />
              )}
            </button>

            <div className="flex flex-1 items-start justify-between gap-2 p-2.5">
              <button
                type="button"
                onClick={() => onInspectFile(file.name)}
                className="min-w-0 flex-1 text-left cursor-pointer focus-visible:outline-none"
              >
                <FileNameTruncate
                  filename={file.name}
                  className="text-xs font-medium text-foreground group-hover:text-primary"
                />
                <div className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">
                  {formatSize(file.size)} · {file.modified}
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  <Badge variant="default">
                    <FileText className="h-2.5 w-2.5" />
                    {file.doc_type || "Document"}
                  </Badge>
                  {hasExecuted ? (
                    file.executed_skills.map((skillId) => (
                      <Badge key={skillId} variant="success" title={`Executed by ${skillId}`}>
                        <Zap className="h-2.5 w-2.5" />
                        {skillId}
                        <CheckCircle2 className="h-2.5 w-2.5" />
                      </Badge>
                    ))
                  ) : (
                    <Badge variant="secondary">
                      <Clock className="h-2.5 w-2.5" />
                      Ready
                    </Badge>
                  )}
                </div>
              </button>

              <Button
                variant="ghost"
                size="icon"
                onClick={() => onDeleteFile(file.name)}
                aria-label={`Delete ${file.name}`}
                title="Delete file"
                className="h-7 w-7 shrink-0 text-rose-400 hover:bg-rose-500/12 hover:text-rose-300"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
