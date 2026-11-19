import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { legalApi } from "@/lib/api-client";
import type { LegalDocName } from "@/types/api";

const LEGAL_TITLES: Record<LegalDocName, string> = {
  license: "License & Terms (GNU AGPL v3.0)",
  privacy: "Data Privacy Policy (PRIVACY_POLICY.md)",
  thirdparty: "Third-Party Open-Source Licenses",
  checklist: "Compliance Checklist (COMPLIANCE_CHECKLIST.md)",
};

interface LegalModalProps {
  docName: LegalDocName | null;
  onClose: () => void;
}

export function LegalModal({ docName, onClose }: LegalModalProps) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!docName) return;
    let active = true;
    setLoading(true);
    setError(null);
    setContent("");

    legalApi
      .getDocument(docName)
      .then((res) => {
        if (active) setContent(res.content || "No content available.");
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "Failed to load document");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [docName]);

  return (
    <Dialog open={docName !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <DialogTitle>
              {docName ? LEGAL_TITLES[docName] : "Legal & Compliance"}
            </DialogTitle>
          </div>
          <DialogDescription>
            Local on-premise compliance and open-source licensing documentation
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="h-[60vh] rounded-lg border border-border bg-background/70 p-4">
          {loading ? (
            <div className="py-12 text-center text-xs text-muted-foreground">
              Loading document...
            </div>
          ) : error ? (
            <div className="py-6 text-xs text-rose-400">
              Error loading document: {error}
            </div>
          ) : (
            <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground/90">
              {content}
            </pre>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
