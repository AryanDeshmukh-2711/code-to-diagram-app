"use client";

import { useRef, useState } from "react";
import { FileText, Paperclip, X } from "lucide-react";

import { classifyAttachment } from "@/lib/attachments";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export type Attachment = { kind: "pdf"; file: File } | { kind: "text"; text: string };

export type ComposerProps = {
  /** A plain chat message — a question, or an edit request. Never how a
   * project description arrives. */
  onSend: (text: string) => void;
  /** The explicit "this is my project" affordance: a PDF or pasted
   * description, chosen by the user's action, never inferred from text. */
  onAttach: (attachment: Attachment) => void;
  busy?: boolean;
};

/**
 * The composer distinguishes two things a user can do, and never blends
 * them: type a message (`onSend`), or attach a project (`onAttach`). A
 * message dropped into the wrong pipeline because its text merely looked
 * like a project description is exactly the failure this split prevents —
 * the distinction is made here, once, by which control the user touched.
 */
export function Composer({ onSend, onAttach, busy = false }: ComposerProps) {
  const [text, setText] = useState("");
  const [attachOpen, setAttachOpen] = useState(false);
  const [attachText, setAttachText] = useState("");
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFiles(files: FileList | File[]) {
    const file = files[0];
    if (!file) return;

    const result = classifyAttachment(file);
    setAttachOpen(true);
    if (!result.ok) {
      setAttachError(result.reason);
      setStagedFile(null);
      return;
    }

    setAttachError(null);
    if (result.kind === "pdf") {
      setStagedFile(file);
      setAttachText("");
    } else {
      setStagedFile(null);
      void file.text().then(setAttachText);
    }
  }

  function submitText() {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
    setText("");
  }

  function submitAttach() {
    if (stagedFile) {
      onAttach({ kind: "pdf", file: stagedFile });
    } else if (attachText.trim()) {
      onAttach({ kind: "text", text: attachText.trim() });
    } else {
      return;
    }
    setStagedFile(null);
    setAttachText("");
    setAttachError(null);
    setAttachOpen(false);
  }

  return (
    <div
      className={cn(
        "border-t border-border p-4 transition-colors",
        dragActive && "bg-accent/40",
      )}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragActive(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      {attachOpen ? (
        <div className="mb-3 space-y-3 rounded-lg border border-dashed border-border p-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">Attach your project</p>
            <button
              type="button"
              aria-label="Close attach panel"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => {
                setAttachOpen(false);
                setAttachError(null);
              }}
            >
              <X className="size-4" />
            </button>
          </div>

          {attachError ? (
            <Alert variant="destructive">
              <AlertDescription>{attachError}</AlertDescription>
            </Alert>
          ) : null}

          {stagedFile ? (
            <div className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">
              <span className="flex items-center gap-2">
                <FileText className="size-4 shrink-0" />
                {stagedFile.name}
              </span>
              <button
                type="button"
                aria-label="Remove attached file"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setStagedFile(null)}
              >
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <Textarea
              value={attachText}
              onChange={(event) => setAttachText(event.target.value)}
              placeholder="Paste your project description here, or drop a PDF anywhere in this box…"
              rows={4}
            />
          )}

          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              onClick={() => fileInputRef.current?.click()}
            >
              browse a file
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              className="hidden"
              onChange={(event) => event.target.files && handleFiles(event.target.files)}
            />
            <Button
              type="button"
              size="sm"
              onClick={submitAttach}
              disabled={!stagedFile && !attachText.trim()}
            >
              Attach project
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex items-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Attach a project description or PDF"
          onClick={() => setAttachOpen((open) => !open)}
        >
          <Paperclip className="size-4" />
        </Button>
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submitText();
            }
          }}
          placeholder="Ask a question, or tell it what to change…"
          rows={1}
          disabled={busy}
          className="min-h-9 resize-none"
        />
        <Button type="button" onClick={submitText} disabled={busy || !text.trim()}>
          Send
        </Button>
      </div>
    </div>
  );
}
