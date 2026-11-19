import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  PenTool,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Trash2,
} from "lucide-react";
import { FileNameTruncate } from "@/components/common/FileNameTruncate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, formatSize, splitByDelimiter } from "@/lib/utils";
import type { AppConfig, InboxItem } from "@/types/api";

interface InboxCardProps {
  item: InboxItem;
  config: AppConfig | null;
  selected: boolean;
  onInspect: (path: string) => void;
  onRetry: (path: string) => void;
  onAutoAssign: (path: string) => void;
  onDelete: (item: InboxItem) => void;
}

export function InboxCard({
  item,
  config,
  selected,
  onInspect,
  onRetry,
  onAutoAssign,
  onDelete,
}: InboxCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [imgVisible, setImgVisible] = useState(false);
  const [imgError, setImgError] = useState(false);

  const isReview = Boolean(item.is_review ?? item.is_pruefen);
  const isProcessed = Boolean(item.is_processed ?? item.is_abgearbeitet);
  const reason = item.reason || item.grund || "";
  const signedVal = item.extracted?.Signed;
  const hasSignedField = signedVal !== undefined && signedVal !== null;
  const isSigned = signedVal === true || signedVal === "true" || signedVal === "Yes";

  const baseName = item.name.replace(/\.[^/.]+$/, "");
  const parts = splitByDelimiter(baseName, config?.folder_delimiter);
  const expectedParts = Array.isArray(config?.folder_structure)
    ? config.folder_structure.length
    : 4;
  const hasAllInfo = parts.length === expectedParts;

  useEffect(() => {
    if (selected && cardRef.current?.scrollIntoView) {
      cardRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selected]);

  useEffect(() => {
    if (!item.preview_url || imgVisible) return;
    const node = cardRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setImgVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setImgVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "240px 0px", threshold: 0.01 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [item.preview_url, imgVisible]);

  return (
    <div
      ref={cardRef}
      data-inbox-card={item.path}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-xl border bg-card transition-all",
        selected
          ? "border-primary ring-2 ring-primary/40 shadow-lg"
          : isReview
            ? "border-amber-500/35 hover:border-amber-400/60"
            : isProcessed
              ? "border-emerald-500/30 hover:border-emerald-400/60"
              : "border-border hover:border-primary/40",
      )}
    >
      {/* Preview thumbnail */}
      <button
        type="button"
        onClick={() => onInspect(item.path)}
        className="relative flex h-36 w-full items-center justify-center overflow-hidden border-b border-border bg-black/25 text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {item.preview_url && !imgError ? (
          imgVisible ? (
            <img
              src={item.preview_url}
              alt={`Thumbnail for ${item.name}`}
              loading="lazy"
              onError={() => setImgError(true)}
              className="h-full w-full object-cover object-top transition-transform duration-200 group-hover:scale-[1.02]"
            />
          ) : (
            <div className="h-full w-full animate-pulse bg-muted/30" />
          )
        ) : (
          <div className="flex flex-col items-center gap-1.5 text-muted-foreground">
            <FileText className="h-7 w-7 opacity-55" />
            <span className="text-[11px]">No preview</span>
          </div>
        )}

        <div className="absolute right-2 top-2">
          {isReview ? (
            <Badge variant="warning" className="bg-popover/90 backdrop-blur-xs">
              <AlertTriangle className="h-3 w-3" />
              Review
            </Badge>
          ) : isProcessed ? (
            <Badge variant="success" className="bg-popover/90 backdrop-blur-xs">
              <CheckCircle2 className="h-3 w-3" />
              Processed
            </Badge>
          ) : (
            <Badge variant="default" className="bg-popover/90 backdrop-blur-xs">
              <Clock className="h-3 w-3" />
              Processing
            </Badge>
          )}
        </div>
      </button>

      {/* Info */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <button
          type="button"
          onClick={() => onInspect(item.path)}
          className="text-left focus-visible:outline-none cursor-pointer"
        >
          <FileNameTruncate
            filename={item.name}
            className="text-xs font-semibold text-foreground group-hover:text-primary"
          />
          <div className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">
            {formatSize(item.size)} · {item.modified}
          </div>
        </button>

        {isReview && reason && (
          <div className="flex items-start gap-1.5 rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-snug text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="line-clamp-2">{reason}</span>
          </div>
        )}

        {hasSignedField && (
          <div className="flex flex-wrap gap-1.5">
            {isSigned ? (
              <Badge variant="success">
                <PenTool className="h-3 w-3" />
                Signed
              </Badge>
            ) : (
              <Badge variant="destructive">
                <ShieldAlert className="h-3 w-3" />
                Not Signed
              </Badge>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="mt-auto flex items-center justify-end gap-1.5 pt-1">
          {(isReview || isProcessed) && (
            <Button
              variant="outline"
              size="xs"
              onClick={() => onRetry(item.path)}
              title="Reprocess document"
              aria-label={`Reprocess ${item.name}`}
            >
              <RefreshCw className="h-3 w-3" />
              Retry
            </Button>
          )}
          {(isReview || isProcessed) && hasAllInfo && (
            <Button
              variant="success"
              size="xs"
              onClick={() => onAutoAssign(item.path)}
              title="Auto-assign based on filename"
            >
              <Sparkles className="h-3 w-3" />
              Assign
            </Button>
          )}
          <Button
            variant="ghost"
            size="xs"
            onClick={() => onDelete(item)}
            title="Move to recycle bin"
            aria-label={`Delete ${item.name}`}
            className="text-rose-400 hover:bg-rose-500/12 hover:text-rose-300"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
