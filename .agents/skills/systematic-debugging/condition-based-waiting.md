# Condition-Based Waiting

## Overview

Flaky tests guess at timing with arbitrary delays (`time.sleep(0.05)`). This creates race
conditions: the test passes on a fast machine but fails under CI load.

**Core principle:** Wait for the actual condition you care about, not a guess about how long
it takes.

## When to Use

- Tests have arbitrary delays (`time.sleep`, `asyncio.sleep` used as a guess).
- Tests are flaky (pass sometimes, fail under load or in parallel).
- You're waiting for an async operation, a file, or a state change to complete.

**Don't use when** you're testing actual timed behavior (debounce/throttle intervals) — and
even then, document WHY the sleep is there.

## Core Pattern

```python
# ❌ BEFORE — guessing at timing
time.sleep(0.05)
assert get_result() is not None

# ✅ AFTER — waiting for the condition
wait_for(lambda: get_result() is not None, "result ready")
assert get_result() is not None
```

## Implementation

```python
import time

def wait_for(condition, description, timeout=5.0, interval=0.01):
    """Poll until condition() is truthy; raise TimeoutError after `timeout` seconds."""
    start = time.monotonic()
    while True:
        result = condition()
        if result:
            return result
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"waiting for {description} after {timeout}s")
        time.sleep(interval)   # poll every 10ms — not every 1ms (wastes CPU)
```

For async code, keep the same loop with `await asyncio.sleep(interval)` and an async
`condition`.

## Quick Patterns

| Scenario | Pattern |
|----------|---------|
| Wait for event | `wait_for(lambda: any(e.type == "DONE" for e in events), "DONE event")` |
| Wait for state | `wait_for(lambda: machine.state == "ready", "machine ready")` |
| Wait for count | `wait_for(lambda: len(items) >= 5, "5 items")` |
| Wait for file | `wait_for(lambda: Path(p).exists(), f"{p} created")` |
| Complex | `wait_for(lambda: obj.ready and obj.value > 10, "obj ready & >10")` |

## Common Mistakes

- **Polling too fast** (`interval=0.001`) wastes CPU → poll every ~10ms.
- **No timeout** → loops forever if the condition never holds. Always include a timeout with
  a clear error message.
- **Stale data** → calling a getter once before the loop. Call it *inside* the loop for fresh
  values.

## When an Arbitrary Sleep IS Correct

```python
wait_for(lambda: tool.started, "tool started")  # 1) first wait for the triggering condition
time.sleep(0.2)  # 2) then wait for known timed behavior: 2 ticks at 100ms — documented WHY
```
Requirements: wait for the triggering condition first, base the delay on *known* timing (not
a guess), and comment the reason.
