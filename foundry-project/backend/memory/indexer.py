import os
import ast
import chromadb
from chromadb.utils import embedding_functions

# Use a lightweight CPU model for embeddings to save VRAM
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2", 
    device="cpu"
)

class CodeIndexer:
    def __init__(self, workspace_path: str, db_path: str = "./.foundry_db"):
        self.workspace_path = workspace_path
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="codebase",
            embedding_function=sentence_transformer_ef
        )

    def extract_functions_and_classes(self, filepath: str, code: str):
        """Uses AST to chunk code logically, not arbitrarily."""
        chunks = []
        try:
            tree = ast.parse(code)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Extract the source code for just this function/class
                    chunk_code = ast.get_source_segment(code, node)
                    if chunk_code:
                        chunks.append({
                            "id": f"{filepath}::{node.name}",
                            "text": chunk_code,
                            "metadata": {"file": filepath, "type": type(node).__name__, "name": node.name}
                        })
        except SyntaxError:
            pass # Handle non-python or malformed files gracefully
        return chunks

    def index_workspace(self):
        """Scans the workspace and builds the vector index."""
        print("[Indexer] Scanning workspace...")
        for root, _, files in os.walk(self.workspace_path):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, self.workspace_path)
                    
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.content()
                        
                    chunks = self.extract_functions_and_classes(rel_path, content)
                    
                    if chunks:
                        self.collection.upsert(
                            ids=[c["id"] for c in chunks],
                            documents=[c["text"] for c in chunks],
                            metadatas=[c["metadata"] for c in chunks]
                        )
        print(f"[Indexer] Indexed {self.collection.count()} code blocks.")