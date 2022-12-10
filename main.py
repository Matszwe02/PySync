import os
import time
from datetime import datetime
import hashlib



src_path = "D:/"




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



def get_contents2(path, recursion=0):
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
                    contents.extend(get_contents2(work_path, recursion + 1))
                except PermissionError:
                    pass

            # If the entry is a file, get its last modification time, size,
            # and hash, and append them to the contents
            else:
                # Use the stat() method to get the last modification time
                # and size of the file in a single call
                file_stat = os.stat(work_path)
                file_time = file_stat.st_mtime
                file_size = file_stat.st_size
                file_creation = file_stat.st_ctime

                # Use a bytearray instead of a bytes object to create
                # the prehash_str variable
                prehash_str = bytearray(f'{file_size}&{file_time}&{file_creation}'.encode("utf-8"))
                file_hash = str(hashlib.sha256(prehash_str).hexdigest())[-16:]
                contents.append(indent + "-" + element + " " + file_hash)

    return contents



timestamp = datetime.now()
formatted_timestamp = timestamp.strftime("%H:%M:%S.") + timestamp.strftime("%f")[:2]
print(f'Getting contents... {formatted_timestamp}')

current_tree = get_contents2(src_path)

# current_tree = "\n".join(contents)
# current_tree_list = current_tree.split('\n')

timestamp = datetime.now()
formatted_timestamp = timestamp.strftime("%H:%M:%S.") + timestamp.strftime("%f")[:2]
print(f'Reading file... {formatted_timestamp}')

with open("file_tree.txt", "r", encoding="utf-8") as file_tree:
    previous_tree = file_tree.readlines()


# with open("file_tree.txt", "w", encoding="utf-8") as file_tree:
#     file_tree.write('\n'.join(current_tree))
    
timestamp = datetime.now()
formatted_timestamp = timestamp.strftime("%H:%M:%S.") + timestamp.strftime("%f")[:2]
print(f'Formatting tree... {formatted_timestamp}')

newtree = set(format_dir_tree(current_tree))
prevtree = set(format_dir_tree(previous_tree))


timestamp = datetime.now()
formatted_timestamp = timestamp.strftime("%H:%M:%S.") + timestamp.strftime("%f")[:2]
print(f'Counting differences... {formatted_timestamp}')

prev_path = []
curr_path = []
i = 0

# all_tree = prevtree.union(newtree)
# t1 = list(all_tree.difference(newtree))
# t2 = list(all_tree.difference(prevtree))

tree1 = prevtree.difference(newtree)
tree2 = newtree.difference(prevtree)
trees = newtree.intersection(prevtree)


t1names = []
for item in tree1:
    t1names.append(item[:-17])
t1names = set(t1names)
t2names = []
for item in tree2:
    t2names.append(item[:-17])
t2names = set(t2names)

t1hashes = []
for item in tree1:
    t1hashes.append(item[-16:])
t1hashes = set(t1hashes)
t2hashes = []
for item in tree2:
    t2hashes.append(item[-16:])
t2hashes = set(t2hashes)


timestamp = datetime.now()
formatted_timestamp = timestamp.strftime("%H:%M:%S.") + timestamp.strftime("%f")[:2]
print(f'Summing up and saving differences... {formatted_timestamp}')

deleted = t1names.difference(t2names)
created = t2names.difference(t1names)
changed = t1names.intersection(t2names)
moved = t1hashes.intersection(t2hashes)
copied = created.intersection(trees)

with open("changes.txt", "w", encoding="utf-8") as changes_file:
    
    
    for item in list(deleted):
        file_str = f'{item}'
        changes_file.write(f'Deleted {file_str}\n')
        
    for item in list(created):
        file_str = f'{item}'
        changes_file.write(f'Created {file_str}\n')
    
    for item in list(changed):
        file_str = f'{item}'
        changes_file.write(f'Changed {file_str}\n')
    
    for item in list(moved):
        file_str = f'{item}'
        changes_file.write(f'Moved {file_str}\n')
        
        
timestamp = datetime.now()
formatted_timestamp = timestamp.strftime("%H:%M:%S.") + timestamp.strftime("%f")[:2]
print(f'Done! {formatted_timestamp}')

