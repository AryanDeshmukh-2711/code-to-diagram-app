# M0 Validation — User Interview Script

**Persona:** engineering student who must submit an SRS + fixed UML set in a university-mandated template.
**Duration:** 12 minutes.
**Core assumption under test:** *format compliance is the real pain, not diagram creation.*

---

## Rules for the interviewer

1. **Never describe the product.** Not at the start, not at the end, not "just so you know what I'm working on." If they ask, say "I'll tell you after — I don't want to bias your answers," and move on.
2. **Every question is about a specific past instance.** If they drift into "generally I would…", pull them back: *"Sorry — for the last one specifically, what happened?"*
3. **Silence is a tool.** After an answer, wait three seconds. The second thing they say is usually the true thing.
4. **Never say "would you" or "do you think."** If a question in this script starts drifting that way, it's a bug — cut it.
5. **Write down verbs, not adjectives.** "Downloaded a senior's report" is data. "It was annoying" is not.

---

## Section A — Locate the last real instance (0:00–3:00)

**1.** When was the last time you had to submit a project report or SRS? What was the project?
> *Tests: whether they are actually in the population, and whether the instance is recent enough to recall accurately.*

**2.** Walk me through everything you did, from finding out it was due to the moment you submitted. In order.
> *Tests: the real workflow end to end. Steps they'd never volunteer under abstract questioning surface here.*

**3.** **[FALSIFIER 1]** When you sat down to start — what was on your screen? A blank document, a template file, or something someone else had already made?
> *Tests: if most students start from a senior's completed report, format compliance is already solved socially, for free, and the wedge is dead.*

**4.** How did that file get to you? Walk me through it.
> *Tests: the distribution channel that already exists — and who the real incumbent is (a WhatsApp group, a drive folder, a senior).*

---

## Section B — Where the hours actually went (3:00–7:00)

**5.** Roughly how many total hours went into that submission? Break it down for me — what ate the most time?
> *Tests: self-reported effort allocation before I name any categories for them.*

**6.** **[FALSIFIER 2]** Of those hours, how many went into making the diagrams versus getting the document to look the way it had to look?
> *Tests: the assumption directly. If diagrams dominated and formatting was trivial, the wedge is inverted and the product should be a diagram tool after all.*

**7.** Which single part of it did you put off the longest?
> *Tests: procrastination is a better pain signal than stated difficulty — people delay what they dread, not what's merely slow.*

**8.** Was there any part you got someone else to do, paid for, or copied outright?
> *Tests: revealed willingness to pay, and which sub-task is already a market.*

---

## Section C — Consequences and enforcement (7:00–10:00)

**9.** **[FALSIFIER 3]** Has a submission of yours ever been returned, marked down, or rejected? What was the stated reason?
> *Tests: whether format non-compliance carries any actual penalty. If penalties are always about content or lateness and never about format, then format compliance is a fear, not a pain — and nobody pays to fix a fear that never materialises.*

**10.** How did you know the format was right before you submitted? What did you check it against?
> *Tests: whether a checkable standard exists at all, or whether "the format" is folklore passed down verbally.*

**11.** Think about the last report you submitted. How closely do you think it was actually read, and what makes you say that?
> *Tests: if the honest answer is "they checked it existed," then internal consistency and quality — the entire differentiator — are worth nothing to the buyer.*

---

## Section D — Closer (10:00–12:00)

**12.** Next time this comes up, what's the first thing you'll do differently?
> *Tests: which pain was sharp enough to change behaviour. Anything they don't mention here didn't hurt enough to matter.*

**13.** *(The question most likely to reveal I'm wrong.)* If a friend in your year messaged you tomorrow saying they were stuck on their report — what exactly would you send them?
> *Tests: the real unit of value, in the student's own currency. If the answer is "my file" or "last year's file," the product they actually want is access to a known-good artefact, not a generator — and the entire build plan is aimed at the wrong problem.*

---

## Post-interview, within 5 minutes

Write down, before you forget:

- The exact starting artefact they used (Q3) — verbatim.
- Their diagram-hours vs. format-hours split (Q6) — as numbers.
- Whether any real penalty for format has ever occurred (Q9) — yes/no.
- What they'd send a stuck friend (Q13) — verbatim.

These four fields are the dataset. Everything else is colour.

---

## How to read the results

| Signal across ≥10 of 15 interviews | Verdict |
|---|---|
| Start from a senior's file (Q3) **and** would send that file to a friend (Q13) | Wedge is wrong. The market wants a trusted artefact library, not a generator. |
| Format hours > diagram hours (Q6) **and** real penalties exist (Q9) | Core assumption holds. Build as specified. |
| Diagram hours > format hours (Q6) | Assumption inverted — but note this puts you in the commodity market the PRD §3.1 says loses. Stop and re-plan. |
| No penalty ever (Q9) **and** "nobody reads it" (Q11) | Consistency/quality differentiator is worthless to this buyer. Compete on speed only, or change persona. |
