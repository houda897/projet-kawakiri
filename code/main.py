from stats.stats_computing import *
from stats.search_engine import *
from stats.functional_dependency import *

def pipeline_and_search() :
    stats_pipeline()

    dict = get_table_stats("EuroStat","Effets_de_la_pollution_atmosphérique_sur_la_santé")
    #print(dict)

    obs_value = dict['obs_value']
    print('obs_value :\n', obs_value)

    obs_value_entropy = dict['obs_value']['entropy']
    print('obs_value_entropy : \n', obs_value_entropy)

def pipeline_and_identifie() :
    stats_pipeline()
    dict = calculate_identifiability("Exercice","test_profiling_clients")
    print("\n",dict)
    print("\n \n ID : ", dict["client_id"])


analyses = analyze_table_dependencies('Exercice', 'test_profiling_clients')
# Extraction et affichage uniquement des dépendances valides trouvées (Utile pour la normalisation !)
print("\n👑 --- DÉPENDANCES FONCTIONNELLES PROUVÉES (Valides) ---")
found_valid = False
for relation, data in analyses.items():
    if data["is_valid"]:
        print(f"  {data['message']}")
        found_valid = True
            
if not found_valid:
    print("  Aucune dépendance fonctionnelle stricte n'a été trouvée entre les colonnes.")