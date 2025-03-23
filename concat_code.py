import os

def gather_files(root, extension, exclude_dirs=None, exclude_files=None):
    """
    Recursively search for files with the given extension in root,
    skipping directories in exclude_dirs and files in exclude_files.
    """
    if exclude_dirs is None:
        exclude_dirs = set()
    if exclude_files is None:
        exclude_files = set()

    collected = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Modify dirnames in-place to skip excluded directories.
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for filename in filenames:
            if filename in exclude_files:
                continue
            if filename.endswith(extension):
                collected.append(os.path.join(dirpath, filename))
    return collected

def main():
    # Set your root directory (project root) and templates directory.
    root_dir = "."
    templates_dir = os.path.join(root_dir, "templates")
    output_file = os.path.join("instance", "combined_codebase.txt")
    
    # Files or directories to exclude for .py files
    exclude_py_dirs = {"templates", "static", "instance" , "venv" , "migrations"}
    exclude_py_files = {"concat_code.py" , "coder.py"}  # update as needed

    # 1. Gather all .py files recursively in the project, excluding certain directories/files
    py_files = gather_files(root_dir, ".py", exclude_dirs=exclude_py_dirs, exclude_files=exclude_py_files)
    
    # 2. Gather all .html files recursively in the templates folder
    html_files = gather_files(templates_dir, ".html")
    
    # Ensure the instance folder exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # 3. Write everything into one file
    with open(output_file, "w", encoding="utf-8") as outfile:
        # Write Python files first
        for f in sorted(py_files):
            outfile.write(f"--- Start of {os.path.relpath(f, root_dir)} ---\n")
            with open(f, "r", encoding="utf-8") as infile:
                outfile.write(infile.read())
            outfile.write(f"\n--- End of {os.path.relpath(f, root_dir)} ---\n\n")
        
        # Then write HTML files
        for f in sorted(html_files):
            outfile.write(f"--- Start of {os.path.relpath(f, root_dir)} ---\n")
            with open(f, "r", encoding="utf-8") as infile:
                outfile.write(infile.read())
            outfile.write(f"\n--- End of {os.path.relpath(f, root_dir)} ---\n\n")

if __name__ == "__main__":
    main()
