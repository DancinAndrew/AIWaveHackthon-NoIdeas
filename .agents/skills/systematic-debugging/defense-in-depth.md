# Defense-in-Depth Validation

## Overview

When you fix a bug caused by invalid data, adding one check feels sufficient. But a single
check is bypassed by different code paths, refactors, or mocks.

**Core principle:** Validate at EVERY layer the data passes through. Make the bug
*structurally impossible*, not merely "fixed here."

## Why Multiple Layers

Single validation says "we fixed the bug." Multiple layers say "we made the bug impossible."
Different layers catch different cases:
- Entry validation catches most bad input.
- Business-logic checks catch edge cases that slip past entry (and mocks).
- Environment guards prevent context-specific danger (e.g. destructive ops during tests).
- Debug logging is the forensic backstop when the others miss.

## The Four Layers (Python)

### Layer 1 — Entry validation (Pydantic / Flask boundary)
Reject obviously invalid input at the API edge.
```python
from pathlib import Path
from pydantic import BaseModel, field_validator

class CreateProject(BaseModel):
    working_dir: str

    @field_validator("working_dir")
    @classmethod
    def _must_be_real_dir(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("working_dir cannot be empty")
        if not Path(v).is_dir():
            raise ValueError(f"working_dir is not a directory: {v}")
        return v
```

### Layer 2 — Business-logic validation
Ensure the data makes sense for *this* operation (catches paths that bypass Layer 1, incl.
mocks in tests).
```python
def init_workspace(project_dir: str, session_id: str) -> None:
    if not project_dir:
        raise ValueError("project_dir required for workspace init")
    ...
```

### Layer 3 — Environment guards
Refuse dangerous operations in the wrong context.
```python
import os, tempfile
from pathlib import Path

def git_init(directory: str) -> None:
    if os.environ.get("ENV") == "test":
        tmp = Path(tempfile.gettempdir()).resolve()
        if not Path(directory).resolve().is_relative_to(tmp):
            raise RuntimeError(f"refusing git init outside tmp during tests: {directory}")
    ...
```

### Layer 4 — Debug instrumentation
Capture context for forensics when everything else fails.
```python
import logging
log = logging.getLogger("debug")

def git_init(directory: str) -> None:
    log.debug("about to git init", extra={"directory": directory, "cwd": os.getcwd()})
    ...
```

## Applying the Pattern

1. **Trace the data flow** — where does the bad value originate? Where is it used?
   (See `root-cause-tracing.md`.)
2. **Map all checkpoints** — list every point the data passes through.
3. **Add validation at each layer** — entry, business, environment, debug.
4. **Test each layer** — try to bypass Layer 1, verify Layer 2 catches it; mock past Layer 2,
   verify Layer 3 holds.

## Key Insight

All four layers earn their place: different code paths bypass entry validation, mocks bypass
business logic, platform edge cases need environment guards, and debug logging is what
identifies structural misuse when the rest miss. **Don't stop at one validation point.**
