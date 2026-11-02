import os

root = os.getcwd()
print("cwd:", root)
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in (".git", ".venv", "node_modules", "__pycache__")]
    rel = os.path.relpath(dirpath, root)
    print(f"\n[{rel}]")
    for f in sorted(filenames):
        print("   ", f)
