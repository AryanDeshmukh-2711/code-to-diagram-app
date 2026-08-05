"use client";

import { useState } from "react";

import type { TemplateSummary } from "@/lib/exports";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export type ExportSetupCardProps = {
  format: "pdf" | "docx";
  templates: TemplateSummary[];
  submitting?: boolean;
  submitted?: boolean;
  onSubmit: (templateId: string, fields: Record<string, string>) => void;
};

/**
 * Template choice plus that template's own required fields (FR-15), in one
 * card. The choice is skipped entirely when there is only one template
 * available — there is nothing to decide, so nothing is asked. Every label,
 * placeholder and help string here is read straight off the template's own
 * declared fields (`GET /templates`); this component writes none of its own
 * (the Watch For, verbatim). Submit stays disabled until every required
 * field of whichever template is currently selected has a non-empty value —
 * the client-side half of "export never fires until every required field is
 * supplied"; `check_fields` on the server is the other half, in case this
 * one is ever bypassed.
 *
 * Image-kind fields (currently only an optional cover logo) have no upload
 * control here — none of the built-in templates require one, so there is
 * nothing this card would ever block on by leaving them out.
 */
export function ExportSetupCard({
  format,
  templates,
  submitting = false,
  submitted = false,
  onSubmit,
}: ExportSetupCardProps) {
  const [selectedId, setSelectedId] = useState(templates[0]?.id ?? "");
  const [values, setValues] = useState<Record<string, string>>({});

  const locked = submitting || submitted;
  const template = templates.find((candidate) => candidate.id === selectedId) ?? templates[0];
  const fields = (template?.fields ?? []).filter((field) => field.kind !== "image");
  const missing = fields.filter((field) => field.required && !(values[field.key] ?? "").trim());
  const canSubmit = !locked && !!template && missing.length === 0;

  function setValue(key: string, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  if (!template) {
    return (
      <Card className="max-w-md">
        <CardContent className="pt-6 text-sm text-muted-foreground">
          No template is available.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="max-w-md">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {format.toUpperCase()} export — {template.name}
        </CardTitle>
      </CardHeader>

      {templates.length > 1 ? (
        <CardContent className="pb-3">
          <Label htmlFor="export-template" className="mb-1.5 block text-xs text-muted-foreground">
            Template
          </Label>
          <select
            id="export-template"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            value={selectedId}
            disabled={locked}
            onChange={(event) => {
              setSelectedId(event.target.value);
              setValues({});
            }}
          >
            {templates.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
          {template.description ? (
            <p className="mt-1 text-xs text-muted-foreground">{template.description}</p>
          ) : null}
        </CardContent>
      ) : template.description ? (
        <CardContent className="pb-3 text-xs text-muted-foreground">{template.description}</CardContent>
      ) : null}

      {fields.length > 0 ? (
        <CardContent className="space-y-3 pt-0">
          {fields.map((field) => (
            <div key={field.key} className="space-y-1">
              <Label htmlFor={`export-field-${field.key}`} className="text-xs">
                {field.label}
                {field.required ? " *" : ""}
              </Label>
              {field.kind === "longtext" ? (
                <Textarea
                  id={`export-field-${field.key}`}
                  value={values[field.key] ?? ""}
                  placeholder={field.placeholder}
                  disabled={locked}
                  onChange={(event) => setValue(field.key, event.target.value)}
                  rows={3}
                />
              ) : (
                <Input
                  id={`export-field-${field.key}`}
                  value={values[field.key] ?? ""}
                  placeholder={field.placeholder}
                  disabled={locked}
                  onChange={(event) => setValue(field.key, event.target.value)}
                />
              )}
              {field.help ? <p className="text-xs text-muted-foreground">{field.help}</p> : null}
            </div>
          ))}
        </CardContent>
      ) : null}

      <CardFooter>
        <Button size="sm" disabled={!canSubmit} onClick={() => onSubmit(template.id, values)}>
          {submitted ? "Export requested" : submitting ? "Starting export…" : "Export"}
        </Button>
      </CardFooter>
    </Card>
  );
}
