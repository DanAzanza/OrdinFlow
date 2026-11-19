import { FileCode2, RefreshCw, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface SkillYamlEditorProps {
  yamlText: string;
  loading: boolean;
  onChangeYaml: (text: string) => void;
  onReloadFromVisual: () => void;
  onApplyAndSave: () => void;
}

export function SkillYamlEditor({
  yamlText,
  loading,
  onChangeYaml,
  onReloadFromVisual,
  onApplyAndSave,
}: SkillYamlEditorProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileCode2 className="h-4 w-4 text-cyan-400" />
          <span className="text-xs font-semibold">
            Raw Skill YAML (Expert Mode)
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={onReloadFromVisual}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Sync from Visual
          </Button>
          <Button size="sm" disabled={loading} onClick={onApplyAndSave}>
            <Save className="h-3.5 w-3.5" />
            Apply &amp; Save YAML
          </Button>
        </div>
      </div>

      <Textarea
        value={yamlText}
        onChange={(e) => onChangeYaml(e.target.value)}
        spellCheck={false}
        rows={22}
        placeholder="# Loading YAML..."
        aria-label="YAML Skill Definition"
        className="min-h-[420px] resize-y bg-zinc-950 font-mono text-xs leading-relaxed text-zinc-100"
      />
    </div>
  );
}
