import { useEffect } from "react";

interface ShortcutOptions {
  commandPaletteOpen: boolean;
  onToggleCommandPalette: () => void;
  inspectorOpen: boolean;
  onSubmitInspector?: () => void;
  onCloseInspector?: () => void;
  onDeleteInspector?: () => void;
  onInboxArrow?: (delta: 1 | -1) => void;
  onInboxOpenSelected?: () => void;
  onInboxDeleteSelected?: () => void;
  onInboxToggleReviewFilter?: () => void;
  activeTab: string;
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

function hasOpenModalDialog(): boolean {
  if (typeof document === "undefined") return false;
  return Boolean(document.querySelector('[role="dialog"]'));
}

export function useKeyboardShortcuts(opts: ShortcutOptions): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        opts.onToggleCommandPalette();
        return;
      }

      if (opts.commandPaletteOpen || hasOpenModalDialog()) {
        return;
      }

      const editing = isEditableElement(e.target);

      if (editing) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && opts.inspectorOpen) {
          e.preventDefault();
          opts.onSubmitInspector?.();
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          (e.target as HTMLElement).blur();
        }
        return;
      }

      if (opts.inspectorOpen) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          opts.onSubmitInspector?.();
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          opts.onCloseInspector?.();
          return;
        }
        if (
          (e.altKey || e.shiftKey) &&
          (e.key === "Delete" || e.key === "Backspace")
        ) {
          e.preventDefault();
          opts.onDeleteInspector?.();
          return;
        }
        return;
      }

      if (opts.activeTab === "inbox") {
        if (e.key === "ArrowDown" || e.key === "j" || e.key === "J") {
          e.preventDefault();
          opts.onInboxArrow?.(1);
          return;
        }
        if (e.key === "ArrowUp" || e.key === "k" || e.key === "K") {
          e.preventDefault();
          opts.onInboxArrow?.(-1);
          return;
        }
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          opts.onInboxOpenSelected?.();
          return;
        }
        if (
          e.key === "Delete" ||
          ((e.altKey || e.shiftKey) && e.key === "Backspace")
        ) {
          e.preventDefault();
          opts.onInboxDeleteSelected?.();
          return;
        }
        if ((e.key === "f" || e.key === "F") && !e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          opts.onInboxToggleReviewFilter?.();
        }
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [opts]);
}
