import itertools
from core.logger import get_logger
from inference.primary_key import PrimaryKeyCandidate
from core.clickhouse_manager import clickhouse_manager
from collections import defaultdict

logger = get_logger(__name__)

class CompositeKeyEngine:
    def __init__(self, db: clickhouse_manager):
        self.db = db

    def _is_numeric(self, ch_type: str) -> bool:
        """Vérifie si un type ClickHouse est numérique."""
        t = ch_type.lower()
        return "int" in t or "float" in t or "decimal" in t

    def generate_composite_candidates(self, all_columns: list[PrimaryKeyCandidate], tables_without_pk: list[str], max_size: int = 3) -> list[PrimaryKeyCandidate]:
        """
        Génère en mémoire les meilleures combinaisons composites pour les tables sans PK.
        Aucune requête DB n'est effectuée ici.
        """
        composite_candidates = []

        # 🚀 OPTIMISATION : On groupe les colonnes par table en un seul passage
        columns_by_table = defaultdict(list)
        for c in all_columns:
            columns_by_table[c.table_name].append(c)

        for table in tables_without_pk:
            # Accès instantané au lieu de reparcourir toute la liste !
            table_cols = columns_by_table.get(table, [])
            
            if len(table_cols) < 2:
                continue

            # 2. On les trie par leur score individuel décroissant (les meilleurs en premier)
            table_cols.sort(key=lambda c: (c.confidence, c.uniqueness_ratio), reverse=True)

            # 3. Génération de toutes les combinaisons de taille 2 à max_size
            all_combos = []
            for size in range(2, max_size + 1):
                for combo in itertools.combinations(table_cols, size):
                    all_combos.append(list(combo))

            if not all_combos:
                continue

            # 4. Application de ta règle de choix :
            #    - Plus petite taille d'abord (minimalité)
            #    - Maximum de colonnes numériques ensuite
            all_combos.sort(key=lambda combo: (
                len(combo),
                -sum(1 for c in combo if self._is_numeric(c.column_type))
            ))

            # 5. On transforme les meilleures combinaisons en PrimaryKeyCandidate pour le pipeline
            # Ici, on prend par exemple le top 2 des meilleures combinaisons à tester pour cette table
            for best_combo in all_combos[:2]: 
                combo_names = [c.column_name for c in best_combo]
                
                # On crée un candidat composite parfaitement compatible avec ton pipeline
                composite_candidates.append(PrimaryKeyCandidate(
                    database_name=best_combo[0].database_name,
                    table_name=table,
                    column_name=", ".join(combo_names), # Stocké proprement sous forme "col1, col2"
                    column_type="Composite",
                    rows=best_combo[0].rows,
                    null_ratio=0.0,
                    uniqueness_ratio=1.0, # On suppose une unicité parfaite théorique avant le test de DF
                    entropy_ratio=sum(c.entropy_ratio for c in best_combo) / len(best_combo),
                    identifiability_score=sum(c.identifiability_score for c in best_combo) / len(best_combo),
                    confidence=sum(c.confidence for c in best_combo) / len(best_combo),
                    reason=f"Composite Candidate (Size {len(combo_names)}) from top scores"
                ))

        return composite_candidates