"""The classifier and the folds. numpy and scipy only: nothing here needs the encoder."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

N_COMPONENTS = 64
C = 0.1
K_NOVELTY = 10
MIN_POPULATION = 12
TOP_NEGATIVES = 200
VARIANTS = {
    "primary": {"score": True, "novelty": True, "embedding": True, "transplanted": True},
    "no_score": {"score": False, "novelty": True, "embedding": True, "transplanted": True},
    "no_novelty": {"score": True, "novelty": False, "embedding": True, "transplanted": True},
    "embedding_only": {"score": False, "novelty": False, "embedding": True, "transplanted": True},
    "no_transplanted": {"score": True, "novelty": True, "embedding": True, "transplanted": False},
}


def novelty(emb: np.ndarray, k: int = K_NOVELTY, min_population: int = MIN_POPULATION, query: np.ndarray | None = None) -> np.ndarray:
    """z-score within a strip of the mean cosine distance to the ``k`` nearest of its population ``emb``. ``query``
    rows are scored against the population and put on its scale; without it, each member against the others."""
    n_query = len(emb) if query is None else len(query)
    if len(emb) < min_population:
        return np.zeros(n_query, np.float32)

    def unit(a):
        return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)

    p = unit(emb)

    def distances(q: np.ndarray, skip_self: bool) -> np.ndarray:
        out = np.zeros(len(q), np.float32)
        for start in range(0, len(q), 256):
            d = 1.0 - q[start : start + 256] @ p.T
            d = np.sort(d, axis=1)[:, (1 if skip_self else 0) : k + (1 if skip_self else 0)]
            out[start : start + 256] = d.mean(axis=1)
        return out

    base = distances(p, True)
    mu, sd = float(base.mean()), max(float(base.std()), 1e-9)
    return (base - mu) / sd if query is None else (distances(unit(query), False) - mu) / sd


@dataclass
class Fitted:
    mean: np.ndarray | None
    components: np.ndarray | None
    scale_mean: np.ndarray
    scale_sd: np.ndarray
    coef: np.ndarray
    intercept: float
    use: dict

    def inputs(self, emb, score, nov) -> np.ndarray:
        parts = []
        if self.use["embedding"]:
            parts.append((emb - self.mean) @ self.components)
        if self.use["score"]:
            parts.append(np.asarray(score, np.float64)[:, None])
        if self.use["novelty"]:
            parts.append(np.asarray(nov, np.float64)[:, None])
        return np.concatenate(parts, axis=1)

    def decision(self, emb, score, nov) -> np.ndarray:
        z = (self.inputs(emb, score, nov) - self.scale_mean) / self.scale_sd
        return z @ self.coef + self.intercept


def principal(emb: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    mean = emb.mean(axis=0)
    x = emb - mean
    vals, vecs = np.linalg.eigh(x.T @ x)
    return mean, vecs[:, ::-1][:, : min(n, emb.shape[1])]


def logistic(x: np.ndarray, y: np.ndarray, w: np.ndarray, c: float = C) -> tuple[np.ndarray, float]:
    """Weighted L2 logistic regression, the intercept unpenalised: sum(w * loss) + |b|^2 / (2c)."""

    def f(p):
        b, a = p[:-1], p[-1]
        m = x @ b + a
        # log(1 + exp(-s m)) and its derivative, stable at both ends
        s = 2.0 * y - 1.0
        loss = np.logaddexp(0.0, -s * m)
        g = -s * w * np.exp(-np.logaddexp(0.0, s * m))
        return float((w * loss).sum() + (b @ b) / (2 * c)), np.concatenate([x.T @ g + b / c, [g.sum()]])

    r = minimize(f, np.zeros(x.shape[1] + 1), jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    return r.x[:-1], float(r.x[-1])


def fit(emb, score, nov, y, w, variant: str = "primary") -> Fitted:
    use = VARIANTS[variant]
    mean, comp = principal(emb, N_COMPONENTS) if use["embedding"] else (None, None)
    m = Fitted(mean, comp, np.zeros(1), np.ones(1), np.zeros(1), 0.0, use)
    z = m.inputs(emb, score, nov)
    m.scale_mean, m.scale_sd = z.mean(axis=0), np.maximum(z.std(axis=0), 1e-9)
    w = w * len(w) / w.sum()
    m.coef, m.intercept = logistic((z - m.scale_mean) / m.scale_sd, y, w)
    return m


def source_weights(sources: np.ndarray) -> np.ndarray:
    """The protocol's weights: positives half native, half copies; negatives a third each from list false alarms,
    shams and tile false alarms; each source's rows share its weight. A source with no rows passes its share on."""
    shares = {"pos": {"native": 1 / 2, "copy": 1 / 2}, "neg": {"list_fa": 1 / 3, "sham": 1 / 3, "tile_fa": 1 / 3}}
    w = np.zeros(len(sources), np.float64)
    for group in shares.values():
        present = {s: v for s, v in group.items() if (sources == s).any()}
        total = sum(present.values())
        for s, v in present.items():
            mask = sources == s
            w[mask] = v / total / mask.sum()
    return w


def label_tile(dets: list[dict], placements: list[dict], radii: list[float]) -> tuple[list[str], list[str], list[int | None]]:
    """For one planted tile: each detection's source and site, and each placement's best detection within its radius.
    The best detection of a real planting is a copy of that planting's site; any other detection on a real planting
    only gets scored, because it is neither a false alarm nor the copy. A detection on a sham is a tile false alarm that
    leaves with the sham's site. Everything else is a tile false alarm belonging to no site."""
    source, site = ["tile_fa"] * len(dets), [""] * len(dets)
    row = np.array([float(d["row"]) for d in dets])
    col = np.array([float(d["col"]) for d in dets])
    sc = np.array([float(d["score"]) for d in dets])
    best: list[int | None] = [None] * len(placements)
    for k in sorted(range(len(placements)), key=lambda k: bool(placements[k]["sham"])):  # real plantings claim first
        p = placements[k]
        inside = np.flatnonzero(np.hypot(row - float(p["row"]), col - float(p["col"])) <= radii[k]) if len(dets) else np.zeros(0, int)
        if len(inside):
            best[k] = int(inside[np.argmax(sc[inside])])
        for j in inside.tolist():
            if not p["sham"]:
                source[j], site[j] = "", p["site"]
            elif source[j] == "tile_fa":
                site[j] = p["site"]
        if not p["sham"] and best[k] is not None:
            source[best[k]] = "copy"
    return source, site, best


def is_positive(sources: np.ndarray) -> np.ndarray:
    return np.isin(sources, ["native", "copy"])


def training_mask(sources: np.ndarray, sites: np.ndarray, targets: np.ndarray, held_site: str, held_target: str | None, transplanted: bool = True) -> np.ndarray:
    """Rows a fold may learn from. Every row of the held-out site leaves; a planted copy or sham of that site leaves
    wherever it is planted; every row on the held-out target strip leaves; a row with source "" never trains."""
    keep = (sources != "") & (sites != held_site)
    if held_target is not None:
        keep &= targets != held_target
    if not transplanted:
        keep &= np.isin(sources, ["native", "list_fa"])
    return keep


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def auc(pos: np.ndarray, neg: np.ndarray) -> float | None:
    """Chance a random ``pos`` scores above a random ``neg``; ties count half."""
    if len(pos) == 0 or len(neg) == 0:
        return None
    neg = np.sort(neg)
    lo, hi = np.searchsorted(neg, pos, "left"), np.searchsorted(neg, pos, "right")
    return round(float((lo + 0.5 * (hi - lo)).sum() / (len(pos) * len(neg))), 3)


def paste_verdict(rows: list[dict]) -> dict:
    """``rows``: per piece, ``native`` and ``copies_median``. The protocol's test of whether the copies score clearly
    higher than the pieces they were cut from."""
    deltas = [r["copies_median"] - r["native"] for r in rows if r["copies_median"] is not None]
    if not deltas:
        return {"n": 0, "median_delta": None, "fraction_higher": None, "learning_the_paste": None}
    med = float(np.median(deltas))
    frac = float(np.mean([d > 0 for d in deltas]))
    return {"n": len(deltas), "median_delta": round(med, 3), "fraction_higher": round(frac, 3), "learning_the_paste": bool(med > 1.0 and frac >= 0.75)}
