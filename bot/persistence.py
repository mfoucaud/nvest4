import json
import os
import requests
from datetime import datetime, timezone


def load_analyses(path: str = "analyses.json") -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save_analyses(analyses: list[dict], path: str = "analyses.json") -> None:
    with open(path, "w") as f:
        json.dump(analyses, f, indent=2)


def append_run(summary_dict: dict, path: str = "analyses.json") -> list[dict]:
    analyses = load_analyses(path)
    analyses.append({**summary_dict, "timestamp": datetime.now(timezone.utc).isoformat()})
    save_analyses(analyses, path)
    return analyses


def push_to_gist(html: str, gist_id: str, github_token: str) -> None:
    requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {github_token}"},
        json={"files": {"dashboard.html": {"content": html}}},
    ).raise_for_status()
