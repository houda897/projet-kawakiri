from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.schema import q_ident
from core.logger import get_logger
from modeling.decision_model import DecisionModelCandidate

logger = get_logger(__name__)

class AggregationStabilityEngine:
    def __init__(self, db: clickhouse_manager):
        self.db = db
        # Marge de tolérance pour les erreurs d'arrondi des nombres à virgule flottante
        self.epsilon = 0.001 

    def check_stability(self, candidate: DecisionModelCandidate) -> list[dict]:
        """
        Vérifie que l'agrégation d'une mesure via les dimensions du modèle 
        ne provoque ni perte ni duplication de données.
        """
        reports = []

        # On parcourt toutes les relations (edges) du modèle
        for edge in candidate.edges:
            # On ne teste que les jointures entre un FAIT et une DIMENSION
            if edge.source_table not in candidate.fact_tables or edge.target_table not in candidate.dimension_tables:
                continue

            fact_table = edge.source_table
            dim_table = edge.target_table
            fk_cols = edge.source_columns
            pk_cols = edge.target_columns

            if not fk_cols or not pk_cols:
                continue

            # 1. Trouver une mesure à sommer dans la table de faits
            measure_col = self._get_best_measure(fact_table)
            if not measure_col:
                logger.debug(f"Aucune mesure numérique trouvée dans {fact_table} pour le test de stabilité.")
                continue

            fk_col = fk_cols[0]
            pk_col = pk_cols[0]

            # 2. REQUÊTE 1 : Somme brute (Grain fin absolu)
            sql_fine = f"""
            SELECT COALESCE(toFloat64(SUM({measure_col})), 0.0) 
            FROM {q_ident(CH_DB)}.{q_ident(fact_table)}
            """
            
            # 3. REQUÊTE 2 : Somme agrégée (Via la jointure vers la dimension)
            # On groupe par la clé de dimension pour simuler l'agrégation du Dashboard
            sql_agg = f"""
            SELECT COALESCE(toFloat64(SUM(agg_measure)), 0.0)
            FROM (
                SELECT SUM(F.{measure_col}) as agg_measure
                FROM {q_ident(CH_DB)}.{q_ident(fact_table)} F
                INNER JOIN {q_ident(CH_DB)}.{q_ident(dim_table)} D
                ON F.{fk_col} = D.{pk_col}
                GROUP BY D.{pk_col}
            )
            """

            # 4. Exécution et comparaison
            fine_val = self.db.query(sql_fine).result_rows[0][0]
            agg_val = self.db.query(sql_agg).result_rows[0][0]
            
            # Calcul du Delta
            delta = abs(fine_val - agg_val)
            is_stable = delta <= self.epsilon

            # Déduction de la raison si échec
            if is_stable:
                reason = "Stable"
            elif agg_val < fine_val:
                reason = "Perte de données à l'agrégation (Faits orphelins suspectés)"
            else:
                reason = "Duplication de données à l'agrégation (Dimension dé-normalisée ou produit cartésien)"

            reports.append({
                "model_id": candidate.model_id,
                "fact_table": fact_table,
                "dimension_table": dim_table,
                "measure_column": measure_col,
                "fine_grain_sum": fine_val,
                "aggregated_sum": agg_val,
                "delta": round(delta, 4),
                "is_stable": is_stable,
                "reason": reason
            })
            
        return reports

    def _get_best_measure(self, table_name: str):
        """
        Trouve la meilleure colonne numérique à utiliser comme mesure de test 
        (en excluant les clés).
        """
        sql = f"""
        SELECT column_name 
        FROM {q_ident(META_DB)}.column_stats
        WHERE database_name = %(db)s AND table_name = %(table)s
        AND column_type IN ('Int32', 'Int64', 'Float32', 'Float64', 'UInt32', 'UInt64')
        AND NOT endsWith(lower(column_name), 'id')
        AND NOT startsWith(lower(column_name), 'id_')
        AND NOT endsWith(lower(column_name), 'key')
        -- On cherche une colonne qui varie pour être une vraie mesure
        ORDER BY variation_coefficient DESC 
        LIMIT 1
        """
        rows = self.db.query(sql, parameters={"db": CH_DB, "table": table_name}).result_rows
                
        return rows[0][0] if rows else None