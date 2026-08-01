"""Flask entrypoint for local development and AWS Lambda packaging.

The earlier dual-agent prototype remains under ``op_agent/`` as reference
code. The executable application now uses the versioned water-repair walking
skeleton contract shared with the React frontend and future AgentCore tools.
"""

from __future__ import annotations

import os

from walking_skeleton.api import create_app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=False)
