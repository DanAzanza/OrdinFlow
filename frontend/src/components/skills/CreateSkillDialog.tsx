import { useState } from "react";
import { Inbox, Stethoscope, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { SkillKind } from "@/types/api";

interface CreateSkillDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (kind: SkillKind, copyDefaultDocTypes: boolean) => void;
}

const OPTIONS: Array<{
  kind: SkillKind;
  title: string;
  desc: string;
  icon: typeof Workflow;
}> = [
  {
    kind: "export",
    title: "Export Skill (GUI / Agentic RPA)",
    desc: "Automate clicks, keystrokes, and file transfers into desktop or RDP software with Set-of-Mark grounding.",
    icon: Workflow,
  },
  {
    kind: "import",
    title: "Import Skill (Inbox & AI Classification)",
    desc: "Configure document formats, PDF splitting rules, document categories, and Vision-LLM extraction schemas.",
    icon: Inbox,
  },
  {
    kind: "gdt",
    title: "GDT 2.1 PVS Export (Satzart 6310)",
    desc: "Write atomic CP437 / ISO-8859-1 medical findings directly into German Practice Management Systems.",
    icon: Stethoscope,
  },
];

export function CreateSkillDialog({
  open,
  onOpenChange,
  onCreate,
}: CreateSkillDialogProps) {
  const [selectedKind, setSelectedKind] = useState<SkillKind>("export");
  const [copyDefaults, setCopyDefaults] = useState(true);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create New Skill</DialogTitle>
          <DialogDescription>
            Choose the automation or extraction pipeline type you want to configure.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2.5">
          {OPTIONS.map((opt) => {
            const Icon = opt.icon;
            const active = selectedKind === opt.kind;
            return (
              <button
                key={opt.kind}
                type="button"
                onClick={() => setSelectedKind(opt.kind)}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors cursor-pointer",
                  active
                    ? "border-primary bg-primary/10 ring-1 ring-primary/40"
                    : "border-border bg-card/50 hover:border-primary/40",
                )}
              >
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-foreground">
                    {opt.title}
                  </div>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                    {opt.desc}
                  </p>
                </div>
              </button>
            );
          })}

          {selectedKind === "import" && (
            <label className="mt-1 flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface/60 px-3 py-2.5 text-xs">
              <Checkbox
                checked={copyDefaults}
                onCheckedChange={(chk) => setCopyDefaults(Boolean(chk))}
              />
              Copy existing document types &amp; extraction fields as starting template
            </label>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onCreate(selectedKind, copyDefaults);
              onOpenChange(false);
            }}
          >
            Create Skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
