import os
import shutil
import time
from datetime import datetime
import hashlib
import threading
import runpy
import json
try:
    from tqdm import tqdm
except:
    pass
import atexit
import copy



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

if not os.path.exists(file_tree_name):
    open(file_tree_name, 'a').close()



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


def get_contents(path, recursion=0):
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

            # If the entry is a directory, append its name to the contents
            # and recursively get its contents
            if is_dir:
                if (recursion > 0 or ((not element in forbidden_paths) and ((element + '/') in allowed_paths or '*' in allowed_paths))):
                    contents.append(indent + "-" + element + " /")
                    try:
                        contents.extend(get_contents(work_path, recursion + 1))
                    except PermissionError:
                        print("PERMISSION ERROR WHILE CREATING " + element)

            # If the entry is a file, get its last modification time
            else:
                # Use the stat() method to get the last modification time
                # and size of the file in a single call
                file_stat = os.stat(work_path)
                file_time = file_stat.st_mtime
                file_size = file_stat.st_size

                prehash_str = bytearray((str(file_size) + "&" + str(file_time)).encode("utf-8"))
                file_hash = str(hashlib.sha256(prehash_str).hexdigest())[-16:]
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
    print("Saved session changes")


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
    
    changes_save = copy.deepcopy(changes)
    
    for item in tqdm(sorted(changes_save["DirCreated"]), "DirCreated"):
        try:
            os.mkdir(to_path + item)
            changes["DirCreated"].remove(item)
        except FileExistsError:
            print(f"FILE EXISTS", end=' ')
            print(to_path + item)
            changes["DirCreated"].remove(item)
            pass
        except FileNotFoundError:
            print(f"FILE NOT FOUND CRITICAL", end=' ')
            print(to_path + item)
            changes["DirCreated"].remove(item)
    
    
    for item in tqdm(changes_save["Created"], "Created"):
        item1 = remove_file_hash(item)
        try:
            shutil.copy2(from_path + item1, to_path + item1)
            changes["Created"].remove(item)
        except PermissionError:
            print(" PERMISSION ERROR WITH FILE " + item1)
                
    for item in tqdm(changes_save["Changed"], "Changed"):
        item1 = remove_file_hash(item)
        shutil.copy2(from_path + item1, to_path + item1)
        changes["Changed"].remove(item)
    
    for item in tqdm(changes_save["Moved"], "Moved"):
        files = split_move_copy(item)
        shutil.move(to_path + files[0], to_path + files[1]) # FIXME: 
        changes["Moved"].remove(item)
    
    for item in tqdm(changes_save["Copied"], "Copied"):
        files = split_move_copy(item)
        shutil.copy2(to_path + files[0], to_path + files[1])
        changes["Copied"].remove(item)
    
    for item in tqdm(changes_save["Deleted"], "Deleted"):
        item1 = remove_file_hash(item)
        try:
            os.remove(to_path + item1)
            changes["Deleted"].remove(item)
        except PermissionError:
            pass
    
    for item in tqdm(sorted(changes_save["DirDeleted"], reverse=True), "DirDeleted"):
        # item = remove_file_hash(item)
        try:
            os.rmdir(to_path + item)
            changes["DirDeleted"].remove(item)
        except:
            pass


if __name__ == "__main__" and mode == "PC":

    print(f'start! {datetime.now().strftime("%H:%M:%S")}')
    resume = False
    # try:
    #     to_download = load_changes("download.json")
    #     to_upload = load_changes("upload.json")
    # except:
    #     to_download = {}
    #     to_upload = {}
    # for key in to_download.keys():
    #     if to_download[key].__len__() > 0:
    #         resume = True
    # for key in to_upload.keys():
    #     if to_upload[key].__len__() > 0:
    #         resume = True
                
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
        to_download = list_changes(right_tree, current_files_tree)
        to_upload = list_changes(current_files_tree, left_tree)
    
    else:
        print("resuming actions...")
    # print(current_files_tree)
    # print(left_tree)
    # print(right_tree)

    save_changes(to_upload, "upload.json")
    save_changes(to_download, "download.json")
    
    atexit.register(exit_save_changes)
    
    if config["DownloadOnly"] == False:
        print("Uploading files...")
        file_operation(to_upload, src_path, nas_path)
    else:
        print("skipping uploading files")
    
    print("Downloading files...")
    file_operation(to_download, nas_path, src_path)
    
    # except FileNotFoundError:
    #     print("ERROR during sync")
    #     atexit.unregister(exit_save_changes)
    #     save_changes({}, "upload.json")
    #     save_changes({}, "download.json")
        
        
    # atexit.unregister(exit_save_changes)
    
    current_files_tree = get_contents(src_path)     
    update_local_tree(current_files_tree)
            
    print(f'Done! {datetime.now().strftime("%H:%M:%S")}')


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