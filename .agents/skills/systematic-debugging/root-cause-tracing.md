# Root Cause Tracing

## Overview

Bugs often surface deep in the call stack (a query runs against the wrong table, a file is
created in the wrong place, a connection opens with the wrong DSN). The instinct is to fix
where the error appears — but that's a symptom.

**Core principle:** Trace backward through the call chain until you find the original
trigger, then fix at the source.

## When to Use

- The error happens deep in execution, not at the entry point.
- The traceback shows a long call chain.
- It's unclear where the invalid value originated.
- You need to find which test/code path triggers the problem.

## The Tracing Process

### 1. Observe the symptom
```
asyncpg.exceptions.UndefinedTableError: relation "tenant_.items" does not exist
```

### 2. Find the immediate cause — what code directly raises this?
```python
rows = await conn.fetch(f'SELECT * FROM "tenant_{tenant}".items')
```

### 3. Ask: what called this, and what value did it pass?
```
Repo.list_items(tenant)        ← tenant = ""  (empty!)
  ← Service.list_items(tenant)
  ← route handler  items(tenant = Header(default=""))
  ← test client call with no X-Tenant header
```

### 4. Keep tracing up to the original trigger
The empty string flowed all the way down: the test never set the `X-Tenant` header, the
dependency default was `""`, and nothing rejected it. **Root cause:** missing validation on
the tenant header default — not the SQL.

### 5. Fix at the source, not the symptom
Reject the empty tenant at the boundary (and add defense-in-depth — see
`defense-in-depth.md`), rather than patching the f-string in the repository.

## Capturing a Stack When You Can't Trace Manually

When the call chain isn't obvious, capture a stack at the dangerous operation and run once:

```python
import traceback, logging
log = logging.getLogger("debug")

def git_init(directory: str) -> None:
    log.error("about to git init in %r\ncwd=%s\n%s",
              directory, os.getcwd(), "".join(traceback.format_stack()))
    subprocess.run(["git", "init"], cwd=directory, check=True)
```

In tests, prefer `logging`/`print` over a suppressed logger, and log **before** the operation
(not after it fails). Include directory, cwd, env vars, and the captured stack — then read the
stack for the test file and line number that triggered the call.

## Finding Which Test Triggers It

If the bad state appears during the suite but you do not know which test caused it, bisect
the relevant test targets with the project's normal pytest command. Do not use a cleanup
script that accepts an unchecked path; inspect and remove test artifacts explicitly.

## Key Principle

```
Found immediate cause → can trace one level up?
   yes → trace backward → is this the source?
            no  → keep tracing
            yes → fix at source + add validation at each layer (bug becomes impossible)
   no  → NEVER fix just the symptom; instrument and gather more evidence first
```

**Never fix only where the error appears.** Trace back to the original trigger.
