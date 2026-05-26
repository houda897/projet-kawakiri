from main import *
from inference.adjacency import AdjacencyMatrixEngine
from semantic.semantic_engine import *
from colorama import Fore, Style


def test_run_join_inference() -> None:
    db = get_manager()
    PK_engine = PrimaryKeyEngine(db)

    primary_keys = PK_engine.infer_candidates()

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

    RED = Fore.RED
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    RESET = Style.RESET_ALL

    print("")
    logger.info("--- *** --- Jointure confirmée --- *** ---\n")
    confirmed_edges = [edge for edge in enriched_edges if edge.evidence == "CONFIRMED"]
    for edge in confirmed_edges:
        src = f"{edge.source_table}.{edge.source_columns[0]}"
        tgt = f"{edge.target_table}.{edge.target_columns[0]}"
        logger.info(f"{src:<25} -> {tgt:<25} | ratio : {edge.join_success_ratio:<10} | hybrid score: {edge.hybrid_score:<10} | {GREEN}{edge.evidence}{RESET}")

    print("") 
    logger.info("--- *** --- Jointure suspecte (coincidence?) --- *** ---\n")
    coincicence_edges = [edge for edge in enriched_edges if edge.evidence == "COINCIDENCE"]
    for edge in coincicence_edges:
        src = f"{edge.source_table}.{edge.source_columns[0]}"
        tgt = f"{edge.target_table}.{edge.target_columns[0]}"
        logger.info(f"{src:<25} -> {tgt:<25} | ratio : {edge.join_success_ratio:<10} | hybrid score: {edge.hybrid_score:<10} | {YELLOW}{edge.evidence}{RESET}")

    print("")
    logger.info("--- *** --- Jointure faible --- *** ---\n")
    weak_edges = [edge for edge in enriched_edges if edge.evidence == "WEAK"]
    for edge in weak_edges:
        src = f"{edge.source_table}.{edge.source_columns[0]}"
        tgt = f"{edge.target_table}.{edge.target_columns[0]}"
        logger.info(f"{src:<25} -> {tgt:<25} | ratio : {edge.join_success_ratio:<10} | hybrid score: {edge.hybrid_score:<10} | {RED}{edge.evidence}{RESET}")

run_basic_profile()
run_identifiability()
run_pk_inference()
test_run_join_inference()