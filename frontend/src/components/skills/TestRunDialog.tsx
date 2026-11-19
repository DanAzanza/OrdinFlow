import { useEffect, useState } from "react";
import { CheckCircle2, FileSearch, Play, XCircle } from "lucide-react";
import { PathPickerDialog } from "@/components/settings/PathPickerDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { skillsApi } from "@/lib/api-client";
import type { SkillDefinition, TestRunResponse } from "@/types/api";

interface TestRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  skillPayload: Partial<SkillDefinition> | null;
}

export function TestRunDialog({
  open,
  onOpenChange,
  skillPayload,
}: TestRunDialogProps) {
  const [docPath, setDocPath] = useState("");
  const [folderName, setFolderName] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TestRunResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setResult(null);
      setErrorMsg(null);
    }
  }, [open]);

  const handleRun = async () => {
    if (!skillPayload || running) return;
    setRunning(true);
    setResult(null);
    setErrorMsg(null);
    try {
      const context: Record<string, unknown> = {};
      if (docPath.trim()) context.document_fullpath = docPath.trim();
      if (folderName.trim()) context.folder_name = folderName.trim();
      const res = await skillsApi.testRun(skillPayload, context);
      setResult(res);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Test execution failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Play className="h-4 w-4 text-emerald-400" />
            <span>Validate &amp; Test Run Skill</span>
          </DialogTitle>
          <DialogDescription>
            Provide optional sample context (required if this skill uses TYPE_FILE_PATH or {"{document_fullpath}"}).
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="testrun-doc-path">
              Sample Document Path (document_fullpath)
            </Label>
            <div className="flex gap-2">
              <Input
                id="testrun-doc-path"
                value={docPath}
                onChange={(e) => setDocPath(e.target.value)}
                placeholder="Optional: path to a sample PDF or image..."
                className="h-8 font-mono text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPickerOpen(true)}
              >
                <FileSearch className="h-3.5 w-3.5" />
                Browse
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="testrun-folder">
              Sample Case Folder Name (optional)
            </Label>
            <Input
              id="testrun-folder"
              value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              placeholder="Optional: e.g. Recipes__Layer Cakes"
              className="h-8 text-xs"
            />
          </div>

          {errorMsg && (
            <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold">
                  {result.success ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <XCircle className="h-4 w-4 text-rose-400" />
                  )}
                  <span>
                    {result.success ? "Test Run Passed" : "Test Run Failed"}
                  </span>
                </div>
                <Badge variant="outline" className="tabular-nums">
                  {result.duration_seconds}s · {result.total_actions ?? 0} actions
                </Badge>
              </div>

              {result.error && (
                <div className="text-xs text-rose-300">{result.error}</div>
              )}

              {Array.isArray(result.progress_log) &&
                result.progress_log.length > 0 && (
                  <div className="max-h-40 space-y-1 overflow-y-auto rounded border border-border bg-background/60 p-2 font-mono text-[11px]">
                    {result.progress_log.map((entry, idx) => (
                      <div key={idx} className="text-muted-foreground">
                        [{entry.current ?? idx + 1}/{entry.total ?? "?"}]{" "}
                        {entry.message || ""}
                      </div>
                    ))}
                  </div>
                )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="success"
            disabled={running}
            onClick={() => void handleRun()}
          >
            <Play className="h-3.5 w-3.5" />
            {running ? "Running..." : "Execute Test Run"}
          </Button>
        </DialogFooter>

        <PathPickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          title="Select Sample Document"
          pickerType="file"
          initialPath={docPath}
          onSelect={(path) => setDocPath(path)}
        />
      </DialogContent>
    </Dialog>
  );
}
