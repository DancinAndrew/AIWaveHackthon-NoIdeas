"""OpenPoint 生活管家 — 雙 Agent 服務媒合後端。

模組關係：
    app.py (Flask)  ->  user_agent  ->  match_client  ->  match_agent
                            |                                  |
                            +------------ repo ----------------+
                            +----------- bedrock --------------+
"""

__all__ = ["config", "domain"]
