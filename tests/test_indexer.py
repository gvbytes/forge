import os
import tempfile
import pytest
from backend.indexer.ast_retriever import CodebaseIndex, SymbolExtractor

def test_python_symbol_extraction():
    sample_code = """
class DataProcessor:
    def __init__(self, name: str):
        self.name = name

    def process_records(self, records: list):
        \"\"\"Process input records.\"\"\"
        return [r.strip() for r in records]

def helper_function(val: int) -> int:
    return val * 2
"""
    symbols = SymbolExtractor.extract_python("test.py", sample_code)
    assert len(symbols) >= 3
    names = [s.name for s in symbols]
    assert "DataProcessor" in names
    assert "process_records" in names
    assert "helper_function" in names

def test_codebase_indexing_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        file1 = os.path.join(tmpdir, "calc.py")
        with open(file1, "w", encoding="utf-8") as f:
            f.write("def compute_fibonacci(n: int) -> int:\n    if n <= 1:\n        return n\n    return compute_fibonacci(n-1) + compute_fibonacci(n-2)\n")
            
        file2 = os.path.join(tmpdir, "auth.py")
        with open(file2, "w", encoding="utf-8") as f:
            f.write("def authenticate_jwt_user(token: str) -> bool:\n    \"\"\"Validate JWT auth token.\"\"\"\n    return True\n")

        index = CodebaseIndex(tmpdir)
        count = index.build_index()
        assert count == 2

        results = index.search("fibonacci algorithm", top_k=1)
        assert len(results) == 1
        assert "compute_fibonacci" in results[0]["formatted_chunk"]
        assert "Lines 1-4" in results[0]["formatted_chunk"]
