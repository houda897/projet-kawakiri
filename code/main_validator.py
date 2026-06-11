from main import *
from inference.adjacency import AdjacencyMatrixEngine
from semantic.semantic_engine import *
from colorama import Fore, Style, init
from datetime import datetime

init()

time0 = datetime.now()

'''print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- folder_ingestion --- *** ---\n' + Style.RESET_ALL)
run_folder_ingestion('D:/Cours/KOUSHIN/DB_Exercice2')

time2 = datetime.now()
segment_time = time2 - time0
absolute_time = time2 - time0
print(Fore.RED + f'--- *** --- folder_ingestion --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)'''

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- basic_profile --- *** ---\n' + Style.RESET_ALL)
run_basic_profile()

time3 = datetime.now()
segment_time = time3 - time0
absolute_time = time3 - time0
print(Fore.RED + f'--- *** --- basic_profile --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- identifiability --- *** ---\n' + Style.RESET_ALL)
run_identifiability()

time4 = datetime.now()
segment_time = time4 - time3
absolute_time = time4 - time0
print(Fore.RED + f'--- *** --- identifiability --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- pk_inference --- *** ---\n' + Style.RESET_ALL)
run_pk_inference()

time5 = datetime.now()
segment_time = time5 - time4
absolute_time = time5 - time0
print(Fore.RED + f'--- *** --- pk_inference --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- join_inference --- *** ---\n' + Style.RESET_ALL)
run_join_inference()

time6 = datetime.now()
segment_time = time6 - time5
absolute_time = time6 - time0

print(Fore.GREEN + '--- *** --- adjacency --- *** ---\n' + Style.RESET_ALL)
run_adjacency()

time7 = datetime.now()
segment_time = time7 - time6
absolute_time = time7 - time0
print(Fore.RED + f'\n--- *** --- adjacency --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- table_roles --- *** ---\n' + Style.RESET_ALL)
run_table_roles()

time8 = datetime.now()
segment_time = time8 - time7
absolute_time = time8 - time0
print(Fore.RED + f'--- *** --- table_roles --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- model_candidate_building --- *** ---\n' + Style.RESET_ALL)
candidates = run_model_candidate_building()

time9 = datetime.now()
segment_time = time9 - time8
absolute_time = time9 - time0
print(Fore.RED + f'--- *** --- model_candidate_building --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)