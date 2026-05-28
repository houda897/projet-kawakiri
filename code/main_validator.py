from main import *
from inference.adjacency import AdjacencyMatrixEngine
from semantic.semantic_engine import *
from colorama import Fore, Style, init

init()

print(Fore.GREEN + '--- *** --- basic_profile --- *** ---' + Style.RESET_ALL)
run_basic_profile()

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- identifiability --- *** ---' + Style.RESET_ALL)
run_identifiability()

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- pk_inference --- *** ---' + Style.RESET_ALL)
run_pk_inference()

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- join_inference --- *** ---' + Style.RESET_ALL)
run_join_inference()

print(Fore.GREEN + '--- *** --- adjacency --- *** ---' + Style.RESET_ALL)
run_adjacency()

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- table_roles --- *** ---' + Style.RESET_ALL)
run_table_roles()