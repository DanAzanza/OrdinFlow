import { useEffect, useState } from "react";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { getActionStyleMeta } from "@/components/skills/SkillActionMeta";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { skillsApi } from "@/lib/api-client";
import type { SkillAction, SkillSynthesis } from "@/types/api";

interface AiSynthesisDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recordedSteps: SkillAction[];
  knownDocTypes: string[];
  defaultSkillName: string;
  onApply: (synthesis: SkillSynthesis, name: string, docType: string) => void;
}

export function AiSynthesisDialog({
  open,
  onOpenChange,
  recordedSteps,
  knownDocTypes,
  defaultSkillName,
  onApply,
}: AiSynthesisDialogProps) {
  const [loading, setLoading] = useState(false);
  const [refining, setRefining] = useState(false);
  const [synthesis, setSynthesis] = useState<SkillSynthesis | null>(null);
  const [skillName, setSkillName] = useState(defaultSkillName);
  const [selectedDocType, setSelectedDocType] = useState("*");
  const [refinePrompt, setRefinePrompt] = useState("");

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setRefinePrompt("");

    skillsApi
      .synthesize(recordedSteps, "")
      .then((res) => {
        if (!active) return;
        const syn = res.synthesis || {
          name: defaultSkillName || "New Recorded Skill",
          description: `Automated skill with ${recordedSteps.length} actions.`,
          suggested_document_types: ["*"],
          detected_variables: [],
          tasks: [
            {
              id: "task_1",
              title: "Task 1: Execute Application Flow",
              actions: recordedSteps,
            },
          ],
        };
        setSynthesis(syn);
        setSkillName(syn.name || defaultSkillName || "New Skill");
        setSelectedDocType(syn.suggested_document_types?.[0] || "*");
      })
      .catch(() => {
        if (!active) return;
        const fallback: SkillSynthesis = {
          name: defaultSkillName || "New Recorded Skill",
          description: `Automated skill (${recordedSteps.length} actions).`,
          suggested_document_types: ["*"],
          detected_variables: [],
          tasks: [
            {
              id: "task_1",
              title: "Task 1: Execute Application Flow",
              actions: recordedSteps,
            },
          ],
        };
        setSynthesis(fallback);
        setSkillName(fallback.name || "New Skill");
        setSelectedDocType("*");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [open, recordedSteps, defaultSkillName]);

  const handleRefine = async () => {
    if (!refinePrompt.trim() || refining) return;
    setRefining(true);
    try {
      const res = await skillsApi.synthesize(recordedSteps, refinePrompt.trim());
      if (res.synthesis) {
        setSynthesis(res.synthesis);
        if (res.synthesis.name) setSkillName(res.synthesis.name);
        if (res.synthesis.suggested_document_types?.[0]) {
          setSelectedDocType(res.synthesis.suggested_document_types[0]);
        }
        toast.success("Skill synthesis updated by local AI");
      }
    } catch (e) {
      toast.error(
        `Refinement failed: ${e instanceof Error ? e.message : "Error"}`,
      );
    } finally {
      setRefining(false);
    }
  };

  const tasks = synthesis?.tasks || [];
  const variables = synthesis?.detected_variables || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span>AI Skill Copilot Synthesis</span>
          </DialogTitle>
          <DialogDescription>
            Automatic task structuring and dynamic metadata variable extraction
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center gap-2.5 py-12 text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span>
              Local LLM is analyzing {recordedSteps.length} recorded actions...
            </span>
          </div>
        ) : (
          <div className="flex max-h-[65vh] flex-col gap-3.5 overflow-y-auto pr-1">
            {synthesis?.description && (
              <div className="rounded-lg border border-primary/25 bg-primary/10 px-3 py-2 text-xs text-foreground">
                {synthesis.description}
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Label>Suggested Skill Name</Label>
                <Input
                  value={skillName}
                  onChange={(e) => setSkillName(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1">
                <Label>Allowed Document Type</Label>
                <Select
                  value={selectedDocType}
                  onValueChange={setSelectedDocType}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="*">* (All Document Types)</SelectItem>
                    {knownDocTypes.map((dt) => (
                      <SelectItem key={dt} value={dt}>
                        {dt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {variables.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label>Detected Placeholders &amp; Variables</Label>
                <div className="flex flex-wrap gap-1.5">
                  {variables.map((v, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-[11px]"
                    >
                      <span className="max-w-[140px] truncate text-muted-foreground">
                        {v.original}
                      </span>
                      <ArrowRight className="h-3 w-3 text-primary" />
                      <span className="font-mono font-semibold text-cyan-400">
                        {v.variable}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <Label>Generated Tasks &amp; Actions</Label>
                <Badge variant="secondary">{tasks.length} Tasks</Badge>
              </div>
              <div className="space-y-2 rounded-lg border border-border bg-background/50 p-3">
                {tasks.map((t, idx) => (
                  <div key={t.id || idx} className="space-y-1.5">
                    <div className="text-xs font-semibold text-foreground">
                      Task {idx + 1}: {t.title}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {(t.actions || []).map((a, aIdx) => {
                        const meta = getActionStyleMeta(a.action_type);
                        const Icon = meta.icon;
                        return (
                          <Badge key={aIdx} variant="outline" className="text-[11px]">
                            <Icon className="h-3 w-3" />
                            {a.description || meta.label}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Additional AI Refinement Instructions (optional)</Label>
              <div className="flex gap-2">
                <Input
                  value={refinePrompt}
                  onChange={(e) => setRefinePrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void handleRefine();
                    }
                  }}
                  placeholder="e.g. 'Only apply to Arztbrief documents'"
                  className="h-8 text-xs"
                />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={refining || !refinePrompt.trim()}
                  onClick={() => void handleRefine()}
                >
                  {refining ? "Refining..." : "Refine"}
                </Button>
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={loading || !synthesis}
            onClick={() => {
              if (synthesis) {
                onApply(synthesis, skillName.trim() || "New Skill", selectedDocType);
                onOpenChange(false);
              }
            }}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Apply to Editor
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
