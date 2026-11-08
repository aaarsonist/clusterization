import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai_service"))


def make_vectors(n: int, seed: int = 1) -> list[list[float]]:
    """Синтетическая выборка из четырех поведенческих групп (давность, частота, сумма)."""
    rng = np.random.default_rng(seed)
    parts = []
    for r, f, m, share in ((8, 22, 5500, 0.15), (40, 1.5, 120, 0.25), (160, 5.5, 700, 0.25), (20, 14, 600, 0.35)):
        k = int(n * share)
        parts.append(np.column_stack([
            np.abs(rng.normal(r, r * 0.4, k)),
            np.maximum(1, rng.normal(f, f * 0.25, k)).round(),
            np.abs(rng.normal(m, m * 0.3, k)),
        ]))
    return np.vstack(parts).tolist()


@pytest.fixture(scope="session")
def vectors_1500() -> list[list[float]]:
    return make_vectors(1500)


@pytest.fixture(scope="session")
def benchmark_1500(vectors_1500):
    from app.services.clustering import run_benchmark

    return run_benchmark(vectors_1500)
