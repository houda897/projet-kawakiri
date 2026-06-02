from main import *
from inference.adjacency import AdjacencyMatrixEngine
from semantic.semantic_engine import *
from colorama import Fore, Style, init
from datetime import datetime

init()

time0 = datetime.now()

print(Fore.GREEN + '--- *** --- basic_profile --- *** ---' + Style.RESET_ALL)
run_basic_profile()

time1 = datetime.now()
segment_time = time1 - time0
absolute_time = time1 - time0
print(Fore.RED + f'--- *** --- basic_profile --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- identifiability --- *** ---' + Style.RESET_ALL)
run_identifiability()

time2 = datetime.now()
segment_time = time2 - time1
absolute_time = time2 - time0
print(Fore.RED + f'--- *** --- identifiability --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- join_inference --- *** ---' + Style.RESET_ALL)
run_join_inference()

time3 = datetime.now()
segment_time = time3 - time2
absolute_time = time3 - time0
print(Fore.RED + f'--- *** --- join_inference --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print(Fore.GREEN + '--- *** --- adjacency --- *** ---' + Style.RESET_ALL)
run_adjacency()

time4 = datetime.now()
segment_time = time4 - time3
absolute_time = time4 - time0
print(Fore.RED + f'--- *** --- adjacency --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print('\n' + '=' * 80 + '\n')

print(Fore.GREEN + '--- *** --- table_roles --- *** ---' + Style.RESET_ALL)
run_table_roles()

time5 = datetime.now()
segment_time = time5 - time4
absolute_time = time5 - time0
print(Fore.RED + f'--- *** --- table_roles --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

print(Fore.GREEN + '--- *** --- model_candidate_building --- *** ---' + Style.RESET_ALL)
run_model_candidate_building()

time6 = datetime.now()
segment_time = time6 - time5
absolute_time = time6 - time0
print(Fore.RED + f'--- *** --- model_candidate_building --- *** --- time: {segment_time} (absolute: {absolute_time})' + Style.RESET_ALL)

