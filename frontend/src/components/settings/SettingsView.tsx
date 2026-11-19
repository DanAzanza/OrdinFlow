import { useState } from "react";
import {
  AlertCircle,
  Check,
  Cpu,
  FolderOpen,
  FolderTree,
  Loader2,
  RotateCcw,
  Settings as SettingsIcon,
} from "lucide-react";
import { PathPickerDialog } from "@/components/settings/PathPickerDialog";
import { useSettingsAutoSave } from "@/components/settings/useSettingsAutoSave";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

export function SettingsView() {
  const {
    form,
    invalidFields,
    saveStatus,
    saveError,
    loadFromServer,
    scheduleSave,
    updateField,
  } = useSettingsAutoSave();

  const [pickerState, setPickerState] = useState<{
    key: "watch_dir" | "target_base_dir" | "llm_model_path" | "mmproj_path";
    title: string;
    type: "folder" | "file";
    filter?: string;
  } | null>(null);

  if (!form) {
    return (
      <div className="py-12 text-center text-xs text-muted-foreground">
        Loading configuration...
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2.5">
          <SettingsIcon className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">
            System Setup &amp; Configuration
          </span>
          <Badge variant="outline" className="text-[11px]">
            Auto-Save
          </Badge>
        </div>

        <div className="flex items-center gap-2.5">
          {saveStatus === "saving" && (
            <Badge variant="info">
              <Loader2 className="h-3 w-3 animate-spin" />
              Saving...
            </Badge>
          )}
          {saveStatus === "saved" && (
            <Badge variant="success">
              <Check className="h-3 w-3" />
              Saved
            </Badge>
          )}
          {saveStatus === "error" && (
            <div className="flex items-center gap-1.5">
              <Badge variant="destructive" title={saveError}>
                <AlertCircle className="h-3 w-3" />
                Save failed
              </Badge>
              <Button
                variant="outline"
                size="xs"
                onClick={() => scheduleSave(true)}
              >
                Retry
              </Button>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadFromServer()}
            title="Reload saved settings from server"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset
          </Button>
        </div>
      </div>

      {/* Group 1: Folders & Paths */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-indigo-400" />
            Folders &amp; System Paths
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3.5 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_watch_dir">Central Inbox Folder</Label>
            <div className="flex gap-2">
              <Input
                id="cfg_watch_dir"
                value={form.watch_dir}
                readOnly
                onClick={() =>
                  setPickerState({
                    key: "watch_dir",
                    title: "Select Inbox Folder",
                    type: "folder",
                  })
                }
                className="cursor-pointer font-mono text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setPickerState({
                    key: "watch_dir",
                    title: "Select Inbox Folder",
                    type: "folder",
                  })
                }
              >
                Browse
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_target_base_dir">Cases Archive Folder</Label>
            <div className="flex gap-2">
              <Input
                id="cfg_target_base_dir"
                value={form.target_base_dir}
                readOnly
                onClick={() =>
                  setPickerState({
                    key: "target_base_dir",
                    title: "Select Cases Archive Folder",
                    type: "folder",
                  })
                }
                className="cursor-pointer font-mono text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setPickerState({
                    key: "target_base_dir",
                    title: "Select Cases Archive Folder",
                    type: "folder",
                  })
                }
              >
                Browse
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_dashboard_port">Dashboard Web Port</Label>
            <Input
              id="cfg_dashboard_port"
              value={form.dashboard_port}
              onChange={(e) => updateField("dashboard_port", e.target.value)}
              className={
                invalidFields.has("dashboard_port")
                  ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                  : "font-mono text-xs"
              }
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-3 py-2">
            <Label
              htmlFor="cfg_keep_inbox_files"
              className="cursor-pointer text-xs text-foreground"
            >
              Keep processed files in Inbox (.meta retention)
            </Label>
            <Switch
              id="cfg_keep_inbox_files"
              checked={form.keep_inbox_files}
              onCheckedChange={(checked) =>
                updateField("keep_inbox_files", checked, true)
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* Group 2: Archiving */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderTree className="h-4 w-4 text-emerald-400" />
            Archiving &amp; Directory Structure
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3.5 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="cfg_folder_structure">
              Subfolder Hierarchy (comma-separated tokens)
            </Label>
            <Input
              id="cfg_folder_structure"
              value={form.folder_structure}
              onChange={(e) => updateField("folder_structure", e.target.value)}
              className="font-mono text-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_folder_delimiter">Folder Delimiter</Label>
            <Input
              id="cfg_folder_delimiter"
              value={form.folder_delimiter}
              onChange={(e) => updateField("folder_delimiter", e.target.value)}
              className="font-mono text-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_match_folder_by">
              Match Existing Folders By (comma-separated)
            </Label>
            <Input
              id="cfg_match_folder_by"
              value={form.match_folder_by}
              onChange={(e) => updateField("match_folder_by", e.target.value)}
              placeholder="Nachname, Vorname"
              className="font-mono text-xs"
            />
          </div>
        </CardContent>
      </Card>

      {/* Group 3: AI Inference */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-cyan-400" />
            AI Detection &amp; Acceleration
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3.5 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_llm_backend">LLM Inference Backend</Label>
            <Select
              value={form.llm_backend}
              onValueChange={(v) => updateField("llm_backend", v, true)}
            >
              <SelectTrigger id="cfg_llm_backend" className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="llama_cpp">
                  llama_cpp (Embedded In-Process GGUF)
                </SelectItem>
                <SelectItem value="server">
                  server (Local Loopback OpenAI API)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_n_gpu_layers">
              GPU Offload Layers (-1 = all)
            </Label>
            <Input
              id="cfg_n_gpu_layers"
              value={form.n_gpu_layers}
              onChange={(e) => updateField("n_gpu_layers", e.target.value)}
              className={
                invalidFields.has("n_gpu_layers")
                  ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                  : "font-mono text-xs"
              }
            />
          </div>

          {form.llm_backend === "server" && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cfg_server_url">
                  Local Loopback Server URL (127.0.0.1 / localhost / ::1 only)
                </Label>
                <Input
                  id="cfg_server_url"
                  value={form.server_url}
                  onChange={(e) => updateField("server_url", e.target.value)}
                  placeholder="http://127.0.0.1:8081/v1"
                  className="font-mono text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cfg_server_api_key">
                  Local Server API Key (masked)
                </Label>
                <Input
                  id="cfg_server_api_key"
                  type="password"
                  value={form.server_api_key}
                  onChange={(e) =>
                    updateField("server_api_key", e.target.value)
                  }
                  placeholder="Enter new key or leave masked"
                  className="font-mono text-xs"
                />
              </div>
            </>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_llm_model_path">
              AI Vision Model Path (.gguf)
            </Label>
            <div className="flex gap-2">
              <Input
                id="cfg_llm_model_path"
                value={form.llm_model_path}
                readOnly
                onClick={() =>
                  setPickerState({
                    key: "llm_model_path",
                    title: "Select GGUF Vision Model",
                    type: "file",
                    filter: ".gguf",
                  })
                }
                className="cursor-pointer font-mono text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setPickerState({
                    key: "llm_model_path",
                    title: "Select GGUF Vision Model",
                    type: "file",
                    filter: ".gguf",
                  })
                }
              >
                Browse
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_mmproj_path">
              Vision Projector Path (.gguf)
            </Label>
            <div className="flex gap-2">
              <Input
                id="cfg_mmproj_path"
                value={form.mmproj_path}
                readOnly
                onClick={() =>
                  setPickerState({
                    key: "mmproj_path",
                    title: "Select GGUF Vision Projector",
                    type: "file",
                    filter: ".gguf",
                  })
                }
                className="cursor-pointer font-mono text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setPickerState({
                    key: "mmproj_path",
                    title: "Select GGUF Vision Projector",
                    type: "file",
                    filter: ".gguf",
                  })
                }
              >
                Browse
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_n_batch">Prompt Batch Size</Label>
            <Input
              id="cfg_n_batch"
              value={form.n_batch}
              onChange={(e) => updateField("n_batch", e.target.value)}
              className={
                invalidFields.has("n_batch")
                  ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                  : "font-mono text-xs"
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cfg_type_k">KV-Cache K (8=Q8_0, 1=F16)</Label>
              <Input
                id="cfg_type_k"
                value={form.type_k}
                onChange={(e) => updateField("type_k", e.target.value)}
                className={
                  invalidFields.has("type_k")
                    ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                    : "font-mono text-xs"
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cfg_type_v">KV-Cache V (8=Q8_0, 1=F16)</Label>
              <Input
                id="cfg_type_v"
                value={form.type_v}
                onChange={(e) => updateField("type_v", e.target.value)}
                className={
                  invalidFields.has("type_v")
                    ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                    : "font-mono text-xs"
                }
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_vision_api_timeout">AI Response Timeout (s)</Label>
            <Input
              id="cfg_vision_api_timeout"
              value={form.vision_api_timeout}
              onChange={(e) => updateField("vision_api_timeout", e.target.value)}
              className={
                invalidFields.has("vision_api_timeout")
                  ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                  : "font-mono text-xs"
              }
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg_vision_api_retries">AI Retry Attempts</Label>
            <Input
              id="cfg_vision_api_retries"
              value={form.vision_api_retries}
              onChange={(e) => updateField("vision_api_retries", e.target.value)}
              className={
                invalidFields.has("vision_api_retries")
                  ? "border-rose-500 ring-1 ring-rose-500 font-mono text-xs"
                  : "font-mono text-xs"
              }
            />
          </div>
        </CardContent>
      </Card>

      <PathPickerDialog
        open={pickerState !== null}
        onOpenChange={(open) => !open && setPickerState(null)}
        title={pickerState?.title || "Select Path"}
        pickerType={pickerState?.type || "folder"}
        fileFilter={pickerState?.filter || ""}
        initialPath={pickerState ? form[pickerState.key] : ""}
        onSelect={(chosen) => {
          if (pickerState) {
            updateField(pickerState.key, chosen, true);
          }
        }}
      />
    </div>
  );
}
