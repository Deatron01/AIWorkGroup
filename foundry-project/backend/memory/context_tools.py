import os
import ast

# Ensure these globals are explicitly defined or injected from the main config
WORKSPACE_DIR = "./workspace"

def tool_search_codebase(query: str, n_results: int = 3) -> str:
    """Semantic search to find relevant code without knowing the filename."""
    results = indexer.collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    output = []
    for i in range(len(results['documents'][0])):
        doc = results['documents'][0][i]
        meta = results['metadatas'][0][i]
        output.append(f"--- File: {meta['file']} | {meta['type']}: {meta['name']} ---\n{doc}")
        
    return "\n\n".join(output) if output else "No relevant code found."

def tool_get_file_symbols(filename: str) -> str:
    """Returns only the signatures (def / class) of a file, saving context space."""
    filepath = os.path.join(WORKSPACE_DIR, filename)
    if not os.path.exists(filepath):
        return f"Error: {filename} not found."
    
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()
        
    try:
        tree = ast.parse(code)
        signatures = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                signatures.append(f"def {node.name}(...)")
            elif isinstance(node, ast.ClassDef):
                signatures.append(f"class {node.name}(...)")
        
        return "\n".join(signatures) if signatures else "File is empty or has no functions/classes."
    except SyntaxError:
        return "Syntax error in file, cannot parse symbols."

def tool_read_file_chunk(filename: str, start_line: int, end_line: int) -> str:
    """Reads a specific segment of a file after the agent uses tool_get_file_symbols."""
    filepath = os.path.join(WORKSPACE_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    # Guardrails to prevent out-of-bounds errors
    start = max(0, start_line - 1)
    end = min(len(lines), end_line)
    
    chunk = "".join(lines[start:end])
    return f"Lines {start_line}-{end_line} of {filename}:\n{chunk}"