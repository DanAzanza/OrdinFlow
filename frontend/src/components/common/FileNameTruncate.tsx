import { cn, splitFilenameExt } from "@/lib/utils";

interface FileNameTruncateProps {
  filename: string;
  className?: string;
}

export function FileNameTruncate({
  filename,
  className,
}: FileNameTruncateProps) {
  const { base, ext } = splitFilenameExt(filename);
  return (
    <span className={cn("filename-truncate", className)} title={filename}>
      <span className="filename-truncate-base">{base}</span>
      {ext && <span className="filename-truncate-ext">{ext}</span>}
    </span>
  );
}
