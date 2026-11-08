"""Валидация интеллектуального компонента на синтетических данных с известной эталонной разметкой.

Генератор данных создает четыре поведенческие группы (VIP 15 %, новички 25 %, отток 25 %, экономные 35 %);
номер клиента однозначно задает эталонную группу. Оценивается согласованность кластеров с эталоном
(ARI, NMI), однородность и полнота, детерминированность результатов и влияние числа кластеров.
"""
import json

from common import REPORTS, client, prepare_ca, run_benchmark, seed
from sklearn.metrics import adjusted_rand_score, completeness_score, homogeneity_score, normalized_mutual_info_score

SHARES = (("VIP", 0.15), ("NEWBIE", 0.25), ("CHURN", 0.25), ("BARGAIN", 0.35))
TOTAL = 1500


def truth(i: int) -> str:
    bound = 0.0
    for name, share in SHARES:
        bound += share * TOTAL
        if i <= round(bound):
            return name
    return SHARES[-1][0]


def labels(c, run_id: int, algorithm: str) -> dict[int, int]:
    points = c.get(f"/api/v1/segmentation/runs/{run_id}/points?algorithm={algorithm}").json()["points"]
    return {p["client_id"]: p["cluster_no"] for p in points}


def evaluate(c, detail: dict) -> dict:
    result = {}
    for model in detail["metrics"]["models"]:
        pred = labels(c, detail["id"], model["algorithm_id"])
        ids = sorted(pred)
        y_true = [truth(i) for i in ids]
        y_pred = [pred[i] for i in ids]
        contingency: dict[str, dict[str, int]] = {}
        names = {cl["cluster_no"]: cl["cluster_label"] for cl in model["clusters"]}
        for t, p in zip(y_true, y_pred, strict=True):
            row = contingency.setdefault(t, {})
            row[names[p]] = row.get(names[p], 0) + 1
        result[model["algorithm_id"]] = {
            "k": model["cluster_count"], "silhouette": model["silhouette_score"], "davies_bouldin": model["davies_bouldin_score"],
            "noise": model["noise_percent"], "ARI": round(adjusted_rand_score(y_true, y_pred), 4),
            "NMI": round(normalized_mutual_info_score(y_true, y_pred), 4),
            "homogeneity": round(homogeneity_score(y_true, y_pred), 4), "completeness": round(completeness_score(y_true, y_pred), 4),
            "contingency": contingency,
        }
    return result


def main() -> None:
    prepare_ca()
    seed(TOTAL)
    c = client("marketer", "Marketer#2026")
    report = {}
    auto, _ = run_benchmark(c)
    report["auto"] = {"elbow": auto["xai"]["elbow_curve"], "optimal_k": auto["xai"]["optimal_k"],
                      "eps": auto["xai"]["selected_eps"], "explained_variance": auto["xai"]["explained_variance_ratio"],
                      "winner": auto["xai"]["winner"], "models": evaluate(c, auto),
                      "profiles": next(m for m in auto["metrics"]["models"] if m["algorithm_id"] == "kmeans")["clusters"]}
    repeat, _ = run_benchmark(c)
    report["deterministic"] = labels(c, auto["id"], "kmeans") == labels(c, repeat["id"], "kmeans")
    forced, _ = run_benchmark(c, target_k=4)
    report["k4"] = {"models": evaluate(c, forced),
                    "profiles": next(m for m in forced["metrics"]["models"] if m["algorithm_id"] == "kmeans")["clusters"]}
    periods = {}
    for days in (90, 180):
        d, _ = run_benchmark(c, days=days)
        km = next(m for m in d["metrics"]["models"] if m["algorithm_id"] == "kmeans")
        periods[days] = {"k": km["cluster_count"], "silhouette": km["silhouette_score"], "davies_bouldin": km["davies_bouldin_score"]}
    report["periods"] = periods
    (REPORTS / "ml_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for key in ("auto", "k4"):
        for alg, v in report[key]["models"].items():
            print(key, alg, {k: v[k] for k in ("k", "silhouette", "davies_bouldin", "noise", "ARI", "NMI", "homogeneity", "completeness")})
    print("deterministic:", report["deterministic"], "periods:", periods)


if __name__ == "__main__":
    main()
