import os

def create_directories(path):
    try:
        os.makedirs(path)
        print(f"Directories created successfully: {path}")
    except FileExistsError:
        print(f"Directories already exist: {path}")
    except OSError as e:
        print(f"Error creating directories: {e}")
