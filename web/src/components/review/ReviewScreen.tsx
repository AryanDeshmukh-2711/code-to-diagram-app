"use client";

/**
 * The CPM review screen.
 *
 * Design brief: a student with no UML training must spot and fix a wrong name
 * in under thirty seconds. Everything here follows from that.
 *
 *  - Section headings are plain English. "Things in your system", not
 *    "Entities"; "Who uses it", not "Actors". The UML term is shown once, in
 *    small grey text, so the vocabulary is learnable without being a barrier.
 *  - Names are the largest text on the page and sit in a single scannable
 *    column, because scanning names for a wrong one is the actual task.
 *  - Re-linking is a dropdown of real names, never an id typed by hand. Ids
 *    are an implementation detail and never appear.
 *  - A rename reports how many references it fixed. A cascade the user cannot
 *    see is a cascade they cannot trust, and trust is what this screen sells.
 *  - Problems are attached to the row that caused them, in the same plain
 *    English, with the fix named.
 */

import { useCallback, useEffect, useState } from "react";

import {
  applyEdit,
  confirmReview,
  type Draft,
  type Edit,
  issuesAt,
  type Issue,
  loadReview,
  ReviewRefused,
  type Review,
  seedReview,
} from "@/lib/review";

const RELATIONSHIP_WORDS: Record<string, string> = {
  association: "relates to",
  aggregation: "groups",
  composition: "is made up of",
  inheritance: "is a kind of",
  dependency: "depends on",
  realization: "implements",
};

export function ReviewScreen({ projectId }: { projectId: string }) {
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<{ version: number } | null>(null);

  useEffect(() => {
    loadReview(projectId)
      .then(setReview)
      .catch(() => seedReview(projectId, "Library Management System").then(setReview));
  }, [projectId]);

  const run = useCallback(
    async (edit: Edit) => {
      setBusy(true);
      setRefusal(null);
      try {
        setReview(await applyEdit(projectId, edit));
      } catch (error) {
        setRefusal(error instanceof ReviewRefused ? error.message : "Something went wrong.");
      } finally {
        setBusy(false);
      }
    },
    [projectId],
  );

  const confirm = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    try {
      setConfirmed(await confirmReview(projectId));
    } catch (error) {
      setRefusal(error instanceof ReviewRefused ? error.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }, [projectId]);

  if (!review) {
    return <p className="p-10 text-muted-foreground">Loading your model…</p>;
  }

  const { draft, issues } = review;

  return (
    <div className="pb-32">
      <header className="border-b border-border bg-background/95 px-6 py-6 backdrop-blur sm:px-10">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Check before generating
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{review.projectName}</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          This is what we understood from your description. Fix anything that looks wrong —
          especially names, because they appear on every diagram and in the document.
        </p>
      </header>

      {review.lastEdit ? (
        <p
          role="status"
          className="mx-6 mt-4 rounded-md border border-emerald-600/30 bg-emerald-600/10 px-4 py-2 text-sm text-emerald-900 dark:text-emerald-200 sm:mx-10"
        >
          {review.lastEdit}
          {review.referencesUpdated > 0 ? (
            <span className="font-medium">
              {" "}
              — {review.referencesUpdated} other{" "}
              {review.referencesUpdated === 1 ? "place was" : "places were"} updated to match.
            </span>
          ) : null}
        </p>
      ) : null}

      {refusal ? (
        <p
          role="alert"
          className="mx-6 mt-4 rounded-md border border-red-600/40 bg-red-600/10 px-4 py-2 text-sm text-red-900 dark:text-red-200 sm:mx-10"
        >
          {refusal}
        </p>
      ) : null}

      <div className="space-y-12 px-6 py-8 sm:px-10">
        <Section
          title="Things in your system"
          umlTerm="entities"
          blurb="Each one becomes a box on the class diagram."
          count={review.counts.entities}
          onAdd={(name) => run({ op: "add_entity", name })}
          addLabel="Add a thing"
        >
          <div className="grid gap-3 md:grid-cols-2">
            {draft.entities?.map((entity, index) => (
              <EntityCard
                key={entity.id}
                entity={entity}
                issues={issuesAt(issues, `entities[${index}]`)}
                busy={busy}
                onRename={(name) => run({ op: "rename_entity", id: entity.id, name })}
                onDelete={() => run({ op: "delete_entity", id: entity.id })}
                onAddAttribute={(attributeName) =>
                  run({
                    op: "add_attribute",
                    entityId: entity.id,
                    attributeName,
                    attributeType: "string",
                  })
                }
                onDeleteAttribute={(attributeName) =>
                  run({ op: "delete_attribute", entityId: entity.id, attributeName })
                }
              />
            ))}
          </div>
        </Section>

        <Section
          title="How they connect"
          umlTerm="relationships"
          blurb="Read each row as a sentence. If it does not read true, change it."
          count={review.counts.relationships}
        >
          <ul className="space-y-2">
            {draft.relationships?.map((relationship, index) => {
              const rowIssues = issuesAt(issues, `relationships[${index}]`);
              return (
                <li
                  key={relationship.id}
                  className={row(rowIssues.length > 0)}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <EntityPicker
                      value={relationship.from}
                      entities={draft.entities ?? []}
                      disabled={busy}
                      onChange={(fromId) =>
                        run({ op: "relink_relationship", id: relationship.id, fromId })
                      }
                    />
                    <select
                      className={select()}
                      value={relationship.type}
                      disabled={busy}
                      onChange={(event) =>
                        run({
                          op: "relink_relationship",
                          id: relationship.id,
                          type: event.target.value,
                        })
                      }
                    >
                      {Object.entries(RELATIONSHIP_WORDS).map(([value, word]) => (
                        <option key={value} value={value}>
                          {word}
                        </option>
                      ))}
                    </select>
                    <EntityPicker
                      value={relationship.to}
                      entities={draft.entities ?? []}
                      disabled={busy}
                      onChange={(toId) =>
                        run({ op: "relink_relationship", id: relationship.id, toId })
                      }
                    />
                    <button
                      type="button"
                      className={ghostButton()}
                      disabled={busy}
                      onClick={() => run({ op: "delete_relationship", id: relationship.id })}
                    >
                      Remove
                    </button>
                  </div>
                  <Problems issues={rowIssues} />
                </li>
              );
            })}
          </ul>
        </Section>

        <Section
          title="Who uses it"
          umlTerm="actors"
          blurb="The people and systems that interact with yours."
          count={review.counts.actors}
          onAdd={(name) => run({ op: "add_actor", name })}
          addLabel="Add a person"
        >
          <div className="flex flex-wrap gap-2">
            {draft.actors?.map((actor, index) => (
              <div
                key={actor.id}
                className={`${row(issuesAt(issues, `actors[${index}]`).length > 0)} flex items-center gap-2`}
              >
                <EditableName
                  value={actor.name}
                  disabled={busy}
                  onSave={(name) => run({ op: "rename_actor", id: actor.id, name })}
                  className="text-base font-medium"
                />
                <button
                  type="button"
                  className={ghostButton()}
                  disabled={busy}
                  onClick={() => run({ op: "delete_actor", id: actor.id })}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </Section>

        <Section
          title="What they do"
          umlTerm="use cases"
          blurb="Each task someone can carry out."
          count={review.counts.useCases}
        >
          <ul className="space-y-2">
            {draft.useCases?.map((useCase, index) => {
              const rowIssues = issuesAt(issues, `useCases[${index}]`);
              return (
                <li key={useCase.id} className={row(rowIssues.length > 0)}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <EditableName
                      value={useCase.name}
                      disabled={busy}
                      onSave={(name) => run({ op: "rename_use_case", id: useCase.id, name })}
                      className="text-base font-medium"
                    />
                    <div className="flex flex-wrap gap-1">
                      {(draft.actors ?? []).map((actor) => {
                        const on = (useCase.actors ?? []).includes(actor.id);
                        return (
                          <button
                            key={actor.id}
                            type="button"
                            disabled={busy}
                            aria-pressed={on}
                            className={`rounded-full border px-2.5 py-1 text-xs transition ${
                              on
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-border text-muted-foreground hover:border-foreground/40"
                            }`}
                            onClick={() =>
                              run({
                                op: "set_use_case_actors",
                                id: useCase.id,
                                actorIds: on
                                  ? (useCase.actors ?? []).filter((a) => a !== actor.id)
                                  : [...(useCase.actors ?? []), actor.id],
                              })
                            }
                          >
                            {actor.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <Problems issues={rowIssues} />
                </li>
              );
            })}
          </ul>
        </Section>
      </div>

      <ConfirmBar
        review={review}
        busy={busy}
        confirmed={confirmed}
        onConfirm={confirm}
      />
    </div>
  );
}

/* ---------------------------------------------------------------- pieces */

function row(hasProblem: boolean) {
  return `rounded-lg border px-4 py-3 ${
    hasProblem ? "border-red-500/60 bg-red-500/5" : "border-border bg-card"
  }`;
}

const select = () =>
  "rounded-md border border-border bg-background px-2 py-1 text-sm disabled:opacity-50";

const ghostButton = () =>
  "rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50";

function Section({
  title,
  umlTerm,
  blurb,
  count,
  children,
  onAdd,
  addLabel,
}: {
  title: string;
  umlTerm: string;
  blurb: string;
  count: number;
  children: React.ReactNode;
  onAdd?: (name: string) => void;
  addLabel?: string;
}) {
  const [adding, setAdding] = useState("");

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">
          {title}{" "}
          <span className="ml-1 text-sm font-normal text-muted-foreground">
            ({count}) · called {umlTerm} in UML
          </span>
        </h2>
      </div>
      <p className="mb-4 text-sm text-muted-foreground">{blurb}</p>
      {children}
      {onAdd ? (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (adding.trim()) {
              onAdd(adding.trim());
              setAdding("");
            }
          }}
        >
          <input
            value={adding}
            onChange={(event) => setAdding(event.target.value)}
            placeholder={addLabel}
            aria-label={addLabel}
            className="w-56 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
          >
            Add
          </button>
        </form>
      ) : null}
    </section>
  );
}

function EntityCard({
  entity,
  issues,
  busy,
  onRename,
  onDelete,
  onAddAttribute,
  onDeleteAttribute,
}: {
  entity: NonNullable<Draft["entities"]>[number];
  issues: Issue[];
  busy: boolean;
  onRename: (name: string) => void;
  onDelete: () => void;
  onAddAttribute: (name: string) => void;
  onDeleteAttribute: (name: string) => void;
}) {
  const [attribute, setAttribute] = useState("");

  return (
    <div className={row(issues.length > 0)}>
      <div className="flex items-start justify-between gap-2">
        <EditableName
          value={entity.name}
          disabled={busy}
          onSave={onRename}
          className="text-lg font-semibold tracking-tight"
        />
        <button type="button" className={ghostButton()} disabled={busy} onClick={onDelete}>
          Remove
        </button>
      </div>

      <ul className="mt-3 flex flex-wrap gap-1.5">
        {(entity.attributes ?? []).map((field) => (
          <li
            key={field.name}
            className="group inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground"
          >
            <span className="text-foreground">{field.name}</span>
            <span className="opacity-60">{field.type}</span>
            {field.isKey ? <span className="font-medium text-primary">key</span> : null}
            <button
              type="button"
              aria-label={`Remove ${field.name}`}
              className="opacity-0 transition group-hover:opacity-100"
              disabled={busy}
              onClick={() => onDeleteAttribute(field.name)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>

      <form
        className="mt-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (attribute.trim()) {
            onAddAttribute(attribute.trim());
            setAttribute("");
          }
        }}
      >
        <input
          value={attribute}
          onChange={(event) => setAttribute(event.target.value)}
          placeholder="add a detail…"
          aria-label={`Add a detail to ${entity.name}`}
          className="w-40 rounded-md border border-dashed border-border bg-transparent px-2 py-1 text-xs"
        />
      </form>

      <Problems issues={issues} />
    </div>
  );
}

function EditableName({
  value,
  onSave,
  disabled,
  className = "",
}: {
  value: string;
  onSave: (name: string) => void;
  disabled: boolean;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);

  useEffect(() => setText(value), [value]);

  if (!editing) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setEditing(true)}
        className={`-mx-1 rounded px-1 text-left hover:bg-muted ${className}`}
        // aria-label, not title: `title` wins the accessible-name computation,
        // which made every one of these announce as "Click to rename" with no
        // way to tell which thing was which.
        aria-label={`${value} — click to rename`}
      >
        {value}
      </button>
    );
  }

  const commit = () => {
    setEditing(false);
    if (text.trim() && text.trim() !== value) onSave(text.trim());
    else setText(value);
  };

  return (
    <input
      autoFocus
      value={text}
      aria-label={`Rename ${value}`}
      // Select the existing name on focus, the way renaming a file does.
      // Without it, fixing "Bookk" means clearing the field first — and the
      // whole target for this screen is thirty seconds.
      onFocus={(event) => event.target.select()}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") commit();
        if (event.key === "Escape") {
          setText(value);
          setEditing(false);
        }
      }}
      className={`-mx-1 w-full rounded border border-primary bg-background px-1 ${className}`}
    />
  );
}

function EntityPicker({
  value,
  entities,
  disabled,
  onChange,
}: {
  value: string;
  entities: NonNullable<Draft["entities"]>;
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  // Names, never ids. An id is an implementation detail and showing one here
  // would be the fastest way to make this feel like a JSON editor.
  return (
    <select
      className={select()}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    >
      {!entities.some((entity) => entity.id === value) ? (
        <option value={value}>⚠ {value} (missing)</option>
      ) : null}
      {entities.map((entity) => (
        <option key={entity.id} value={entity.id}>
          {entity.name}
        </option>
      ))}
    </select>
  );
}

function Problems({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1">
      {issues.map((issue) => (
        <li key={issue.path + issue.code} className="text-xs text-red-700 dark:text-red-300">
          {issue.explanation}
        </li>
      ))}
    </ul>
  );
}

function ConfirmBar({
  review,
  busy,
  confirmed,
  onConfirm,
}: {
  review: Review;
  busy: boolean;
  confirmed: { version: number } | null;
  onConfirm: () => void;
}) {
  const problems = review.issues.length;

  return (
    <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background/95 px-6 py-4 backdrop-blur sm:px-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          {confirmed ? (
            <span className="font-medium text-emerald-700 dark:text-emerald-300">
              Confirmed — saved as version {confirmed.version}. Generating your diagrams…
            </span>
          ) : problems > 0 ? (
            <span className="font-medium text-red-700 dark:text-red-300">
              {problems} thing{problems === 1 ? "" : "s"} to fix before you can generate.
            </span>
          ) : (
            <span className="text-muted-foreground">
              Looks consistent. Nothing is generated until you say so.
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy || !review.confirmable || confirmed !== null}
          className="rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition disabled:cursor-not-allowed disabled:opacity-40"
        >
          {confirmed ? "Confirmed" : "This is correct — generate"}
        </button>
      </div>
    </div>
  );
}
