"use client";

import { useEffect, useState } from "react";

/** A finished string, or a factory for a fresh token stream. A factory, not
 * a bare `AsyncIterable` — the iterable itself would be a generator object
 * that can only be consumed once, and Strict Mode's dev-mode double-invoke
 * of this effect (mount, clean up, mount again) would then have two
 * effect runs racing to pull from the same exhausted-after-one-read
 * generator, each stealing chunks the other was waiting for. Calling the
 * factory fresh inside the effect gives every run its own stream. */
export type NarrationSource = string | (() => AsyncIterable<string>);

/**
 * Assistant narration, rendered token-by-token when the source is a stream
 * and all at once when it isn't — the same component either way, so nothing
 * calling this has to know whether the backend behind it can stream yet.
 *
 * Cards never go through here: a card is complete the moment it renders, by
 * design (see the Watch For on this step). Only prose does.
 */
export function StreamingText({ source }: { source: NarrationSource }) {
  const [text, setText] = useState(typeof source === "string" ? source : "");

  useEffect(() => {
    if (typeof source === "string") {
      setText(source);
      return;
    }

    let cancelled = false;
    setText("");

    void (async () => {
      for await (const chunk of source()) {
        if (cancelled) return;
        setText((previous) => previous + chunk);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [source]);

  return <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>;
}
