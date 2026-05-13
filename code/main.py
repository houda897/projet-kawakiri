from stats.stats_computing import *
from stats.search_engine import *

def pipeline_and_search() :
    stats_pipeline()

    dict = get_table_stats("EuroStat","Effets_de_la_pollution_atmosphérique_sur_la_santé")
    #print(dict)

    obs_value = dict['obs_value']
    print('obs_value :\n', obs_value)

    obs_value_entropy = dict['obs_value']['entropy']
    print('obs_value_entropy : \n', obs_value_entropy)

# stats_pipeline()
dict = calculate_identifiability("Exercice","test_profiling_clients")
#print("\n",dict)
#print("\n \n ID : ", dict["client_id"])