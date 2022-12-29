import os
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



with open("config.json", "r") as config_file:
    config = json.load(config_file)


mode = config["Mode"]
src_path = config["SyncPath"]
if src_path[-1] != '/':
    src_path += "/"
nas_path = config["NasPath"]
if nas_path[-1] != '/':
    nas_path += "/"
file_tree_path = config["FileTreePath"]
if file_tree_path[-1] != '/':
    file_tree_path += "/"
    
forbidden_paths = config["ForbiddenPaths"]
allowed_paths = config["AllowedPaths"]
file_tree_name = config["FileTreeName"]
last_list_threshold = config["LastListThreshold"]
large_file_size = config["LargeFileSize"]
small_file_threads = config["SmallFileThreads"]

task_queue = queue.Queue()
errors = 0

if not os.path.exists(file_tree_name):
    open(file_tree_name, 'a').close()
    
    
def prRed(skk): print("\033[91m{}\033[00m".format(skk))
def prGreen(skk): print("\033[92m{}\033[00m".format(skk))
def prYellow(skk): print("\033[93m{}\033[00m".format(skk))
def prBlue(skk): print("\033[94m{}\033[00m".format(skk))
def prPurple(skk): print("\033[95m{}\033[00m".format(skk))
def prCyan(skk): print("\033[96m{}\033[00m".format(skk))
def prLightGray(skk): print("\033[97m{}\033[00m".format(skk))
def prBlack(skk): print("\033[98m{}\033[00m".format(skk))


def file_action(action_info):
    global errors
    item = action_info["item"]
    src_path = action_info["src"]
    dst_path = action_info["dst"]
    tq = action_info["tqdmInstance"]
    action = action_info["Action"]
    changes = action_info["Changes"]
    try:
        if action == "Copy":
            item1 = remove_file_hash(item)
            shutil.copy2(src_path + item1, dst_path + item1)
            tq.update()
        
        if action == "Delete":
            item1 = remove_file_hash(item)
            os.remove(dst_path + item1)
            tq.update()
            
        changes.remove(item)
    except Exception as e:
        prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {src_path + item}')
        errors += 1
        time.sleep(0.5)
        tq.update()


def worker():
  while True:
    work = task_queue.get()
    if work is None:
      # Sentinel value reached, break the loop
      break
    file_action(work)
    task_queue.task_done()


def update_nas_tree():
    with open(nas_path + file_tree_path + "sync.txt", "w") as f:
        f.write(" ")
    
    time.sleep(2)
    print("waiting for NAS script...")
    while os.path.exists(nas_path + file_tree_path + "sync.txt"):
        time.sleep(1)
    print("Getting NAS filetree...")
    get_nas_tree() 
    print("NAS filetree download complete")


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
                file_hash = (str(hashlib.sha256(prehash_str).hexdigest()) + size)[-16:]
                contents.append(indent + "-" + element + " " + file_hash)

    return contents


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


def load_changes(path : str):
    with open(path, "r", encoding="utf-8") as changes_file:
        changes_list = json.load(changes_file)
    return changes_list


def save_changes(changes_list : dict, path: str):
    with open(path, "w", encoding="utf-8") as changes_file:
        json.dump(changes_list, changes_file)


def exit_save_changes():
    global to_upload, to_download
    save_changes(to_upload, "upload.json")
    save_changes(to_download, "download.json")
    prGreen("Saved session changes")


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


def update_local_tree(local_tree : list, path = ""):
    global file_tree_name
    with open(path + file_tree_name, "w", encoding="utf-8") as file_tree:
        file_tree.write('\n'.join(local_tree))


def remove_file_hash(name : str):
    return name[:-17]


def split_move_copy(command: str):
    sides = command.split(' >> ')
    return [remove_file_hash(sides[0]), remove_file_hash(sides[1])]


def file_operation(changes : dict, from_path: str, to_path: str):
    global errors
    
    global large_file_size
    changes_1 = copy.deepcopy(changes)
    
    for item in tqdm(sorted(changes_1["DirCreated"]), "DirCreated", colour = "CYAN"):
        try:
            os.mkdir(to_path + item)
        except FileExistsError:
            prYellow(f"FILE EXISTS")
            print(to_path + item)
        except FileNotFoundError:
            prRed(f"FILE NOT FOUND CRITICAL")
            print(to_path + item)
        changes["DirCreated"].remove(item)
    
    
    
    small_files = []
    large_files = []
    for item in changes_1["Created"]:
        if int(item[-1], 16) >= large_file_size:
            large_files.append(item)
        else:
            small_files.append(item)
    
    with tqdm(total = small_files.__len__(), desc="Created SmallFiles", colour = "CYAN") as tq:
        for item in small_files:
            task_queue.put({"Action" : "Copy", "src" : from_path, "dst" : to_path, "item" : item, "tqdmInstance" : tq, "Changes" : changes["Created"]})
        
        task_queue.join()
    
    for item in tqdm(large_files, "Created LargeFiles", colour = "CYAN"):
        item1 = remove_file_hash(item)
        try:
            shutil.copy2(from_path + item1, to_path + item1)
            changes["Created"].remove(item)
        except Exception as e:
            prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
            time.sleep(0.5)
            errors += 1
    
    
    small_files = []
    large_files = []
    for item in changes_1["Changed"]:
        if int(item[-1], 16) >= large_file_size:
            large_files.append(item)
        else:
            small_files.append(item)
    
    with tqdm(total = small_files.__len__(), desc="Changed SmallFiles", colour = "CYAN") as tq:
        for item in small_files:
            task_queue.put({"Action" : "Copy", "src" : from_path, "dst" : to_path, "item" : item, "tqdmInstance" : tq, "Changes" : changes["Changed"]})
        
        task_queue.join()
                
    for item in tqdm(large_files, "Changed LargeFiles", colour = "CYAN"):
        item1 = remove_file_hash(item)
        try:
            shutil.copy2(from_path + item1, to_path + item1)
            changes["Changed"].remove(item)
        except Exception as e:
            prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
            time.sleep(0.5)
            errors += 1
    
    
    for item in tqdm(changes_1["Moved"], "Moved", colour = "CYAN"):
        files = split_move_copy(item)
        try:
            shutil.move(to_path + files[0], to_path + files[1]) # FIXME: 
            changes["Moved"].remove(item)
        except Exception as e:
            prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
            time.sleep(0.5)
            errors += 1
    
    for item in tqdm(changes_1["Copied"], "Copied", colour = "CYAN"):
        files = split_move_copy(item)
        try:
            shutil.copy2(to_path + files[0], to_path + files[1])
            changes["Copied"].remove(item)
        except Exception as e:
            prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
            time.sleep(0.5)
            errors += 1
            
    
    
    with tqdm(total = changes_1["Deleted"].__len__(), desc="Deleted", colour = "CYAN") as tq:
        for item in changes_1["Deleted"]:
            task_queue.put({"Action" : "Delete", "src" : from_path, "dst" : to_path, "item" : item, "tqdmInstance" : tq, "Changes" : changes["Deleted"]})
        task_queue.join()
    
    # for item in tqdm(changes["Deleted"], "Deleted", colour = "CYAN"):
    #     item1 = remove_file_hash(item)
    #     try:
    #         os.remove(to_path + item1)
    #     except Exception as e 
    # prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')PermissionError:
    #         pass
    
    for item in tqdm(sorted(changes_1["DirDeleted"], reverse=True), "DirDeleted", colour = "CYAN"):
        # item = remove_file_hash(item)
        try:
            os.rmdir(to_path + item)
            changes["DirDeleted"].remove(item)
        except Exception as e:
            prRed(f'\r{" " * 200}\r ERROR {type(e).__name__}  With file : {from_path + item}')
            time.sleep(0.5)
            errors += 1




if __name__ == "__main__" and mode == "PC":

    print(f'start! {datetime.now().strftime("%H:%M:%S")}')
    resume = False
    
    for _ in range(small_file_threads):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
    
    
    try:
        to_download = load_changes("download.json")
        to_upload = load_changes("upload.json")
    except:
        to_download = {}
        to_upload = {}
    for key in to_download.keys():
        if to_download[key].__len__() > 0:
            resume = True
    for key in to_upload.keys():
        if to_upload[key].__len__() > 0:
            resume = True
    
    tu_len = 0
    td_len = 0
    
    if not resume:
        
        print("Not resuming")
        
        nas_contents = []
        thread = threading.Thread(target=update_nas_tree)
        thread.start()

        current_files_tree = get_contents(src_path)
        left_tree = get_local_tree()
        thread.join()
        right_tree = nas_contents


        # to_download = list_changes(right_tree, left_tree)
        to_upload = list_changes(current_files_tree, left_tree)
            
        to_download = list_changes(right_tree, left_tree)
    
    else:
        print("resuming previous sync")
        
    
    
    for key in to_upload:
        tu_len += to_upload[key].__len__()
    for key in to_download:
        td_len += to_download[key].__len__()


    save_changes(to_upload, "upload.json")
    save_changes(to_download, "download.json")
    
    atexit.register(exit_save_changes)
    
    prCyan(f'There will be {tu_len} upload changes and {td_len} download changes.\nYou can check them in upload.json and download.json.')
    print("Press \t 't' for file_tree update \t 'r' to replace file tree with nas \t 'q' to quit \t 'c' to clear sync queue \t anything else to sync\n")
    action = str(msvcrt.getch())[2]
    print(action)
    
    if action in ['t', 'r', 'c', 'q']:
        if action == 't':
            update_local_tree(current_files_tree)
            prPurple("SYNC OVERRIDE \t file_tree update")
        if action == 'r':
            update_local_tree(nas_contents)
            prPurple("SYNC OVERRIDE \t replace file tree with nas")
        if action == 'c':
            save_changes({}, "upload.json")
            save_changes({}, "download.json")
            prPurple("SYNC OVERRIDE \t clear sync queue")
        if action == 'q':
            pass
        atexit.unregister(exit_save_changes)
        exit()
    
    os.system("cls")
    no_errors = True
    
    if config["DownloadOnly"] == False:
        prBlue("\n   __________  Uploading files  __________")
        errors = 0
        file_operation(to_upload, src_path, nas_path)
        if errors > 0:
            prYellow("Some errors occured. Retrying operations...")
            file_operation(to_upload, src_path, nas_path)
        if errors > 0:
            prRed("Upload completed with errors. Check upload.json for more details.")
            no_errors = False
    else:
        print("skipping uploading files")
        
    
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
    
    # except FileNotFoundError:
    #     print("ERROR during sync")
    #     atexit.unregister(exit_save_changes)
    #     save_changes({}, "upload.json")
    #     save_changes({}, "download.json")
        
        
    # atexit.unregister(exit_save_changes)
    
    print(f'\nDone!')
    
    if no_errors:
        update_local_tree(get_contents(src_path))
    else:
        prYellow("Syncing incomplete. Cannot run next sync before completing this one.")
            


if __name__ == "__main__" and mode == "NAS":
    while True:
        if os.path.exists(src_path + file_tree_path + "sync.txt"):
            if (time.time() - os.path.getmtime(file_tree_name)) > last_list_threshold:
                print("Listing file tree...")
                current_files_tree = get_contents(src_path)
                update_local_tree(current_files_tree, src_path + file_tree_path)
                
            os.remove(src_path + file_tree_path + "sync.txt")
            print("Listing done!")
        time.sleep(1)