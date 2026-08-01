---
name: adversarial-spec-review
description: Attack a written spec or OpenSpec proposal as a hostile reviewer before any code is written — hunt for ambiguity, hidden assumptions, scope creep, missing edge cases, untestable acceptance criteria, and absent rollback/observability. Outputs Must-Fix / Should-Fix / Nice-to-Have / Accepted-Risk. Use after a spec exists and before implementation, or when the user says "attack this spec" / "對抗性審查".
---

# Adversarial Spec Review — try to break the spec before code does

A spec written by the same mind that will approve it inherits all of that mind's blind
spots. This skill deliberately switches sides: the AI stops being a helpful collaborator and
becomes a **hostile reviewer whose job is to find every hole** in the spec — while fixing it
is still free, before a single line of code commits to its mistakes.

> **Distinct from `grill-me`:** grill-me runs *before* a spec exists — it collaborates,
> one question at a time, to *produce* clarity. This runs *after* a spec exists — it
> adversarially *attacks* the written artifact. grill-me builds the plan; this tries to
> break it. Use grill-me to draft, then this to red-team. They are the two ends of spec
> hardening, not substitutes.

## When to use

- After `proposal.md` / `design.md` exists, **before** implementing the tasks.
- On any spec touching auth, payments, money, or the data model — where a hole is expensive.
- When a spec "feels done" — that comfort is exactly when an adversary is most useful.
- When the user says "attack this spec", "對抗性審查", "red-team this", "poke holes".

## The stance

Read the spec assuming it is **wrong until proven otherwise**. Do not look for reasons to
approve; look for the question that, if asked in production, would have no answer. For each
section, ask "what did the author assume here that they didn't write down?"

## The attack checklist

1. **Ambiguity** — which sentences admit two readings? An implementer would have to guess.
2. **Hidden assumptions** — what decisions are implied but never stated (ordering, defaults,
   units, timezones, currency, idempotency)?
3. **Scope creep** — what's in here that isn't needed for the stated goal, and could be cut?
4. **Missing edge cases** — empty/null, concurrency, partial failure, retries, duplicate
   requests, large inputs, permission denied, network/timeout.
5. **Untestable acceptance criteria** — which "done" conditions can't be turned into a test?
   Vague success ("works well") is a defect.
6. **Underestimated difficulty** — where will implementation be harder than the spec implies?
7. **Failure & blast radius** — if this ships broken, *how would we even know*? Is there a
   log / metric / alert? Is there a rollback path? How big is the blast radius?
8. **Independent-implementability** — is this spec sufficient for a *different* engineer or
   AI agent to build the right thing with no further questions? If not, it's not done.

## Output

Sort every finding by severity so the author knows what blocks and what doesn't:

```markdown
## Adversarial Review — <spec>

### Must Fix   (the spec is wrong/dangerous/unbuildable as written — blocks implementation)
- <finding> — why it bites, and the question it leaves unanswered.

### Should Fix (a real gap, cheaper to close now than after code exists)
- ...

### Nice to Have (improvement, not a blocker)
- ...

### Accepted Risk (a hole we choose to leave open — name it so it's a decision, not an oversight)
- <risk> — why we accept it, and what would change our mind.

→ Next: revise the spec to v2, then implement. Keep this review attached to the proposal.
```

## After the review

Feed the findings **back into the spec** — don't treat the review as a side note. The
sequence is `Spec v1 → adversarial review → Spec v2 → ready to implement`. The "Accepted
Risk" list is the part people skip; writing a risk down converts a silent oversight into a
deliberate, revisitable decision.

## Anti-patterns

- **Politeness.** "This looks great, just a couple of small thoughts" is the failure mode.
  The job is to break it, not to validate it.
- **Re-running grill-me.** If there's no written spec yet, you want grill-me, not this.
- **Attacking the prose instead of the design.** Wording nits are noise; hunt for the
  unanswered question that breaks in production.
- **Findings without severity.** An unsorted wall of nitpicks buries the one Must-Fix that
  actually matters.
- **Reviewing and never revising the spec.** A review that doesn't produce a v2 was theater.
