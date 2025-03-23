import os
import re
import sys

def create_project_from_text(text):
    """
    Parses the input text for file blocks and creates the corresponding files.
    
    Expected block format:
    
    !!#@!#$FILE: path/to/file.ext!@#!@#!@
    (file content)
    !!#@!#$END FILE!@#!@#!@
    """
    # Define the regex pattern to match the file blocks.
    pattern = r"!!#@!#\$FILE:\s*(.*?)!@#!@#!@(.*?)!!#@!#\$END FILE!@#!@#!@"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if not matches:
        print("No valid file blocks found. Please check your template.")
        return

    for filepath, file_content in matches:
        # Clean up whitespace/newlines.
        filepath = filepath.strip()
        file_content = file_content.lstrip("\n").rstrip()

        # Create directories if they do not exist.
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Write the file content.
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(file_content)
        print(f"Created file: {filepath}")

def main():
    # If a filename is provided as a command-line argument, read from that file.
    if len(sys.argv) > 1:
        input_filename = sys.argv[1]
        try:
            with open(input_filename, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file {input_filename}: {e}")
            return
    else:
        # Otherwise, read pasted text from standard input.
        print("Please paste your project text below. End input with Ctrl-D (Unix) or Ctrl-Z (Windows) on a new line:")
        text = sys.stdin.read()
    
    create_project_from_text(text)

if __name__ == '__main__':
    main()

"""
please give me full updated file in this format
!!#@!#$FILE: path/to/file1.py!@#!@#!@
# Contents of file1.py
print("Hello, World!")
!!#@!#$END FILE!@#!@#!@

!!#@!#$FILE: path/to/subfolder/file2.txt!@#!@#!@
This is some text content.
!!#@!#$END FILE!@#!@#!@

do not answer anything that not belongs to above format
"""