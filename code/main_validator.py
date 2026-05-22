from main import *
from inference.adjacency import AdjacencyMatrixEngine
from semantic.semantic_engine import *


def test_run_join_inference() -> None:
    db = get_manager()
    PK_engine = PrimaryKeyEngine(db)
    CP_engine = CompositeKeyEngine(db)

    primary_keys = process_composite_candidates(db, PK_engine, CP_engine)

    print("\n", "="*50, "\n")
    
    logger.info("--- *** --- Evaluation de jointures physiques --- *** ---\n")
    join_engine = JoinEngine(db)
    raw_join_candidates = join_engine.evaluate_candidates(primary_keys) 
    
    join_engine.print_candidates(raw_join_candidates)

    print("\n", "="*50, "\n")


    logger.info("--- *** --- Construction du graphe d'adjacence... --- *** ---\n")
    adj_engine = AdjacencyMatrixEngine(db)
    raw_edges = adj_engine.build_edges_from_join_candidates(raw_join_candidates)

    logger.info("--- *** --- Enrichissement des arêtes avec l'analyse sémantique... --- *** ---")
    enriched_edges = enrich_edges_with_semantics(raw_edges)

    logger.info(f"--- *** --- Sauvegarde de {len(enriched_edges)} arêtes analysées --- *** ---")
    adj_engine.store_edges(enriched_edges)

    print("\n", "="*50, "\n")

    logger.info("--- *** --- Construction de la matrice d'adjacence --- *** ---")
    final_matrix = adj_engine.build_matrix(enriched_edges)
    adj_engine.print_binary_matrix(final_matrix)

    print("\n", "="*50, "\n")
    
    logger.info("--- *** --- Graphe d'adjacence enrichi --- *** ---\n")

    print("")
    logger.info("--- *** --- Jointure confirmée --- *** ---\n")
    confirmed_edges = [edge for edge in enriched_edges if edge.evidence == "CONFIRMED"]
    for edge in confirmed_edges:
        src = f"{edge.source_table}.{edge.source_columns[0]}"
        tgt = f"{edge.target_table}.{edge.target_columns[0]}"
        logger.info(f"{src:<25} -> {tgt:<25} | hybrid score: {edge.join_success_ratio:<10} | {edge.evidence}")

    print("") 
    logger.info("--- *** --- Jointure suspecte (coincidence?) --- *** ---\n")
    coincicence_edges = [edge for edge in enriched_edges if edge.evidence == "coincidence?"]
    for edge in coincicence_edges:
        src = f"{edge.source_table}.{edge.source_columns[0]}"
        tgt = f"{edge.target_table}.{edge.target_columns[0]}"
        logger.info(f"{src:<25} -> {tgt:<25} | hybrid score: {edge.join_success_ratio:<10} | {edge.evidence}")

    print("")
    logger.info("--- *** --- Jointure faible --- *** ---\n")
    weak_edges = [edge for edge in enriched_edges if edge.evidence == "weak"]
    for edge in weak_edges:
        src = f"{edge.source_table}.{edge.source_columns[0]}"
        tgt = f"{edge.target_table}.{edge.target_columns[0]}"
        logger.info(f"{src:<25} -> {tgt:<25} | hybrid score: {edge.join_success_ratio:<10} | {edge.evidence}")


test_run_join_inference()