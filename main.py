import_errors = False
import os
import sys
import queue
import shutil
import time
from datetime import datetime
import hashlib
import threading
import runpy
import json
import atexit
import copy
import concurrent.futures
import base64
import math
import subprocess
import select
import shlex
try:
    from tqdm import tqdm
    import msvcrt
except:
    import_errors = "PC"
try:
    from watchdog.observers import Observer
    from watchdog.events import LoggingEventHandler
except:
    import_errors = "NAS"


with open("config.json", "r") as config_file:
    config = json.load(config_file)



src_path = config["SyncPath"].rstrip('/') + '/'
file_tree_path = config["FileTreePath"].rstrip('/') + '/'
nas_path = False
nas_detection_timeout = config["NasDetectionTimeout"]
nas_detection_trials = config["NasDetectionTrials"]
nas_local_path = config["NasLocalPath"].rstrip('/') + '/'
forbidden_paths = config["ForbiddenPaths"]
allowed_paths = config["AllowedPaths"]
file_tree_name = config["FileTreeName"]
last_list_threshold = config["LastListThreshold"]
large_file_size = config["LargeFileSize"]
small_file_threads = config["SmallFileThreads"]
hash_threads = config["HashThreads"]
nas_autosave_delay = config["NasAutoSaveDelay"]
list_changes_fold_paths = config["ListChangesFoldPaths"]
max_operations_without_confirm = config["MaxOperationsWithoutConfirm"]

task_queue = queue.Queue()
hash_queue = queue.Queue()

NASsuccessfullyDownloaded = False
documents_path = os.path.expanduser("~/Documents/PySync/").replace("\\", "/")

tqdm_main_format = '{desc:<10.50} | {percentage:3.0f}% | {bar} | {n_fmt}/{total_fmt} {rate_fmt}{postfix} | ETA:{remaining}'

errors = 0
retries = 0
last_print_time = 0
current_formatted_tree = {}


mode = 'PC'
if os.path.split(os.getcwd())[-1] + '/' == file_tree_path:
    mode = 'NAS'

if mode == import_errors:
    raise Exception("Error during packages importing")


    
def prRed(skk, end='\n'): print("\033[91m{}\033[00m".format(skk), end=end)
def prGreen(skk, end='\n'): print("\033[92m{}\033[00m".format(skk), end=end)
def prYellow(skk, end='\n'): print("\033[93m{}\033[00m".format(skk), end=end)
def prBlue(skk, end='\n'): print("\033[94m{}\033[00m".format(skk), end=end)
def prPurple(skk, end='\n'): print("\033[95m{}\033[00m".format(skk), end=end)
def prCyan(skk, end='\n'): print("\033[96m{}\033[00m".format(skk), end=end)
def prLightGray(skk, end='\n'): print("\033[97m{}\033[00m".format(skk), end=end)
def prBlack(skk, end='\n'): print("\033[98m{}\033[00m".format(skk), end=end)

    
def red(s): return("\033[91m{}\033[00m".format(s))
def green(s): return("\033[92m{}\033[00m".format(s))
def yellow(s): return("\033[93m{}\033[00m".format(s))
def blue(s): return("\033[94m{}\033[00m".format(s))
def purple(s): return("\033[95m{}\033[00m".format(s))
def cyan(s): return("\033[96m{}\033[00m".format(s))
def lightGray(s): return("\033[97m{}\033[00m".format(s))
def black(s): return("\033[98m{}\033[00m".format(s))

def wrap(s): return s[:os.get_terminal_size()[0] - 5]



def check_nas_path(path, timeout):
    def worker():
        try:
            os.listdir(path)
        except:
            time.sleep(timeout * 2)
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return False
    return True

def check_nas_paths():
    nas_path = False
    for path in config["NasPaths"]:
        print(f"Checking Network Drive on {blue(path)} ...")
        if check_nas_path(path, nas_detection_timeout):
            nas_path =path.rstrip('/') + '/'
            prGreen("Drive found!")
            break
    return nas_path
    

def file_action(action_info):
    global errors
    item = action_info["item"]
    src_path = action_info["src"]
    dst_path = action_info["dst"]
    tq = action_info["tqdm"]
    action = action_info["Action"]
    changes = action_info["Changes"]
    desc = action_info["desc"]
    
    try:
        if action == "Copy":
            item1 = remove_file_hash(item)
            shutil.copy2(src_path + item1, dst_path + item1)
            
        
        if action == "Delete":
            item1 = remove_file_hash(item)
            os.remove(dst_path + item1)
        
        
        tq.update()
        desc.set_description_str(wrap("    " + (item)))
        changes.remove(item)
    except Exception as e:
        prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {src_path + item}')
        errors += 1
        time.sleep(0.5)
        tq.update()

def file_worker():
    while True:
        work = task_queue.get()
        if work is None:
            # Sentinel value reached, break the loop
            break
        file_action(work)
        task_queue.task_done()


def hash_action(path):
    global hashed_files
    try:
        file_stat = os.stat(path[1])
        file_time = file_stat.st_mtime
        file_size = file_stat.st_size
    except:
        if path[1].__len__() > 256:
            prRed(path[1])
            raise Exception("PATH over 256 chars!")
    
    size = str(hex(str(file_size).__len__()))[-1]
    prehash_str = bytearray((str(file_size) + "&" + str(file_time)).encode("utf-8"))
    file_hash = ((hashlib.sha256(prehash_str).digest()))
    encoded_hash = (str(base64.urlsafe_b64encode(file_hash))[2:-2] + size)[-16:]
    hashed_files.append(path[0] + " " + encoded_hash)
    return (path[0] + " " + encoded_hash)


def hash_worker():
    while True:
        path = hash_queue.get()
        if path is None:
            # Sentinel value reached, break the loop
            break
        hash_action(path)
        hash_queue.task_done()


def update_nas_config():
    shutil.copy("config.json", nas_path + file_tree_path + "config.json")


def run_nas_script():
    global NASsuccessfullyDownloaded
    print("Listing NAS files...")
    update_nas_config()
    with open(nas_path + file_tree_path + "sync.txt", "w") as f:
        f.write(" ")
        
    time.sleep(2)
    while os.path.exists(nas_path + file_tree_path + "sync.txt"):
        time.sleep(1)
    prGreen("NAS listing complete")
    get_nas_tree()
    prGreen("NAS fileTree download complete")
    NASsuccessfullyDownloaded = True


def reload_nas_tree():
    print("Reloading NAS tree...")
    update_nas_config()
    with open(nas_path + file_tree_path + "restart.txt", "w") as f:
        f.write(" ")
        
    time.sleep(2)
    while os.path.exists(nas_path + file_tree_path + "restart.txt"):
        time.sleep(1)
        
    prGreen("NAS fileTree reloaded")


def get_contents(path, local_path = ""):
    contents = []
    
    with os.scandir(path) as entries:
        for entry in entries:
            
            element = entry.name
            is_dir = entry.is_dir()
            
            work_path = os.path.join(path, element)
            local_path_1 = os.path.join(local_path, element).replace("\\", "/")
            
            if is_dir:                
                if (local_path != "" or ((not element in forbidden_paths) and ((element + '/') in allowed_paths or '*' in allowed_paths))):
                    if local_path_1 + '/' in forbidden_paths:
                        continue
                    contents.append(local_path_1 + "/")
                    try:
                        contents.extend(get_contents(work_path, local_path_1))
                    except PermissionError:
                        print("PERMISSION ERROR WHILE CREATING " + element)
                        
            else:
                contents.append(local_path_1)
    
    return contents

def get_contents_with_hashes(path, unformatted = True):
    global hashed_files
    hashed_files = []
    contents = []
    time_start = time.time()
    
    contents_1 = get_contents(path)
    
    print(f'took {round(time.time() - time_start, 2)} s to list files')
    time_start = time.time()
    
    for item in contents_1:
        if item[-1] == "/":
            contents.append(item)
        else:
            hash_queue.put([item, path + item])
    print(f'took {round(time.time() - time_start, 2)} s to update queue')
    time_start = time.time()
    
    hash_queue.join()
    print(f'took {round(time.time() - time_start, 2)} s to hash files')
    contents.extend(hashed_files)
    print(f' total of {contents.__len__()} files listed')
    
    if not unformatted: 
        return contents
        
    contents_output = unformat_dir_tree(contents)
    return contents_output
    

def get_trees_async():
    global NASsuccessfullyDownloaded
    time_start = time.time()
    global left_tree, right_tree, common_tree, current_formatted_tree
    right_tree = []
    thread = threading.Thread(target=run_nas_script)
    thread.start()
    print("Listing local files...")
    left_tree = get_contents_with_hashes(src_path)
    current_formatted_tree = left_tree
    
    prGreen("Local listing complete")
    # exit()
    common_tree = get_local_tree()
    thread.join()
    if NASsuccessfullyDownloaded == False:
        raise Exception("Failed to download NAS tree")
    NASsuccessfullyDownloaded = False
    print(f'Total time: {time.time() - time_start}')
    return left_tree, right_tree, common_tree


def get_changes(left_tree, right_tree, common_tree):
    to_upload = list_changes(left_tree, common_tree)
    to_download = list_changes(right_tree, common_tree)
    tu_new = {}
    td_new = {}
    for key in list(set(to_upload.keys()).union(set(to_download.keys()))):
        try:
            tu_val = to_upload[key]
            td_val = to_download[key]
            diff1 = list(set(tu_val).difference(set(td_val)))
            diff2 = list(set(td_val).difference(set(tu_val)))
            tu_new[key] = diff1
            td_new[key] = diff2
        except:
            if key in to_upload.keys():
                tu_new = to_upload[key]
            if key in to_download.keys():
                td_new = to_download[key]
        
    return tu_new, td_new


def format_dir_tree(lines):
    indent_level = 0
    path = []
    elements = []
    
    for line in lines:
        
        indent_level = len(line) - len(line.lstrip())
        
        while path.__len__() > indent_level and path.__len__() > 0:
            path.pop()
            
        is_file = False
        element = line.strip()
        if element[-1] == "/":
            path.append(element[1:-2])
        else:
            is_file = True
        
        if is_file:
            if path:
                elements.append("/".join(path) + "/" + element[1:])
            else:
                elements.append(element[1:])
        else:
            elements.append("/".join(path) + "/")
    return elements

def unformat_dir_tree(elements):
    elements_sort = sorted(elements)
    lines = []
    for element in elements_sort:
        path = element.split('/')
        if element[-1] == '/':
            lines.append(' ' * (len(path) - 2) + '-' + path[-2] + ' /')
        else:
            lines.append(' ' * (len(path) - 1) + '-' + path[-1])
    return lines


def list_changes(left_tree : list, right_tree : list):
    global config
    detect_copy = config["DetectCopy"]
    detect_move = config["DetectMove"]
    
    left_side = set(format_dir_tree(left_tree))
    right_side = set(format_dir_tree(right_tree))

    only_left_side = left_side.difference(right_side)
    only_right_side = right_side.difference(left_side)
    common_files = left_side.intersection(right_side)

    only_left_side_names = {}
    only_left_side_hashes = {}
    only_left_side_dirs = []
    for element in only_left_side:
        if element[-1] == '/':
            only_left_side_dirs.append(element)
        else:
            only_left_side_names[element[:-17]] = element
            if only_left_side_hashes.get(element[-16:]):
                only_left_side_hashes[element[-16:]] = only_left_side_hashes[element[-16:]] + [element]
            else:
                only_left_side_hashes[element[-16:]] = [element]


    only_right_side_names = {}
    only_right_side_hashes = {}
    only_right_side_dirs = []
    for element in only_right_side:
        if element[-1] == '/':
            only_right_side_dirs.append(element)
        else:
            only_right_side_names[element[:-17]] = element
            if only_right_side_hashes.get(element[-16:]):
                only_right_side_hashes[element[-16:]] = only_right_side_hashes[element[-16:]] + [element]
            else:
                only_right_side_hashes[element[-16:]] = [element]


    common_files_names = {}
    common_files_hashes = {}
    for element in common_files:
        common_files_names[element[:-17]] = element
        if common_files_hashes.get(element[-16:]):
            common_files_hashes[element[-16:]] = common_files_hashes[element[-16:]] + [element]
        else:
            common_files_hashes[element[-16:]] = [element]


    local_create_files = []
    local_delete_files = []
    copied = []
    moved = []
    
    for element in only_left_side_hashes:
        left_elements = only_left_side_hashes.get(element)
        right_elements = only_right_side_hashes.get(element)
        common_elements = common_files_hashes.get(element)
        
        for i, item in enumerate(left_elements):
            if left_elements.__len__() > i:
                if (right_elements and right_elements.__len__() > i) and detect_move:
                    moved.append(f'{right_elements[i]} >> {item}')
                    local_create_files.append(item)
                    local_delete_files.append(right_elements[i])
                
                elif common_elements and detect_copy:
                    copied.append(f'{common_elements[0]} >> {item}')
                    local_create_files.append(item)
                

    created = []
    for element in only_left_side_names:
        if not element in only_right_side_names:
            created.append(only_left_side_names[element])

    created = list(set(created).difference(set(local_create_files)))

    deleted = []
    for element in only_right_side_names:
        if not element in only_left_side_names:
            deleted.append(only_right_side_names[element])
            
    deleted = list(set(deleted).difference(set(local_delete_files)))

    changed = []
    for element in only_right_side_names:
        if element in only_left_side_names:
            changed.append(only_left_side_names[element])

    dirs_created = sorted(only_left_side_dirs)
    dirs_deleted = sorted(only_right_side_dirs, reverse=True)
    return {"DirCreated" : dirs_created, "Changed" : changed, "Created" : created, "Moved" : moved, "Copied" : copied, "Deleted" : deleted, "DirDeleted" : dirs_deleted}


def get_len(dictionary: dict, condition = ''): 
    try:
        return sum(len(v) for k, v in dictionary.items() if condition in k)
    except:
        return 0


def load_changes():
    try:
        with open(documents_path + "upload.json", "r", encoding="utf-8") as changes_file:
            to_upload = json.load(changes_file)
        with open(documents_path + "download.json", "r", encoding="utf-8") as changes_file:
            to_download = json.load(changes_file)
        return to_upload, to_download
    except:
        return {}, {}
    
    
def save_changes(to_upload, to_download):
    with open(documents_path + "upload.json", "w", encoding="utf-8") as changes_file:
        json.dump(to_upload, changes_file)
    with open(documents_path + "download.json", "w", encoding="utf-8") as changes_file:
        json.dump(to_download, changes_file)


def save_changes_log(to_upload, to_download):
    with open(documents_path + "last_upload.json", "w", encoding="utf-8") as changes_file:
        json.dump(to_upload, changes_file)
    with open(documents_path + "last_download.json", "w", encoding="utf-8") as changes_file:
        json.dump(to_download, changes_file)
        

def exit_save_changes():
    global to_upload, to_download
    save_changes(to_upload, to_download)
    if get_len(to_upload) + get_len(to_download) > 0:
        prYellow("Saved session changes")


#FIXME: CRITICAL BUG ZERO LENGTH TREE WHEN ERROR DURING TREE DOWNLOAD
def get_nas_tree():
    global right_tree
    with open(nas_path + file_tree_path + file_tree_name, "r", encoding="utf-8") as file_tree:
        nas_contents = file_tree.readlines()
    for i in range(nas_contents.__len__()):
        nas_contents[i] = nas_contents[i].removesuffix("\n")
    right_tree = nas_contents


def get_local_tree():
    global file_tree_name
    with open(documents_path + file_tree_name, "r", encoding="utf-8") as file_tree:
        contents = file_tree.readlines()
        for i in range(contents.__len__()):
            contents[i] = contents[i].removesuffix("\n")
    return contents


def update_local_tree(local_tree : list, path):
    global file_tree_name
    with open(path + file_tree_name, "w", encoding="utf-8") as file_tree:
        file_tree.write('\n'.join(local_tree))


def remove_file_hash(name : str): return name[:-17]
def split_move_copy(command: str): return [remove_file_hash(sides) for sides in command.split(' >> ')]


def copy_file(from_path, to_path, item1, item, desc):
    t = threading.Thread(target=shutil.copy2, args=[from_path + item1, to_path + item1])
    t.start()
    i = 0
    s2 = os.path.getsize(from_path + item1)
    
    while t.is_alive():
        i += 1
        time.sleep(0.1)
        if i > 20:
            i = 0
            s1 = os.path.getsize(to_path + item1)
            percent = int(s1/s2 * 100)
            if percent > 100: percent = 100
            desc.set_description_str(wrap(f" {green(str(percent) + '%')}   " + item))
    t.join()


def file_operation(changes : dict, from_path: str, to_path: str):
    global errors
    
    global large_file_size
    changes_1 = copy.deepcopy(changes)
    with tqdm(total=changes_1["DirCreated"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(sorted(changes_1["DirCreated"]), "DirCreated", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            try:
                os.mkdir(to_path + item)
            except FileExistsError:
                prYellow(f"FILE EXISTS")
                print(to_path + item)
            except FileNotFoundError:
                prRed(f"FILE NOT FOUND CRITICAL")
                print(to_path + item)
            changes["DirCreated"].remove(item)
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
    
    
    small_files = []
    large_files = []
    for item in changes_1["Created"]:
        if int(item[-1], 16) >= large_file_size:
            large_files.append(item)
        else:
            small_files.append(item)
    
    with tqdm(total=small_files.__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        with tqdm(total = small_files.__len__(), desc="Created SmallFiles", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE") as tq:
            for item in small_files:
                task_queue.put({"Action" : "Copy", "src" : from_path, "dst" : to_path, "item" : item, "tqdm" : tq, "desc" : desc, "Changes" : changes["Created"]})
            
            while task_queue.qsize() > 0:
                try:
                    time.sleep(0.1)
                except KeyboardInterrupt:
                    task_queue._init(0)
                    exit()
            task_queue.join()
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
    
    
    with tqdm(total=large_files.__len__() + 10, desc = " ", bar_format='{desc}', position=1, unit_scale=True, unit='B') as desc:
        for item in tqdm(large_files, "Created LargeFiles", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            item1 = remove_file_hash(item)
            try:
                copy_file(from_path, to_path, item1, item, desc)
                changes["Created"].remove(item)
            except Exception as e:
                prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
                time.sleep(0.5)
                errors += 1
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
    
    
    small_files = []
    large_files = []
    for item in changes_1["Changed"]:
        if int(item[-1], 16) >= large_file_size:
            large_files.append(item)
        else:
            small_files.append(item)
    
    with tqdm(total=small_files.__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        with tqdm(total = small_files.__len__(), desc="Changed SmallFiles", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE") as tq:
            for item in small_files:
                task_queue.put({"Action" : "Copy", "src" : from_path, "dst" : to_path, "item" : item, "tqdm" : tq, "desc" : desc, "Changes" : changes["Changed"]})
            
            while task_queue.qsize() > 0:
                try:
                    time.sleep(0.1)
                except KeyboardInterrupt:
                    task_queue._init(0)
                    exit()
            task_queue.join()
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
        
             
    with tqdm(total=large_files.__len__() + 10, desc = " ", bar_format='{desc}', position=1, unit_scale=True, unit='B') as desc:
        for item in tqdm(large_files, "Changed LargeFiles", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            item1 = remove_file_hash(item)
            try:
                copy_file(from_path, to_path, item1, item, desc)
                changes["Changed"].remove(item)
            except Exception as e:
                prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
                time.sleep(0.5)
                errors += 1
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
        
    
    with tqdm(total=changes_1["Moved"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(changes_1["Moved"], "Moved", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            files = split_move_copy(item)
            try:
                shutil.move(to_path + files[0], to_path + files[1]) # FIXME: move/copy not working
                changes["Moved"].remove(item)
            except Exception as e:
                prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
                time.sleep(0.5)
                errors += 1
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
        
    
    with tqdm(total=changes_1["Copied"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(changes_1["Copied"], "Copied", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            files = split_move_copy(item)
            try:
                shutil.copy2(to_path + files[0], to_path + files[1])
                changes["Copied"].remove(item)
            except Exception as e:
                prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
                time.sleep(0.5)
                errors += 1
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
        
            
    with tqdm(total=changes_1["Deleted"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        with tqdm(total = changes_1["Deleted"].__len__(), desc="Deleted", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE") as tq:
            tq.set_postfix_str()
            for item in changes_1["Deleted"]:
                task_queue.put({"Action" : "Delete", "src" : from_path, "dst" : to_path, "item" : item, "tqdm" : tq, "desc" : desc, "Changes" : changes["Deleted"]})
            
            while task_queue.qsize() > 0:
                try:
                    time.sleep(0.1)
                except KeyboardInterrupt:
                    task_queue._init(0)
                    exit()
            task_queue.join()
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
        
    
    with tqdm(total=changes_1["DirDeleted"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(sorted(changes_1["DirDeleted"], reverse=True), "DirDeleted", bar_format=tqdm_main_format, unit='file', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            try:
                os.rmdir(to_path + item)
                changes["DirDeleted"].remove(item)
            except Exception as e:
                prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
                time.sleep(0.5)
                errors += 1
        desc.set_description_str(wrap(" " * 500), refresh=True)
        

def init_sync():
    global to_upload, to_download, nas_path, left_tree, right_tree, common_tree
    
    for i in range(nas_detection_trials):
    
        nas_path = check_nas_paths()
        if nas_path != False:
            break
        prRed(f"Network Drive not found in any of selected paths! {i + 1} of {nas_detection_trials}")
    else:
        time.sleep(1)
        exit()
    
    if not os.path.exists(documents_path + file_tree_name):
        open(documents_path + file_tree_name, 'a').close()
    
    to_upload, to_download = load_changes()
    
    if get_len(to_upload) + get_len(to_download) > 0:
        prYellow("resuming previous sync")
        right_tree = None
        left_tree = None
    else:
        left_tree, right_tree, common_tree = get_trees_async()
        to_upload, to_download = get_changes(left_tree, right_tree, common_tree)
    
    save_changes(to_upload, to_download)


def analyse_tree_change(file_tree : list, possible_change):
    changed = False
    root_dir = possible_change.split('/')[0]
    if not((not root_dir in forbidden_paths) and ((root_dir + '/') in allowed_paths or '*' in allowed_paths)): return False
    change_path = nas_local_path + possible_change
    item_exists = os.path.exists(change_path)
    new_item = possible_change
    if possible_change[-1] == '/':
        if possible_change in file_tree:
            file_tree.remove(possible_change)
            changed = True
            # print("removed " + possible_change)
    else:
        if item_exists: new_item = hash_action([possible_change, change_path])
        for line in file_tree:
            if line[:-17] == possible_change:
                file_tree.remove(line)
                changed = True
                # print("removed " + line)
                break
    
    if item_exists:
        file_tree.append(new_item)
        changed = True
    #     print("added " + new_item)
    # print("-------------------------------")
    return changed



def list_info(change_list: dict):
    try:
        for item in change_list.keys():
            if change_list[item].__len__() == 0:
                continue
            prYellow(" " + item + ":")
            elements:str = change_list[item]
            elements = sorted(elements)
            start_dir = ''
            no_items = 1
            for element in elements:
                
                if element[-1] == '/':
                    test_dir = element
                else:
                    test_dir = element[:-17]
                    
                start_index = -1
                for _ in range(list_changes_fold_paths):
                    start_index = test_dir.find("/", start_index + 1)
                    if start_index == -1:
                        start_index = -2
                        break
                    
                fix_start_dir = ">" + start_dir
                fix_test_dir = ">" + test_dir[:start_index+1]
                if start_index == -2:
                    fix_test_dir = ">" + test_dir
                
                
                if fix_test_dir in fix_start_dir and list_changes_fold_paths > 0:
                    no_items += 1
                    # if fix_test_dir[-1] != '/':
                    #     fix_test_dir += '/'
                    
                    if "Deleted" in item:
                        print(wrap(red("  - " + fix_test_dir[1:]) + cyan("   *" + str(no_items)) + ' ' * 200)[:-2], end='\r')
                    else:
                        print(wrap(green("  - " + fix_test_dir[1:]) + cyan("   *" + str(no_items)) + ' ' * 200)[:-2], end='\r')
                        
                    continue
                
                
                print()
                no_items = 1
                start_dir = element
                if "Deleted" in item:
                    prRed("  - " + element, end='\r')
                else:
                    prGreen("  - " + element, end='\r')
            print()
    except AttributeError:
        prRed("ATTRIBUTE ERROR !!!")


for _ in range(small_file_threads):
    t = threading.Thread(target=file_worker)
    t.daemon = True
    t.start()

for _ in range(hash_threads):
    t = threading.Thread(target=hash_worker)
    t.daemon = True
    t.start()


def main(action_list = ''):
    
    global errors
    global no_errors
    global retries
    
    if not os.path.exists(documents_path): os.mkdir(documents_path)
    if not os.path.exists(documents_path + file_tree_name): open(documents_path + file_tree_name, "w").close()
    
    os.system('cls')
    init_sync()
    # action_list = ''
    if action_list == '':
        for arg in sys.argv[1:]:
            action_list += arg
        
    while True:
        
        to_upload_len = get_len(to_upload)
        to_upload_removed_len = get_len(to_upload, 'Deleted')
        to_download_len = get_len(to_download)
        to_download_removed_len = get_len(to_download, 'Deleted')

        
        print(f"\nRun with {cyan('s')} argument to start sync immedialety.\n"
        f"There will be {blue(to_upload_len)} upload changes ({red(to_upload_removed_len)} files to remove)"
        f" and {blue(to_download_len)} download changes ({red(to_download_removed_len)} files to remove)."
        f"You can check them in upload.json and download.json in your Documents folder, or press {green('l')}.\n"
        f"Press \t {green('t')} for file_tree update \t {green('r')} to replace file tree with nas \t {green('q')} to quit"
        f" \t {green('c')} to clear sync queue \t {green('l')} to list changed files \t {green('x')} to reload sync"
        f"\t {green('n')} to reload NAS tree \t {green('space')} or {green('s')} to sync\t {green('/')} to skip confirming\n\n"
        f"{blue('r')} causes to update from local disk to NAS\n"
        f"{blue('t')} causes to update from NAS to local disk\n")
        
        if action_list.__len__() == 0:
            action_list = input()
        
        if action_list.__len__() > 0:
            action = action_list[0]
            action_list = action_list[1:]
        else:
            action = 'Nothing selected'
        if action == ' ': action = 's'
            
        prBlue(action)
        time.sleep(0.5)
        
        if action in 'crtqlxn':
            if action == 't':
                if 'left_tree' in globals() or left_tree == None:
                    left_tree = get_contents_with_hashes(src_path)
                update_local_tree(left_tree, documents_path)
                prPurple("SYNC OVERRIDE \t file_tree update")
                print(f"use {blue('x')} option to reload sync")
                
            if action == 'r':
                if 'right_tree' in globals() or right_tree == None:
                    run_nas_script()
                update_local_tree(right_tree, documents_path)
                prPurple("SYNC OVERRIDE \t replace file tree with nas")
                print(f"use {blue('x')} option to reload sync")
                
            if action in 'crt':
                save_changes({}, {})
                prPurple("SYNC OVERRIDE \t clear sync queue")
                print(f"use {blue('x')} option to reload sync")
            
            if action == 'l':
                prBlue("\nTo Upload:")
                list_info(to_upload)
                
                prBlue("\nTo Download:")
                list_info(to_download)
            
            if action == 'n':
                reload_nas_tree()
            
            if action == 'x':
                init_sync()
            
            if action == 'q':
                exit()
            
            time.sleep(1)
            if '/' not in action_list: 
                input(f"\n\nPress {blue('Enter')} to continue")
        
        if action == ' ' or action == 's':
            if to_upload_len + to_download_len > max_operations_without_confirm:
                prYellow(f"\n\nWARNING! There will be {to_upload_len + to_download_len} operations, which is greater than max operations without confirm")
                if input("Confirm? [Y/N]").strip().upper() == 'Y':
                    break
            else:
                break
        
        
        # os.system('cls')
        print('\n' * 50)
        
            
    prGreen('Starting sync')
    time.sleep(1)
    
    atexit.register(exit_save_changes)
    os.system("cls")
    no_errors = True
    
    
    
    save_changes_log(to_upload, to_download)
    
    prBlue("\n   __________  Uploading files  __________")
    errors = 0
    file_operation(to_upload, src_path, nas_path)
    print(errors)
    if errors > 0:
        prYellow("Some errors occured. Retrying operations...")
        file_operation(to_upload, src_path, nas_path)
    if errors > 0:
        prRed("Upload completed with errors. Check upload.json for more details.")
        no_errors = False
        
    
    prBlue("\n   _________  Downloading files  _________")
    errors = 0
    file_operation(to_download, nas_path, src_path)
    print(errors)
    if errors > 0:
        prYellow("Some errors occured. Retrying operations...")
        errors = 0
        file_operation(to_download, nas_path, src_path)
    if errors > 0:
        prRed("Download completed with errors. Check download.json for more details.")
        no_errors = False
    
    
    
    if no_errors:
        update_local_tree(current_formatted_tree, documents_path)
    else:
        if retries < 1:
            retries += 1
            prRed("Clearing local tree and retrying operations...")
            time.sleep(5)
            main('cxs/')
        elif retries < 2:
            retries += 1
            prRed("Clearing NAS tree and retrying operations...")
            time.sleep(5)
            main('cnxs/')
            
        else:
            prYellow("Syncing incomplete. Cannot run next sync before completing this one.")
    
    prGreen(f'\nDone!')
    



if __name__ == "__main__" and mode == "PC":
    main()      
            
if __name__ == "__main__" and mode == "NAS":
    
    print("Setting up file change detection")
    total_updates = 0
    time_from_last_update = 0
    update_log = []
    
    class CustomEventHandler(LoggingEventHandler):        
        def on_any_event(self, event):
            update_log.append(event.src_path)
            
            
    event_handler = CustomEventHandler()
    observer = Observer()
    observer.schedule(event_handler, nas_local_path, recursive=True)
    observer.start()
    
    
    print("Listing file tree...")
    current_formatted_tree = get_contents_with_hashes(nas_local_path, unformatted = False)
    print("Ready for logging!")

    while True:
        if os.path.exists(nas_local_path + file_tree_path + "restart.txt"):
            print("Listing file tree...")
            current_formatted_tree = get_contents_with_hashes(nas_local_path, unformatted = False)
            os.remove(nas_local_path + file_tree_path + "restart.txt")
            print("Ready for logging!")
            
        if os.path.exists(nas_local_path + file_tree_path + "sync.txt"):            
            
            total_updates = 0
            update_local_tree(unformat_dir_tree(current_formatted_tree), nas_local_path + file_tree_path)
            
            os.remove(nas_local_path + file_tree_path + "sync.txt")
            print("Listing done!")
            
            with open("config.json", "r") as config_file:
                config = json.load(config_file)
            src_path = config["SyncPath"].rstrip('/') + '/'
            file_tree_path = config["FileTreePath"].rstrip('/') + '/'
            nas_local_path = config["NasLocalPath"].rstrip('/') + '/'
            forbidden_paths = config["ForbiddenPaths"]
            allowed_paths = config["AllowedPaths"]
            file_tree_name = config["FileTreeName"]
            nas_autosave_delay = config["NasAutoSaveDelay"]
        
        
        update_log_1 = list(set(update_log))
        update_log = update_log_1
        
        for update in update_log:
            if time.time() - last_print_time > 10:
                print(total_updates)
                last_print_time = time.time()
            change = update[nas_local_path.__len__():]
            if os.path.isdir(update): change += "/"
            
            changed = analyse_tree_change(current_formatted_tree, change)
            update_log.remove(update)
            if changed:
                total_updates += 1
                time_from_last_update = 0
        
        if total_updates > 0 and time_from_last_update > nas_autosave_delay:
            total_updates = 0
            update_local_tree(unformat_dir_tree(current_formatted_tree), nas_local_path + file_tree_path)
            
        time_from_last_update += 5
        time.sleep(5)
        