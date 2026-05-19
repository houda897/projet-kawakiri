from stats.stats_computing import *
from stats.functional_dependency import *
from stats.search_engine import *
from stats.table_partition import *

def search() :

    dict = get_table_stats("EuroStat","Effets_de_la_pollution_atmosphérique_sur_la_santé")
    #print(dict)

    obs_value = dict['obs_value']
    print('obs_value :\n', obs_value)

    obs_value_entropy = dict['obs_value']['entropy']
    print('obs_value_entropy : \n', obs_value_entropy)

def identifie() :
    dictionnary = calculate_identifiability('Exercice', 'test_profiling_clients')
    print("\n",dictionnary)

def analyse() :
    if analyze_table_dependencies('Exercice', 'test_profiling_clients', 'client_id') :
        print("The column have a dependency with all the other columns")
    else :
        print("The column don't have dependency with all the others and is not PK candidate")

analyse()




