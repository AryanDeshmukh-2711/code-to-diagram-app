"use client";

import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  LLM_KEY_REQUIRED,
  LLM_PROVIDER_LABEL,
  LLM_PROVIDER_SIGNUP_URL,
  getLlmApiKey,
  setLlmApiKey,
} from "@/lib/llmKey";

/**
 * A visitor's own LLM API key, entered once and kept in this browser only.
 * On a local self-hosted install this is optional and mostly invisible
 * (Ollama needs no key); on a hosted public demo it's required, so the
 * toggle opens by default and says so.
 */
export function LlmKeyControl() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    const existing = getLlmApiKey();
    setHasKey(Boolean(existing));
    setDraft(existing ?? "");
  }, []);

  const save = () => {
    setLlmApiKey(draft);
    setHasKey(Boolean(draft.trim()));
    setOpen(false);
  };

  const clear = () => {
    setLlmApiKey(null);
    setDraft("");
    setHasKey(false);
  };

  return (
    <div className="relative">
      <Button
        variant={hasKey ? "secondary" : LLM_KEY_REQUIRED ? "default" : "outline"}
        size="sm"
        onClick={() => setOpen((value) => !value)}
      >
        <KeyRound className="size-4" />
        {hasKey ? "API key set" : LLM_KEY_REQUIRED ? "Add API key" : "API key"}
      </Button>

      {open && (
        <div className="absolute right-0 top-full z-10 mt-2 w-80 rounded-md border border-border bg-background p-4 shadow-md">
          <div className="space-y-2">
            <Label htmlFor="llm-api-key">
              {LLM_KEY_REQUIRED ? "Your API key (required)" : "Your API key (optional)"}
            </Label>
            <Input
              id="llm-api-key"
              type="password"
              autoComplete="off"
              placeholder="sk-..."
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {LLM_KEY_REQUIRED
                ? `This demo runs on your own key so nobody else's usage is on it. Get a free key from ${LLM_PROVIDER_LABEL}`
                : `Only needed if you want to use a hosted model instead of your local Ollama. Get a key from ${LLM_PROVIDER_LABEL}`}
              {LLM_PROVIDER_SIGNUP_URL ? (
                <>
                  {" "}
                  <a
                    href={LLM_PROVIDER_SIGNUP_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    here
                  </a>
                  .
                </>
              ) : (
                "."
              )}{" "}
              Stored only in this browser; sent only with your own requests.
            </p>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            {hasKey && (
              <Button variant="ghost" size="sm" onClick={clear}>
                Clear
              </Button>
            )}
            <Button size="sm" onClick={save}>
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
