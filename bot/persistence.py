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


def load_from_gist(gist_id: str, github_token: str) -> list[dict]:
    resp = requests.get(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {github_token}"},
    )
    if not resp.ok:
        return []
    files = resp.json().get("files", {})
    if "analyses.json" not in files:
        return []
    raw = files["analyses.json"].get("content", "[]")
    return json.loads(raw)


def append_run(summary_dict: dict, analyses: list[dict] | None = None,
               path: str = "analyses.json") -> list[dict]:
    if analyses is None:
        analyses = load_analyses(path)
    analyses.append({**summary_dict, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")})
    save_analyses(analyses, path)
    return analyses


def push_to_gist(
    html: str,
    analyses: list[dict],
    gist_id: str,
    github_token: str,
    reviews: list[dict] | None = None,
) -> None:
    files: dict = {
        "dashboard.html": {"content": html},
        "analyses.json":  {"content": json.dumps(analyses, indent=2)},
    }
    if reviews is not None:
        files["reviews.json"] = {"content": json.dumps(reviews, indent=2)}

    requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {github_token}"},
        json={"files": files},
    ).raise_for_status()


def load_reviews_from_gist(gist_id: str, github_token: str) -> list[dict]:
    resp = requests.get(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {github_token}"},
    )
    if not resp.ok:
        return []
    files = resp.json().get("files", {})
    if "reviews.json" not in files:
        return []
    raw = files["reviews.json"].get("content", "[]")
    return json.loads(raw)
