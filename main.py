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
try:
    from tqdm import tqdm
    import msvcrt
except:
    pass
import atexit
import copy
import concurrent.futures
import base64
import math


with open("config.json", "r") as config_file:
    config = json.load(config_file)



src_path = config["SyncPath"].rstrip('/') + '/'
file_tree_path = config["FileTreePath"].rstrip('/') + '/'
nas_path = False
nas_detection_timeout = config["NasDetectionTimeout"]
nas_local_path = config["NasLocalPath"].rstrip('/') + '/'
forbidden_paths = config["ForbiddenPaths"]
allowed_paths = config["AllowedPaths"]
file_tree_name = config["FileTreeName"]
last_list_threshold = config["LastListThreshold"]
large_file_size = config["LargeFileSize"]
small_file_threads = config["SmallFileThreads"]
task_queue = queue.Queue()
hash_queue = queue.Queue()

errors = 0

mode = 'PC'
if os.path.split(os.getcwd())[-1] + '/' == file_tree_path:
    mode = 'NAS'




# FIXME: Better function naming
    
    
def prRed(skk): print("\033[91m{}\033[00m".format(skk))
def prGreen(skk): print("\033[92m{}\033[00m".format(skk))
def prYellow(skk): print("\033[93m{}\033[00m".format(skk))
def prBlue(skk): print("\033[94m{}\033[00m".format(skk))
def prPurple(skk): print("\033[95m{}\033[00m".format(skk))
def prCyan(skk): print("\033[96m{}\033[00m".format(skk))
def prLightGray(skk): print("\033[97m{}\033[00m".format(skk))
def prBlack(skk): print("\033[98m{}\033[00m".format(skk))

    
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
    
    file_stat = os.stat(path[1] + path[0])
    file_time = file_stat.st_mtime
    file_size = file_stat.st_size
    
    size = str(hex(str(file_size).__len__()))[-1]
    prehash_str = bytearray((str(file_size) + "&" + str(file_time)).encode("utf-8"))
    file_hash = ((hashlib.sha256(prehash_str).digest()))
    encoded_hash = (str(base64.urlsafe_b64encode(file_hash))[2:-2] + size)[-16:]
    hashed_files.append(path[0] + " " + encoded_hash)

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
    print("Listing NAS files...")
    update_nas_config()
    with open(nas_path + file_tree_path + "sync.txt", "w") as f:
        f.write(" ")
    
    time.sleep(2)
    while os.path.exists(nas_path + file_tree_path + "sync.txt"):
        time.sleep(1)
    get_nas_tree() 
    prGreen("NAS fileTree download complete")

# DEPRECATED
def get_contents(path, local_path = "", recursion=0):
    contents = []
    indent = " " * recursion

    # Use os.scandir() to iterate over the contents of the directory
    with os.scandir(path) as entries:
        for entry in entries:
            # Get the name and type of the entry
            element = entry.name
            is_dir = entry.is_dir()

            # Construct the full path of the entry
            work_path = os.path.join(path, element)
            local_path_1 = os.path.join(local_path, element).replace("\\", "/")
            # If the entry is a directory, append its name to the contents
            # and recursively get its contents
            if is_dir:
                if (recursion > 0 or ((not element in forbidden_paths) and ((element + '/') in allowed_paths or '*' in allowed_paths))):
                    if local_path_1 + '/' in forbidden_paths:
                        continue
                    contents.append(indent + "-" + element + " /")
                    try:
                        contents.extend(get_contents(work_path, local_path_1, recursion + 1))
                    except PermissionError:
                        print("PERMISSION ERROR WHILE CREATING " + element)

            # If the entry is a file, get its last modification time
            else:
                # Use the stat() method to get the last modification time
                # and size of the file in a single call
                file_stat = os.stat(work_path)
                file_time = file_stat.st_mtime
                file_size = file_stat.st_size
                
                size = str(hex(str(file_size).__len__()))[-1]
                prehash_str = bytearray((str(file_size) + "&" + str(file_time)).encode("utf-8"))
                file_hash = ((hashlib.sha256(prehash_str).digest()))
                encoded_hash = (str(base64.urlsafe_b64encode(file_hash))[2:-2] + size)[-16:]
                contents.append(indent + "-" + element + " " + encoded_hash)
    
    return contents

# TODO: optimization for HDD
hashed_files = []
def get_contents_2(path):
    global hashed_files
    contents = []
    time_start = time.time()
    for (root, dirs, files) in os.walk(path):
        common_path = os.path.relpath(root, path).replace('\\', '/').rstrip("/") + "/"
        
        if ((not common_path.split('/')[0] in forbidden_paths) and (common_path.split('/')[0] in allowed_paths or '*' in allowed_paths)):
        
            for file in files:
                file = (common_path.replace('\\', '/').rstrip('/') + '/' + file)
                if file.startswith("./"): file = file[2:]
                hash_queue.put([file, path])
            for dir in dirs:
                content = (common_path.replace('\\', '/').rstrip('/') + '/' +  dir.replace('\\', '/').rstrip('/') + '/')
                if content.startswith("./"): content = content[2:]
                if ((not content.split('/')[0] in forbidden_paths) and (content.split('/')[0] in allowed_paths or '*' in allowed_paths)):
                    contents.append(content)
    
    
    print(f'took {time.time() - time_start} s to list files')
    time_start = time.time()
    hash_queue.join()
    print(f'took {time.time() - time_start} s to hash files')
    contents.extend(hashed_files)
    contents = sorted(contents)
    contents = unformat_dir_tree(contents)
    return contents
    

def get_trees_async():
    time_start = time.time()
    global nas_contents, left_tree, right_tree, common_tree
    nas_contents = []
    thread = threading.Thread(target=run_nas_script)
    thread.start()
    print("Listing local files...")
    left_tree = get_contents_2(src_path)
    
    prGreen("Local listing complete")
    # exit()
    common_tree = get_local_tree()
    thread.join()
    right_tree = nas_contents
    print(f'Total time: {time.time() - time_start}')
    return left_tree, right_tree, common_tree


# TODO: compare to_upload with right_tree and to_download with left_tree to prevent FILE_EXISTS exceptions
def get_changes(left_tree, right_tree, common_tree):
    to_upload = list_changes(left_tree, common_tree)
    to_download = list_changes(right_tree, common_tree)
    return to_upload, to_download


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
    # elements = sorted(elements)
    lines = []
    for element in elements:
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


def get_len(dictionary: dict, condition = ''): return sum(len(v) for k, v in dictionary.items() if condition in k)


def load_changes():
    try:
        with open("upload.json", "r", encoding="utf-8") as changes_file:
            to_upload = json.load(changes_file)
        with open("download.json", "r", encoding="utf-8") as changes_file:
            to_download = json.load(changes_file)
        return to_upload, to_download
    except:
        return {}, {}
    
    
def save_changes(to_upload, to_download):
    with open("upload.json", "w", encoding="utf-8") as changes_file:
        json.dump(to_upload, changes_file)
    with open("download.json", "w", encoding="utf-8") as changes_file:
        json.dump(to_download, changes_file)


def exit_save_changes():
    global to_upload, to_download
    save_changes(to_upload, to_download)
    if get_len(to_upload) + get_len(to_download) > 0:
        prYellow("Saved session changes")


def get_nas_tree():
    global file_tree_name, nas_contents, nas_path, file_tree_path
    with open(nas_path + file_tree_path + file_tree_name, "r", encoding="utf-8") as file_tree:
        nas_contents = file_tree.readlines()
    for i in range(nas_contents.__len__()):
        nas_contents[i] = nas_contents[i].removesuffix("\n")


def get_local_tree():
    global file_tree_name
    with open(file_tree_name, "r", encoding="utf-8") as file_tree:
        contents = file_tree.readlines()
        for i in range(contents.__len__()):
            contents[i] = contents[i].removesuffix("\n")
    return contents

# TODO: update tree with every sync file to prevent issues with modified files during sync
def update_local_tree(local_tree : list, path = ""):
    global file_tree_name
    with open(path + file_tree_name, "w", encoding="utf-8") as file_tree:
        file_tree.write('\n'.join(local_tree))


def remove_file_hash(name : str): return name[:-17]
def split_move_copy(command: str): return [remove_file_hash(sides) for sides in command.split(' >> ')]


def file_operation(changes : dict, from_path: str, to_path: str):
    global errors
    
    global large_file_size
    changes_1 = copy.deepcopy(changes)
    
    with tqdm(total=changes_1["DirCreated"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(sorted(changes_1["DirCreated"]), "DirCreated", unit='files', position=0, colour="BLUE"):
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
        with tqdm(total = small_files.__len__(), desc="Created SmallFiles", unit='files', position=0, colour="BLUE") as tq:
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
        
    
    
    with tqdm(total=large_files.__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(large_files, "Created LargeFiles", unit='files', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            item1 = remove_file_hash(item)
            try:
                shutil.copy2(from_path + item1, to_path + item1)
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
        with tqdm(total = small_files.__len__(), desc="Changed SmallFiles", unit='files', position=0, colour="BLUE") as tq:
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
        
        
             
    with tqdm(total=large_files.__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(large_files, "Changed LargeFiles", unit='files', position=0, colour="BLUE"):
            desc.set_description_str(wrap("    " + (item)))
            item1 = remove_file_hash(item)
            try:
                shutil.copy2(from_path + item1, to_path + item1)
                changes["Changed"].remove(item)
            except Exception as e:
                prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
                time.sleep(0.5)
                errors += 1
        desc.set_description_str(wrap(" " * 500), refresh=True)
        
        
    
    with tqdm(total=changes_1["Moved"].__len__() + 10, desc = " ", bar_format='{desc}', position=1) as desc:
        for item in tqdm(changes_1["Moved"], "Moved", unit='files', position=0, colour="BLUE"):
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
        for item in tqdm(changes_1["Copied"], "Copied", unit='files', position=0, colour="BLUE"):
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
        with tqdm(total = changes_1["Deleted"].__len__(), desc="Deleted", unit='files', position=0, colour="BLUE") as tq:
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
        for item in tqdm(sorted(changes_1["DirDeleted"], reverse=True), "DirDeleted", unit='files', position=0, colour="BLUE"):
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
    global current_files_tree, nas_contents, to_upload, to_download, nas_contents, nas_path
    
    nas_path = check_nas_paths()
    
    if nas_path == False:
        prRed("Network Drive not found in any of selected paths!")
        exit()
    
    if not os.path.exists(file_tree_name):
        open(file_tree_name, 'a').close()
    
    to_upload, to_download = load_changes()
    
    # current_files_tree = None
    # nas_contents = None
    
    if get_len(to_upload) + get_len(to_download) > 0:
        prYellow("resuming previous sync")
    else:
        left_tree, right_tree, common_tree = get_trees_async()
        to_upload, to_download = get_changes(left_tree, right_tree, common_tree)
    
    save_changes(to_upload, to_download)



for _ in range(small_file_threads):
    t = threading.Thread(target=file_worker)
    t.daemon = True
    t.start()

for _ in range(4):
    t = threading.Thread(target=hash_worker)
    t.daemon = True
    t.start()


if __name__ == "__main__" and mode == "PC":
    
    os.system('cls')
    
    init_sync()
    
    to_upload_len = get_len(to_upload)
    to_upload_removed_len = get_len(to_upload, 'Deleted')
    to_download_len = get_len(to_download)
    to_download_removed_len = get_len(to_download, 'Deleted')

    
    print(f"\nRun with {cyan('--sync')} argument to start sync immedialety.\n"
    f"There will be {blue(to_upload_len)} upload changes ({red(to_upload_removed_len)} files to remove)"
    f" and {blue(to_download_len)} download changes ({red(to_download_removed_len)} files to remove)."
    f"You can check them in upload.json and download.json.\n"
    f"Press \t {green('t')} for file_tree update \t {green('r')} to replace file tree with nas \t {green('q')} to quit"
    f" \t {green('c')} to clear sync queue \t {green('space')} to sync\n\n"
    f"{blue('r')} causes to update from local disk to NAS\n"
    f"{blue('t')} causes to update from NAS to local disk\n")
    
    
    if sys.argv.__len__() > 1 and sys.argv[1] == '--sync': action = ' '
    else: action = str(msvcrt.getch())[2]
    prBlue(action)
    time.sleep(0.5)
    
    if action in 'crtq':
        if action == 't':
            if left_tree == None:
                left_tree = get_contents(src_path)
            update_local_tree(left_tree)
            prPurple("SYNC OVERRIDE \t file_tree update")
            
        if action == 'r':
            if right_tree == None:
                run_nas_script()
            update_local_tree(right_tree)
            prPurple("SYNC OVERRIDE \t replace file tree with nas")
            
        if action in 'crt':
            save_changes({}, {})
            prPurple("SYNC OVERRIDE \t clear sync queue")
            
        if action in 'rt':
            to_upload, to_download = get_changes(left_tree, right_tree, common_tree)
            save_changes(to_upload, to_download)
            
        if action == 'q':
            pass
        exit()
    
    if action != ' ':
        exit()
    prGreen('Starting sync')
    time.sleep(1)
    
    atexit.register(exit_save_changes)
    os.system("cls")
    no_errors = True
    
    
    prBlue("\n   __________  Uploading files  __________")
    errors = 0
    file_operation(to_upload, src_path, nas_path)
    if errors > 0:
        prYellow("Some errors occured. Retrying operations...")
        file_operation(to_upload, src_path, nas_path)
    if errors > 0:
        prRed("Upload completed with errors. Check upload.json for more details.")
        no_errors = False
        
    
    prBlue("\n   _________  Downloading files  _________")
    errors = 0
    file_operation(to_download, nas_path, src_path)
    if errors > 0:
        prYellow("Some errors occured. Retrying operations...")
        errors = 0
        file_operation(to_download, nas_path, src_path)
    if errors > 0:
        prRed("Download completed with errors. Check download.json for more details.")
        no_errors = False
    
    
    prGreen(f'\nDone!')
    
    if no_errors:
        update_local_tree(get_contents(src_path))
    else:
        prYellow("Syncing incomplete. Cannot run next sync before completing this one.")
            


if __name__ == "__main__" and mode == "NAS":
    while True:
        if os.path.exists(nas_local_path + file_tree_path + "sync.txt"):
            
            with open("config.json", "r") as config_file:
                config = json.load(config_file)
            src_path = config["SyncPath"].rstrip('/') + '/'
            file_tree_path = config["FileTreePath"].rstrip('/') + '/'
            nas_local_path = config["NasLocalPath"].rstrip('/') + '/'
            forbidden_paths = config["ForbiddenPaths"]
            allowed_paths = config["AllowedPaths"]
            file_tree_name = config["FileTreeName"]
            last_list_threshold = config["LastListThreshold"]
            
            
            if (time.time() - os.path.getmtime(file_tree_name)) > last_list_threshold:
                print("Listing file tree...")
                current_files_tree = get_contents_2(nas_local_path)
                update_local_tree(current_files_tree, nas_local_path + file_tree_path)
                
            os.remove(nas_local_path + file_tree_path + "sync.txt")
            print("Listing done!")
        time.sleep(1)
        