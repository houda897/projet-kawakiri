from main import *
from inference.adjacency import AdjacencyMatrixEngine
from semantic.semantic_engine import *
from colorama import Fore, Style, init


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
    edges = adj_engine.build_edges_from_join_candidates(raw_join_candidates)

    logger.info(f"--- *** --- Sauvegarde de {len(edges)} arêtes analysées --- *** ---")
    adj_engine.store_edges(edges)

    print("\n", "="*50, "\n")

    logger.info("--- *** --- Construction de la matrice d'adjacence --- *** ---")
    final_matrix = adj_engine.build_matrix(edges)
    adj_engine.print_binary_matrix(final_matrix)

    print("\n", "="*50, "\n")
    
    logger.info("--- *** --- Graphe d'adjacence enrichi --- *** ---\n")

    adj_engine.print_edges(edges)

#run_basic_profile()
#run_identifiability()
#run_pk_inference()
test_run_join_inference()