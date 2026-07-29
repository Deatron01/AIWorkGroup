import os
import shutil
import datetime

# The main repository for the Boss Planner and final merged code
WORKSPACE_DIR = os.path.abspath("./workspace")

def write_file(filename: str, content: str, base_path: str = None) -> str:
    """Writes content to a file within the designated workspace or worktree."""
    active_dir = os.path.abspath(base_path) if base_path else WORKSPACE_DIR
    target_path = os.path.abspath(os.path.join(active_dir, filename))
    
    # Security check to prevent path traversal outside the active directory
    if not target_path.startswith(active_dir):
        return f"Error: Cannot write outside of active directory. Path {filename} is invalid."
    
    try:
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {filename}"
    except Exception as e:
        return f"Error writing to {filename}: {str(e)}"

def read_file(filename: str, base_path: str = None) -> str:
    """Reads content from a file within the designated workspace or worktree."""
    active_dir = os.path.abspath(base_path) if base_path else WORKSPACE_DIR
    target_path = os.path.abspath(os.path.join(active_dir, filename))
    
    # Security check to prevent path traversal outside active directory
    if not target_path.startswith(active_dir):
        return f"Error: Cannot read outside of active directory. Path {filename} is invalid."
        
    if not os.path.exists(target_path):
        return f"Error: File {filename} does not exist."
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filename}: {str(e)}"
    
def list_workspace(base_path: str = None) -> list:
    """Returns a list of all files in the active directory, ignoring git and pycache."""
    active_dir = os.path.abspath(base_path) if base_path else WORKSPACE_DIR
    file_list = []
    
    for root, dirs, files in os.walk(active_dir):
        if ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            # Store paths relative to the active directory
            file_list.append(os.path.relpath(os.path.join(root, file), active_dir))
    return file_list

def archive_workspace(files_to_archive: list = None) -> str:
    """
    Archives specific files or the entire main workspace to an archive directory.
    Strictly operates on the main WORKSPACE_DIR (used by Boss Phase 0 Triage).
    """
    archive_dir = os.path.abspath("./workspace_archive")
    os.makedirs(archive_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_archive_dir = os.path.join(archive_dir, f"run_{timestamp}")
    
    try:
        os.makedirs(run_archive_dir, exist_ok=True)
        
        if files_to_archive:
            # Archive only the specified irrelevant files
            for file_path in files_to_archive:
                src = os.path.join(WORKSPACE_DIR, file_path)
                if os.path.exists(src):
                    # Maintain directory structure inside the archive
                    dst_dir = os.path.join(run_archive_dir, os.path.dirname(file_path))
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.move(src, os.path.join(run_archive_dir, file_path))
            return f"Successfully archived {len(files_to_archive)} files to {run_archive_dir}"
        else:
            # Blanket archive of everything (except .git) if no specific list is given
            count = 0
            for item in os.listdir(WORKSPACE_DIR):
                if item == ".git" or item == "__pycache__":
                    continue
                src = os.path.join(WORKSPACE_DIR, item)
                shutil.move(src, os.path.join(run_archive_dir, item))
                count += 1
            return f"Successfully archived {count} items from workspace to {run_archive_dir}"
    except Exception as e:
        return f"Error archiving workspace: {str(e)}"