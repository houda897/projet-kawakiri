from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class DimensionCandidate:
    table: str
    key_columns: tuple[str, ...]
    attribute_columns: tuple[str, ...]
    confidence: float
    reason: str

# Une clé dimensionnelle doit être unique, informative et suffisamment complète.
def _is_strong_key(stat: dict, threshold: float) -> bool:
    return (
        stat["entropy_ratio"] >= threshold
        and stat["uniqueness_ratio"] >= threshold
        and stat["completeness_ratio"] >= threshold
    )



def _is_measure_like_type(ch_type: str) -> bool:
    lowered = ch_type.lower()
    return lowered.startswith(("int", "uint", "float", "decimal", "bool", "nullable(int", "nullable(uint", "nullable(float", "nullable(decimal"))


def infer_dimension_candidates(
    table: str,
    column_stats: list[dict],
    key_threshold: float = 0.95,
) -> list[dict]:
    if not column_stats:
        return []

    strong_keys = [stat for stat in column_stats if _is_strong_key(stat, key_threshold)]
    if not strong_keys:
        return []

    strong_keys = sorted(
        strong_keys,
        key=lambda item: (item["uniqueness_ratio"], item["entropy_ratio"], item["non_null_rows"]),
        reverse=True,
    )

    best_key = strong_keys[0]
    strong_key_names = {best_key["column"]}

    attribute_columns = []
    for stat in column_stats:
        if stat["column"] in strong_key_names:
            continue
        if _is_measure_like_type(stat["ch_type"]):
            continue
        attribute_columns.append(stat["column"])

    confidence = round(
        min(1.0, 0.85 * ((best_key["uniqueness_ratio"] + best_key["entropy_ratio"]) / 2) + 0.15 * min(1.0, len(attribute_columns) / max(1, len(column_stats) - 1))),
        4,
    )

    reason = (
        f"key={best_key['column']} strong entropy+uniqueness; "
        f"{len(attribute_columns)} stable attributes grouped"
    )

    candidate = DimensionCandidate(
        table=table,
        key_columns=tuple(stat["column"] for stat in strong_keys[:1]),
        attribute_columns=tuple(attribute_columns),
        confidence=confidence,
        reason=reason,
    )

    return [asdict(candidate)]
'''Ce qu’elle fait exactement:

elle cherche d’abord les colonnes qui sont des clés fortes,
elle garde la plus forte comme noyau de dimension,
elle prend ensuite les autres colonnes non-mesure comme attributs,
elle calcule une confiance globale,
elle renvoie une liste de dictionnaires prêts à être consommés par le pipeline.
Pourquoi je l’ai conçue comme ça:

elle reste conservatrice, donc elle évite de classer trop vite une table de faits comme dimension,
elle ne recalcule pas l’entropie, elle consomme ce qui existe déjà,
elle produit une sortie simple, stable, et importable.
J’ai ajouté un score de confiance pour éviter un simple verdict binaire. Il combine:
la force de la clé,
la présence d’attributs stables dans la table.'''