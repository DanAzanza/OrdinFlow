import { useEffect, useRef, useState } from "react";
import { Bot, Eraser, Send, Sparkles, User } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { skillsApi } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { CopilotMessage, SkillDefinition } from "@/types/api";

interface SkillCopilotChatProps {
  skillId: string;
  currentPayload: Partial<SkillDefinition>;
  onSkillUpdated: (updated: SkillDefinition) => void;
}

const SUGGESTION_CHIPS = [
  "Add a 500ms delay before clicking Export",
  "Type {Nachname} into the search field",
  "Bring Remote Desktop window to foreground first",
];

function nowTimeLabel(): string {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SkillCopilotChat({
  skillId,
  currentPayload,
  onSkillUpdated,
}: SkillCopilotChatProps) {
  const [historyMap, setHistoryMap] = useState<Record<string, CopilotMessage[]>>({});
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  const history = historyMap[skillId] ?? [
    {
      id: `welcome_${skillId}`,
      role: "assistant",
      content:
        "I am your local AI Copilot for this RPA skill. Describe workflow modifications in plain language (e.g., add delays, click elements, insert metadata variables).",
      time: nowTimeLabel(),
    },
  ];

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [history.length, sending]);

  const setSkillHistory = (messages: CopilotMessage[]) => {
    setHistoryMap((prev) => ({ ...prev, [skillId]: messages }));
  };

  const handleClear = () => {
    setSkillHistory([
      {
        id: `reset_${Date.now()}`,
        role: "assistant",
        content: "Chat history cleared. How should we refine this automation flow?",
        time: nowTimeLabel(),
      },
    ]);
  };

  const handleSend = async (customText?: string) => {
    const text = (customText ?? prompt).trim();
    if (!text || sending) return;

    const userMsg: CopilotMessage = {
      id: `u_${Date.now()}`,
      role: "user",
      content: text,
      time: nowTimeLabel(),
    };
    const nextHistory = [...history, userMsg];
    setSkillHistory(nextHistory);
    if (!customText) setPrompt("");
    setSending(true);

    try {
      const res = await skillsApi.aiModify(
        currentPayload,
        text,
        history.map((m) => ({ role: m.role, content: m.content })),
      );
      if (res.skill) {
        onSkillUpdated(res.skill);
        setSkillHistory([
          ...nextHistory,
          {
            id: `a_${Date.now()}`,
            role: "assistant",
            content:
              res.reply || "Updated the workflow according to your instructions.",
            time: nowTimeLabel(),
          },
        ]);
        toast.success("Skill updated by AI Copilot");
      } else {
        setSkillHistory([
          ...nextHistory,
          {
            id: `a_${Date.now()}`,
            role: "assistant",
            content: "Could not apply this modification automatically.",
            time: nowTimeLabel(),
          },
        ]);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error";
      setSkillHistory([
        ...nextHistory,
        {
          id: `err_${Date.now()}`,
          role: "assistant",
          content: `Failed to apply changes: ${msg}`,
          time: nowTimeLabel(),
        },
      ]);
      toast.error(`Copilot error: ${msg}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-[540px] flex-col overflow-hidden rounded-xl border border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-border bg-surface/80 px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div>
            <div className="text-xs font-semibold text-foreground">
              AI Skill Copilot
            </div>
            <div className="text-[11px] text-muted-foreground">
              Natural-language RPA workflow authoring
            </div>
          </div>
        </div>
        <Button variant="ghost" size="xs" onClick={handleClear}>
          <Eraser className="h-3 w-3" />
          New Chat
        </Button>
      </div>

      {/* Messages */}
      <div ref={feedRef} className="flex-1 space-y-3 overflow-y-auto p-3.5">
        {history.map((msg) => {
          const isUser = msg.role === "user";
          return (
            <div
              key={msg.id}
              className={cn(
                "flex gap-2.5",
                isUser ? "flex-row-reverse" : "flex-row",
              )}
            >
              <div
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border",
                  isUser
                    ? "border-primary/40 bg-primary/20 text-primary"
                    : "border-cyan-500/30 bg-cyan-500/15 text-cyan-400",
                )}
              >
                {isUser ? (
                  <User className="h-3 w-3" />
                ) : (
                  <Bot className="h-3 w-3" />
                )}
              </div>
              <div
                className={cn(
                  "max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed",
                  isUser
                    ? "bg-primary text-primary-foreground"
                    : "border border-border bg-surface text-foreground",
                )}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>
                <div
                  className={cn(
                    "mt-1 text-[10px]",
                    isUser ? "text-primary-foreground/75" : "text-muted-foreground",
                  )}
                >
                  {msg.time}
                </div>
              </div>
            </div>
          );
        })}

        {sending && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Bot className="h-3.5 w-3.5 animate-pulse text-cyan-400" />
            <span>Local LLM synthesizing workflow updates...</span>
          </div>
        )}
      </div>

      {/* Suggestions & Input */}
      <div className="flex flex-col gap-2 border-t border-border bg-surface/60 p-3">
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTION_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              disabled={sending}
              onClick={() => void handleSend(chip)}
              className="rounded-md border border-border bg-card px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground cursor-pointer disabled:opacity-50"
            >
              {chip}
            </button>
          ))}
        </div>

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSend();
          }}
        >
          <Input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe changes (e.g. 'Add 500ms delay before export')..."
            className="h-8 text-xs"
            disabled={sending}
          />
          <Button type="submit" size="sm" disabled={sending || !prompt.trim()}>
            <Send className="h-3.5 w-3.5" />
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
