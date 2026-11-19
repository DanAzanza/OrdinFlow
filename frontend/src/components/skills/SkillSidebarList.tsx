import { useMemo, useState } from "react";
import { Inbox, Plus, Search, Stethoscope, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { SkillDefinition } from "@/types/api";

interface SkillSidebarListProps {
  skills: SkillDefinition[];
  selectedSkillId: string | null;
  isNewCreation: boolean;
  onSelectSkill: (id: string) => void;
  onOpenCreate: () => void;
}

export function SkillSidebarList({
  skills,
  selectedSkillId,
  isNewCreation,
  onSelectSkill,
  onOpenCreate,
}: SkillSidebarListProps) {
  const [search, setSearch] = useState("");

  const filteredSkills = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter(
      (s) =>
        (s.name || "").toLowerCase().includes(q) ||
        (s.id || "").toLowerCase().includes(q) ||
        (s.description || "").toLowerCase().includes(q),
    );
  }, [skills, search]);

  return (
    <div className="flex min-h-0 flex-col gap-2.5 rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Registered Skills
        </span>
        <Button size="xs" onClick={onOpenCreate}>
          <Plus className="h-3.5 w-3.5" />
          New
        </Button>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter skills..."
          aria-label="Filter skills"
          className="h-8 pl-8 text-xs"
        />
      </div>

      <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
        {filteredSkills.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">
            {search ? "No matching skills" : "No skills configured yet"}
          </div>
        ) : (
          filteredSkills.map((s) => {
            const active = !isNewCreation && s.id === selectedSkillId;
            const isImport = s.type === "import";
            const isGdt = s.type === "gdt" || s.type === "gdt_export";
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => onSelectSkill(s.id)}
                className={cn(
                  "group flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors cursor-pointer",
                  active
                    ? "bg-primary/14 font-semibold text-foreground ring-1 ring-primary/30"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}
              >
                <div className="flex min-w-0 items-center gap-2">
                  {isImport ? (
                    <Inbox className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                  ) : isGdt ? (
                    <Stethoscope className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                  ) : (
                    <Workflow className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                  )}
                  <span className="truncate" title={s.name || s.id}>
                    {s.name || s.id}
                  </span>
                </div>
                <Badge
                  variant="outline"
                  className="px-1.5 py-0 font-mono text-[9px] uppercase"
                >
                  {isImport ? "IN" : isGdt ? "GDT" : "RPA"}
                </Badge>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
