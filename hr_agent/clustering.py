"""Deterministic complete-link clustering over normalized feature sets."""
from collections.abc import Mapping

WEIGHTS = {"hard_skills": .30, "tasks": .30, "industry": .20, "level": .10, "soft_skills": .10}


def _score(left: object, right: object) -> float:
    if isinstance(left, list) and isinstance(right, list):
        a, b = set(map(str.lower, left)), set(map(str.lower, right))
        return len(a & b) / len(a | b) if a or b else 1.0
    return float(str(left).lower() == str(right).lower())


def similarity(a: Mapping, b: Mapping, weights: Mapping[str, float] = WEIGHTS) -> float:
    if abs(sum(weights.values()) - 1) > 1e-9 or any(v < 0 for v in weights.values()):
        raise ValueError("weights must be nonnegative and total 1")
    return sum(weight * _score(a.get(key, []), b.get(key, [])) for key, weight in weights.items())


def complete_link(items: list[tuple[int, Mapping]], threshold: float = .88) -> list[list[int]]:
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    clusters: list[list[tuple[int, Mapping]]] = [[item] for item in items]
    while True:
        candidate: tuple[float, int, int] | None = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                minimum = min(similarity(a[1], b[1]) for a in clusters[i] for b in clusters[j])
                if minimum >= threshold and (candidate is None or minimum > candidate[0]):
                    candidate = (minimum, i, j)
        if candidate is None:
            break
        _, i, j = candidate
        clusters[i].extend(clusters.pop(j))
    return [[id_ for id_, _ in group] for group in clusters]
