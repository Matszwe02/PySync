import os
import time
from datetime import datetime
import hashlib


src_path = "D:/test/"



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
                contents.append(indent + "-" + element + " /")
                try:
                    contents.extend(get_contents(work_path, recursion + 1))
                except PermissionError:
                    pass

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
        
        if path and path[0] == "$RECYCLE.BIN":
            continue
        
        if is_file:
            elements.append("/".join(path) + "/" + element[1:])
        else:
            elements.append("/".join(path) + "/")
    return elements




print(f'Getting contents... {datetime.now().strftime("%H:%M:%S")}')

current_tree = get_contents(src_path)




print(f'Reading file... {datetime.now().strftime("%H:%M:%S")}')

with open("file_tree.txt", "r", encoding="utf-8") as file_tree:
    previous_tree = file_tree.readlines()


    
    
print(f'Formatting tree... {datetime.now().strftime("%H:%M:%S")}')

left_side = set(format_dir_tree(current_tree))
right_side = set(format_dir_tree(previous_tree))



print(f'Counting differences... {datetime.now().strftime("%H:%M:%S")}')





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




print(f'Summing up and saving differences... {datetime.now().strftime("%H:%M:%S")}')


            

local_create_files = []
local_delete_files = []
copied = []
moved = []
for element in only_left_side_hashes:
    left_elements = only_left_side_hashes.get(element)
    right_elements = only_right_side_hashes.get(element)
    common_elements = common_files_hashes.get(element)
    
    for i, item in enumerate(left_elements):
        if(left_elements.__len__() > i):
            if right_elements and right_elements.__len__() > i:
                moved.append(f'{right_elements[i]} >> {item}')
                local_create_files.append(item)
                local_delete_files.append(right_elements[i])
            
            elif common_elements:
                copied.append(f'{common_elements[0]} >> {item}')
                local_create_files.append(item)
            
print(f'Analyzed copies. Filling everything else... {datetime.now().strftime("%H:%M:%S")}')


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


print(f'Created files: {created.__len__()}')
print(f'Deleted files: {deleted.__len__()}')
print(f'Changed files: {changed.__len__()}')
print(f'Moved files: {moved.__len__()}')
print(f'Copied files: {copied.__len__()}')
print(f'Created directories: {dirs_created.__len__()}')
print(f'Deleted directories: {dirs_deleted.__len__()}')



with open("changes.txt", "w", encoding="utf-8") as changes_file:
    
    
    for item in dirs_created:
        changes_file.write(f'DirCreated {item}\n')
    for item in changed:
        changes_file.write(f'Changed {item}\n')
    for item in created:
        changes_file.write(f'Created {item}\n')
    for item in moved:
        changes_file.write(f'Moved {item}\n')
    for item in copied:
        changes_file.write(f'Copied {item}\n')
    for item in deleted:
        changes_file.write(f'Deleted {item}\n')
    for item in dirs_deleted:
        changes_file.write(f'DirRemoved {item}\n')
        
        
        
print(f'Done! {datetime.now().strftime("%H:%M:%S")}')


with open("file_tree.txt", "w", encoding="utf-8") as file_tree:
    file_tree.write('\n'.join(current_tree))