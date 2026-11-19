import { useState } from "react";
import { ExternalLink, FileWarning } from "lucide-react";
import { cn, isPdfUrl } from "@/lib/utils";

interface DocumentPreviewProps {
  fileUrl?: string;
  previewUrl?: string;
  fileName: string;
  className?: string;
  pointerEventsDisabled?: boolean;
}

export function DocumentPreview({
  fileUrl,
  previewUrl,
  fileName,
  className,
  pointerEventsDisabled = false,
}: DocumentPreviewProps) {
  const [imgError, setImgError] = useState(false);
  const targetUrl = fileUrl || previewUrl || "";

  if (!targetUrl) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 text-xs text-muted-foreground">
        No preview available
      </div>
    );
  }

  const showPdf = isPdfUrl(fileName) || isPdfUrl(targetUrl);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border bg-black/30",
        className,
      )}
    >
      <a
        href={targetUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="absolute right-2 top-2 z-10 inline-flex items-center gap-1 rounded-md border border-border bg-popover/90 px-2 py-1 text-[11px] font-medium text-foreground shadow-sm backdrop-blur-xs transition-colors hover:bg-accent"
        title="Open full document in new window"
      >
        <ExternalLink className="h-3 w-3" />
        Open
      </a>

      {showPdf ? (
        <iframe
          src={`${targetUrl}#toolbar=0&navpanes=0&view=FitH`}
          title={`Preview of ${fileName}`}
          loading="lazy"
          className={cn(
            "h-[360px] w-full border-0 bg-zinc-900",
            pointerEventsDisabled && "pointer-events-none",
          )}
        />
      ) : imgError ? (
        <div className="flex h-48 flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
          <FileWarning className="h-5 w-5 text-amber-400" />
          <span>Preview unavailable</span>
        </div>
      ) : (
        <img
          src={previewUrl || targetUrl}
          alt={`Preview of ${fileName}`}
          loading="lazy"
          onError={() => setImgError(true)}
          className="max-h-[360px] w-full object-contain bg-zinc-950/60"
        />
      )}
    </div>
  );
}
