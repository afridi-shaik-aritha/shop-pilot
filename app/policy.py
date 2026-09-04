"""Grounded store-policy service. Policy answers come only from these rules.

Policy text is data: the service returns exact rule bodies and ids so the
policy agent can quote them instead of inventing figures.
"""
import json

from pydantic import BaseModel, Field

from app.retrieval.corpus import normalize_text


class PolicyRule(BaseModel):
    policy_id: str = Field(min_length=1)
    topic: str = ""
    title: str = ""
    body: str = ""


def load_policies(path: str) -> list[PolicyRule]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [PolicyRule(**item) for item in raw]


class PolicyService:
    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = list(rules)

    def search(self, query: str | None, top_k: int = 5) -> list[dict]:
        """Top-k rules by token overlap with query + topic/title keywords."""
        q = normalize_text(query or "")
        if not q:
            return []
        scored = []
        for rule in self._rules:
            body_tokens = normalize_text(rule.body)
            meta_tokens = normalize_text(f"{rule.topic} {rule.title} {rule.policy_id}")
            hits = sum(body_tokens.count(t) for t in q) + 3 * sum(meta_tokens.count(t) for t in q)
            if hits:
                scored.append((hits, rule))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            {
                "policy_id": r.policy_id,
                "topic": r.topic,
                "title": r.title,
                "body": r.body,
                "kind": "policy-rule",
            }
            for _, r in scored[: max(top_k, 0)]
        ]
