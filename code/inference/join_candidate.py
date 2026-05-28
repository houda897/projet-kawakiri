from __future__ import annotations
from datetime import datetime

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident

from inference.primary_key import PrimaryKeyCandidate
from colorama import init, Fore, Style

logger = get_logger(__name__)


@dataclass
class JoinPrimaryKeyCandidate:
    """
    Empirical relationship between a source column and a primary-key candidate.

    The success ratio measures the fraction of non-null source rows whose value
    is present in the target key domain.
    """

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    source_non_null_rows: int
    matched_rows: int
    join_success_ratio: float


@dataclass
class SourceColumn:
    """Profiled column that can be evaluated as a possible foreign key."""

    table_name: str
    column_name: str
    column_type: str


class JoinEngine:
    """
    Evaluate physical joins between profiled columns and primary-key candidates.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def _to_q_ident_list(self, columns_str: str) -> str:
        return ", ".join(q_ident(c.strip()) for c in columns_str.split(","))

    def _to_is_not_null_cond(self, columns_str: str) -> str:
        return " AND ".join(f"{q_ident(c.strip())} IS NOT NULL" for c in columns_str.split(","))

    def evaluate_join_to_primary_key(
        self,
        source_table: str,
        source_column: str,
        primary_key: PrimaryKeyCandidate,
        limit_rows: int | None = None,
    ) -> JoinPrimaryKeyCandidate:
        """
        Measure whether a source column is covered by a primary-key candidate.
        """

        source_ref = f"{q_ident(CH_DB)}.{q_ident(source_table)}"
        target_ref = f"{q_ident(CH_DB)}.{q_ident(primary_key.table_name)}"

        source_cols = self._to_q_ident_list(source_column)
        target_cols = self._to_q_ident_list(primary_key.column_name)

        source_not_null = self._to_is_not_null_cond(source_column)
        target_not_null = self._to_is_not_null_cond(primary_key.column_name)

        limit_clause = f"LIMIT {limit_rows}" if limit_rows is not None else ""

        sql = f"""
        WITH
            source_values AS (
                SELECT tuple({source_cols}) AS value
                FROM {source_ref}
                WHERE {source_not_null}
                {limit_clause}
            ),
            target_values AS (
                SELECT DISTINCT tuple({target_cols}) AS value
                FROM {target_ref}
                WHERE {target_not_null}
            )
        SELECT
            count() AS source_non_null_rows,
            countIf(t.value IS NOT NULL) AS matched_rows,
            if(
                source_non_null_rows = 0,
                0.0,
                matched_rows / toFloat64(source_non_null_rows)
            ) AS join_success_ratio
        FROM source_values AS s
        LEFT JOIN target_values AS t
            ON s.value = t.value
        """

        row = self.db.query(sql).result_rows[0]

        return JoinPrimaryKeyCandidate(
            source_table=source_table,
            source_column=source_column,
            target_table=primary_key.table_name,
            target_column=primary_key.column_name,
            source_non_null_rows=row[0],
            matched_rows=row[1],
            join_success_ratio=round(row[2], 6),
        )

    def evaluate_join_by_target(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        primary_keys: list[PrimaryKeyCandidate],
    ) -> JoinPrimaryKeyCandidate:
        """
        Evaluate a join between a source column and a named target key.

        Looks up the PrimaryKeyCandidate from the provided list, then delegates
        to evaluate_join_to_primary_key.
        """
        primary_key = self.find_primary_key(
            primary_keys=primary_keys,
            target_table=target_table,
            target_column=target_column,
        )

        return self.evaluate_join_to_primary_key(
            source_table=source_table,
            source_column=source_column,
            primary_key=primary_key,
        )

    def find_primary_key(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        target_table: str,
        target_column: str,
    ) -> PrimaryKeyCandidate:
        """
        Return the PrimaryKeyCandidate that matches table and column names.

        Raises ValueError if no match is found, which means profiling and
        primary-key inference must be run before calling this method.
        """
        for primary_key in primary_keys:
            if primary_key.table_name == target_table and primary_key.column_name == target_column:
                return primary_key

        raise ValueError(
            f"No primary-key candidate found for {target_table}.{target_column}. "
            "Run profiling and primary-key inference first."
        )

    def load_source_columns(self) -> list[SourceColumn]:
        """
        Load all profiled columns that are eligible foreign-key candidates.

        Excludes columns with 100% nulls and internal columns prefixed with '__'.
        """
        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type
        FROM {q_ident(META_DB)}.column_profiles
        WHERE null_ratio < 1
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name, column_name
        """

        rows = self.db.query(sql).result_rows

        return [
            SourceColumn(
                table_name=row[0],
                column_name=row[1],
                column_type=row[2],
            )
            for row in rows
        ]

    '''def evaluate_candidates(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        min_success_ratio: float = 0.95,
        max_workers: int = 8,
    ) -> list[JoinPrimaryKeyCandidate]:
        """
        Discover all foreign-key relationships in the database.

        Optimisations vs. version originale :
        - Index colonnes par type : accès O(1) au lieu de scan linéaire
        - Deux phases séparées : collecte CPU, puis exécution I/O parallèle
        - ThreadPoolExecutor : les requêtes SQL tournent en parallèle
        - should_skip_pair retiré là où le filtrage par type l'a rendu redondant
        """
        import itertools
        from collections import defaultdict
        from concurrent.futures import ThreadPoolExecutor, as_completed

        source_columns = self.load_source_columns()

        # Index principal : table → colonnes
        cols_by_table: dict[str, list] = defaultdict(list)
        # Index par type : table → type_nettoyé → colonnes  (évite le scan linéaire)
        cols_by_table_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

        print('\n Creation des colonnes')

        for col in source_columns:
            cols_by_table[col.table_name].append(col)
            cols_by_table_type[col.table_name][self._clean_type(col.column_type)].append(col)

        print('\n Phase 1 : collecte des paires valides (CPU-only, pas de SQL)')

        tasks: list[tuple[str, str, PrimaryKeyCandidate]] = []

        time = datetime.now()
        iter1 = 0
        iter2 = 0
        iter3 = 0

        for primary_key in primary_keys:

            iter1 += 1
            Rtime = datetime.now() - time
            print(f'Boucle 1 : {iter1} || temps écoulé : {Rtime}')

            target_cols  = [c.strip() for c in primary_key.column_name.split(",")]
            target_types = [self._clean_type(t.strip()) for t in primary_key.column_type.split(",")]
            is_composite = len(target_cols) > 1

            for table_name in cols_by_table:

                iter2 += 1
                Rtime = datetime.now() - time
                print(Fore.GREEN + f'Boucle 2 : {iter2} || temps écoulé : {Rtime}' + Style.RESET_ALL)

                if table_name == primary_key.table_name:
                    continue

                if not is_composite:
                    # Accès direct par type : pas de scan de toutes les colonnes
                    target_type = target_types[0]
                    matching_cols = cols_by_table_type[table_name].get(target_type, [])
                    for src in matching_cols:

                        iter3 += 1
                        Rtime = datetime.now() - time
                        print(Fore.YELLOW + f'Boucle 3 : {iter3} || temps écoulé : {Rtime}' + Style.RESET_ALL)

                        # Type déjà vérifié par l'index ; seule la table est à checker
                        # (should_skip_pair ferait exactement ça — on l'inline pour éviter l'appel)
                        tasks.append((table_name, src.column_name, primary_key))

                else:
                    # Pools par position, construits depuis l'index de types
                    pools = [
                        cols_by_table_type[table_name].get(t, [])
                        for t in target_types
                    ]
                    # Si une position n'a aucune colonne candidate → skip immédiat
                    if any(len(pool) == 0 for pool in pools):
                        continue

                    for combo in itertools.product(*pools):

                        iter3 += 1
                        Rtime = datetime.now() - time
                        print(Fore.RED + f'\rBoucle 3 : {iter3} || temps écoulé : {Rtime}' + Style.RESET_ALL)

                        # Pas de colonne dupliquée dans le combo
                        if len({c.column_name for c in combo}) != len(combo):
                            continue
                        tasks.append((
                            table_name,
                            ", ".join(c.column_name for c in combo),
                            primary_key,
                        ))

        # ── Phase 2 : exécution parallèle des JOIN SQL ────────────────────────────
        candidates: list[JoinPrimaryKeyCandidate] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(
                    self.evaluate_join_to_primary_key,
                    source_table=table_name,
                    source_column=combo_str,
                    primary_key=pk,
                ): (table_name, combo_str, pk)
                for table_name, combo_str, pk in tasks
            }

            for future in as_completed(future_to_task):
                try:
                    result = future.result()
                    if result.join_success_ratio >= min_success_ratio:
                        candidates.append(result)
                except Exception as exc:
                    table_name, combo_str, pk = future_to_task[future]
                    # Logguer sans faire planter tout le batch
                    print(f"[WARN] JOIN échoué : {table_name}.{combo_str} → {pk.table_name} : {exc}")

        return candidates'''

    MAX_COMPOSITE_COLS = 3   # FK à plus de 3 colonnes → ignorée
    MAX_COMBOS_PER_BATCH = 500

    def evaluate_candidates(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        min_success_ratio: float = 0.95,
        max_workers: int = 8,
        max_composite_cols: int = MAX_COMPOSITE_COLS,
        max_combos_per_batch: int = MAX_COMBOS_PER_BATCH,
    ) -> list[JoinPrimaryKeyCandidate]:
        import itertools
        from collections import defaultdict
        from concurrent.futures import ThreadPoolExecutor, as_completed

        source_columns = self.load_source_columns()

        cols_by_table: dict[str, list] = defaultdict(list)
        cols_by_table_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for col in source_columns:
            cols_by_table[col.table_name].append(col)
            cols_by_table_type[col.table_name][self._clean_type(col.column_type)].append(col)

        # ── Phase 1 : grouper les combos par (source_table, primary_key) ──────────
        # Structure : { (source_table, primary_key) → [combo_str, ...] }
        batches: dict[tuple, tuple[PrimaryKeyCandidate, list[str]]] = {}

        time = datetime.now()
        iter1 = 0
        iter2 = 0
        iter3 = 0

        for primary_key in primary_keys:

            iter1 += 1
            Rtime = datetime.now() - time
            print(f'\rBoucle 1 : {iter1} || temps écoulé : {Rtime}', end='')

            target_cols  = [c.strip() for c in primary_key.column_name.split(",")]
            target_types = [self._clean_type(t.strip()) for t in primary_key.column_type.split(",")]
            is_composite = len(target_types) > 1

            if is_composite and len(target_cols) > max_composite_cols:
                print(f"[SKIP] PK composite ignorée ({len(target_cols)} cols) : "
                      f"{primary_key.table_name}.{primary_key.column_name}")
                continue

            for table_name in cols_by_table:

                iter2 += 1
                Rtime = datetime.now() - time
                print(Fore.GREEN + f'\rBoucle 2 : {iter2} || temps écoulé : {Rtime}', end='' + Style.RESET_ALL)

                if table_name == primary_key.table_name:
                    continue

                batch_key = (table_name, primary_key.table_name, primary_key.column_name)

                if batch_key not in batches:
                    batches[batch_key] = (primary_key, [])

                _, combo_list = batches[batch_key]

                if not is_composite:
                    matching = cols_by_table_type[table_name].get(target_types[0], [])
                    for src in matching:
                        combo_list.append(src.column_name)

                else:
                    pools = [cols_by_table_type[table_name].get(t, []) for t in target_types]
                    if any(len(p) == 0 for p in pools):
                        continue
                    for combo in itertools.product(*pools):

                        iter3 += 1
                        Rtime = datetime.now() - time
                        print(Fore.YELLOW + f'\rBoucle 3 : {iter3} || temps écoulé : {Rtime}', end='' + Style.RESET_ALL)

                        if len(combo_list) >= max_combos_per_batch:
                            print(f"[CAP] {table_name} vs {primary_key.table_name} "
                                  f"tronqué à {max_combos_per_batch} combos")
                            break

                        if len({c.column_name for c in combo}) != len(combo):
                            continue
                        combo_list.append(", ".join(c.column_name for c in combo))

        # ── Phase 2 : une requête SQL par batch, en parallèle ────────────────────
        candidates: list[JoinPrimaryKeyCandidate] = []

        def evaluate_batch(
            source_table: str,
            primary_key: PrimaryKeyCandidate,
            combo_strs: list[str],
        ) -> list[JoinPrimaryKeyCandidate]:
            """
            Évalue toutes les colonnes candidates contre une PK
            en un seul scan de la source_table.
            """
            results = self.evaluate_join_batch(
                source_table=source_table,
                primary_key=primary_key,
                combo_strs=combo_strs,
            )
            return [r for r in results if r.join_success_ratio >= min_success_ratio]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(evaluate_batch, table_name, pk, combos): (table_name, pk)
                for (table_name, _, __), (pk, combos) in batches.items()
                if combos
            }
            for future in as_completed(futures):

                iter3 += 1
                Rtime = datetime.now() - time
                print(Fore.RED + f'\rBoucle 3 : {iter3} || temps écoulé : {Rtime}', end= '' + Style.RESET_ALL)

                try:
                    candidates.extend(future.result())
                except Exception as exc:
                    table_name, pk = futures[future]
                    print(f"[WARN] Batch échoué : {table_name} → {pk.table_name} : {exc}")

        return candidates
    
    def evaluate_join_batch(
        self,
        source_table: str,
        primary_key: PrimaryKeyCandidate,
        combo_strs: list[str],
    ) -> list[JoinPrimaryKeyCandidate]:

        pk_table = primary_key.table_name
        pk_cols  = [c.strip() for c in primary_key.column_name.split(",")]
        is_composite = len(pk_cols) > 1

        if is_composite:
            pk_tuple = f"({', '.join(q_ident(c) for c in pk_cols)})"
            pk_subq  = f"(SELECT {pk_tuple} FROM {q_ident(pk_table)})"
        else:
            pk_subq = f"(SELECT {q_ident(pk_cols[0])} FROM {q_ident(pk_table)})"

        select_parts = []
        for i, combo_str in enumerate(combo_strs):
            src_cols = [c.strip() for c in combo_str.split(",")]
            if is_composite:
                src_tuple    = f"({', '.join(q_ident(c) for c in src_cols)})"
                non_null_expr = f"countIf({' AND '.join(f'{q_ident(c)} IS NOT NULL' for c in src_cols)})"
                match_expr    = f"countIf({src_tuple} IN {pk_subq})"
            else:
                non_null_expr = f"countIf({q_ident(src_cols[0])} IS NOT NULL)"
                match_expr    = f"countIf({q_ident(src_cols[0])} IN {pk_subq})"

            select_parts.append(f"{non_null_expr} AS non_null_{i}")
            select_parts.append(f"{match_expr} AS matched_{i}")

        sql = f"""
            SELECT
                {', '.join(select_parts)}
            FROM {q_ident(source_table)}
        """

        row = self.db.query(sql).result_rows[0]

        results = []
        for i, combo_str in enumerate(combo_strs):
            source_non_null_rows = row[i * 2]
            matched_rows         = row[i * 2 + 1]
            ratio = matched_rows / source_non_null_rows if source_non_null_rows > 0 else 0.0

            results.append(JoinPrimaryKeyCandidate(
                source_table=source_table,
                source_column=combo_str,
                target_table=pk_table,
                target_column=primary_key.column_name,
                source_non_null_rows=source_non_null_rows,
                matched_rows=matched_rows,
                join_success_ratio=ratio,
            ))

        return results

    def store_candidates(
        self,
        candidates: list[JoinPrimaryKeyCandidate],
    ) -> None:
        """
        Store inferred join candidates in metadata.
        """

        if not candidates:
            return

        rows = [
            [
                candidate.source_table,
                candidate.source_column,
                candidate.target_table,
                candidate.target_column,
                candidate.source_non_null_rows,
                candidate.matched_rows,
                candidate.join_success_ratio,
            ]
            for candidate in candidates
        ]

        self.db.insert(
            f"{META_DB}.join_candidates",
            rows,
            column_names=[
                "source_table",
                "source_column",
                "target_table",
                "target_column",
                "source_non_null_rows",
                "matched_rows",
                "join_success_ratio",
            ],
        )


    def load_candidates(self) -> list[JoinPrimaryKeyCandidate]:
        """
        Load stored join candidates from metadata.
        """

        sql = f"""
        SELECT
            source_table,
            source_column,
            target_table,
            target_column,
            source_non_null_rows,
            matched_rows,
            join_success_ratio
        FROM {q_ident(META_DB)}.join_candidates
        ORDER BY source_table, target_table, source_column, target_column
        """

        rows = self.db.query(sql).result_rows

        return [
            JoinPrimaryKeyCandidate(
                source_table=row[0],
                source_column=row[1],
                target_table=row[2],
                target_column=row[3],
                source_non_null_rows=row[4],
                matched_rows=row[5],
                join_success_ratio=row[6],
            )
            for row in rows
        ]

    @staticmethod
    def _clean_type(ch_type: str) -> str:
        """Strip Nullable() wrapper to compare base physical types."""
        return ch_type.removeprefix("Nullable(").removesuffix(")")

    @classmethod
    def should_skip_pair(
        cls,
        source_combo: tuple[SourceColumn, ...],
        primary_key: PrimaryKeyCandidate,
    ) -> bool:
        """
        Return True if this source combination / primary-key pair cannot be a valid FK relationship.

        A pair is skipped when the source and target belong to the same table,
        or when their base ClickHouse types are incompatible (e.g. String vs Int64).
        Nullable wrappers are stripped before comparing types.
        """
        if not source_combo:
            return True

        same_table = source_combo[0].table_name == primary_key.table_name
        if same_table:
            return True

        target_types = [cls._clean_type(t.strip()) for t in primary_key.column_type.split(",")]

        if len(source_combo) != len(target_types):
            return True

        for src, t_type in zip(source_combo, target_types, strict=False):
            if cls._clean_type(src.column_type) != t_type:
                return True

        return False

    @staticmethod
    def print_result(result: JoinPrimaryKeyCandidate) -> None:
        log_join_result(result)

    @staticmethod
    def print_candidates(candidates: list[JoinPrimaryKeyCandidate]) -> None:
        log_join_candidates(candidates)


def log_join_result(result: JoinPrimaryKeyCandidate) -> None:
    """Log the result of a single join evaluation."""
    logger.info(
        "%s.%s -> %s.%s",
        result.source_table,
        result.source_column,
        result.target_table,
        result.target_column,
    )
    logger.info("Source non-null rows : %s", result.source_non_null_rows)
    logger.info("Matched rows         : %s", result.matched_rows)
    logger.info("Join success ratio   : %s", result.join_success_ratio)


def log_join_candidates(candidates: list[JoinPrimaryKeyCandidate]) -> None:
    """Log all join candidates found during inference."""
    if not candidates:
        logger.info("No join candidates found.")
        return

    for candidate in candidates:
        logger.info(
            "%s.%s -> %s.%s | ratio=%s",
            candidate.source_table,
            candidate.source_column,
            candidate.target_table,
            candidate.target_column,
            candidate.join_success_ratio,
        )
