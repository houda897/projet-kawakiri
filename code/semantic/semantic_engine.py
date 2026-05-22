import re
from rapidfuzz import fuzz
from core.logger import get_logger
from inference.adjacency import AdjacencyEdge

logger = get_logger(__name__)

class SemanticEngine:
    '''Semantic engine that computes a similarity (with Levenshtein distance) score between column names to enrich join candidates'''
    def __init__(self):
        '''
        Define usual prefix and suffix patterns in columns names
        Those patterns will be stripped out to normalise column names
        '''
        self.noise_patterns = [
            r'^id_', r'^fk_', r'^pk_',  # Préfixes
            r'_id$', r'_fk$', r'_key$'  # Suffixes
        ]
        self.noise_regex = re.compile('|'.join(self.noise_patterns), re.IGNORECASE)

    def normalize_column_name(self, column_name: str) -> str:
        '''Normalise the column name by removing prefix/suffix patterns, underscores, hyphens and converting to lowercase'''
        if not column_name:
            return ""

        name = column_name.lower()

        prev_name = ""
        while name != prev_name:
            prev_name = name
            name = self.noise_regex.sub('', name)

        name = name.replace('_', '').replace('-', '')

        return name.strip()

    def compute_similarity(self, col1: str, col2: str) -> float:
        '''Calculate a similarity score between two column names using Levenshtein distance'''
        norm1 = self.normalize_column_name(col1)
        norm2 = self.normalize_column_name(col2)

        if not norm1 or not norm2:
            return 1.0 if norm1 == norm2 else 0.0

        score = fuzz.ratio(norm1, norm2) / 100.0

        return round(score, 4)


def enrich_edges_with_semantics(edges: list[AdjacencyEdge]) -> list[AdjacencyEdge]:
    '''
    Enrich the join candidates (edges) by recalculating an hybrid score that combine the original join success ratio with a semantic similarity score
    and add a evidence label based on the new hybrid score
    '''

    semantic_engine = SemanticEngine()
    enriched_edges = []
    
    for edge in edges:
        # TODO : À adapter pour des clés composites de jointure
        src_col = edge.source_columns[0] 
        tgt_col = edge.target_columns[0]
        
        semantic_score = semantic_engine.compute_similarity(src_col, tgt_col)
        
        hybrid_score = round((0.66 * edge.join_success_ratio) + (0.34 * semantic_score), 6)
        
        # TODO : Label à modifier, voir mardi
        if semantic_score >= 0.75:
            evidence_label = "CONFIRMED"
        elif semantic_score <= 0.25 and edge.join_success_ratio > 0.9:
            evidence_label = "coincidence?"
        else:
            evidence_label = "weak"
            
        enriched_edges.append(AdjacencyEdge(
            source_table=edge.source_table,
            target_table=edge.target_table,
            source_columns=edge.source_columns,
            target_columns=edge.target_columns,
            join_success_ratio=hybrid_score,
            evidence= evidence_label
        ))
        
    return enriched_edges