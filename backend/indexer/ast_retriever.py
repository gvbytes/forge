import os
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

class CodeSymbol:
    def __init__(
        self,
        file_path: str,
        symbol_type: str,
        name: str,
        start_line: int,
        end_line: int,
        signature: str,
        docstring: Optional[str],
        content: str,
    ):
        self.file_path = file_path
        self.symbol_type = symbol_type
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.signature = signature
        self.docstring = docstring or ""
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "symbol_type": self.symbol_type,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
            "docstring": self.docstring,
            "content": self.content,
        }

class SymbolExtractor:
    @staticmethod
    def extract_python(file_path: str, source_code: str) -> List[CodeSymbol]:
        symbols: List[CodeSymbol] = []
        lines = source_code.splitlines()
        try:
            tree = ast.parse(source_code, filename=file_path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno
                    end = getattr(node, "end_lineno", start)
                    doc = ast.get_docstring(node)
                    chunk = "\n".join(lines[start - 1 : end])
                    sig = f"def {node.name}(...)"
                    symbols.append(CodeSymbol(
                        file_path=file_path,
                        symbol_type="function",
                        name=node.name,
                        start_line=start,
                        end_line=end,
                        signature=sig,
                        docstring=doc,
                        content=chunk,
                    ))
                elif isinstance(node, ast.ClassDef):
                    start = node.lineno
                    end = getattr(node, "end_lineno", start)
                    doc = ast.get_docstring(node)
                    chunk = "\n".join(lines[start - 1 : end])
                    sig = f"class {node.name}"
                    symbols.append(CodeSymbol(
                        file_path=file_path,
                        symbol_type="class",
                        name=node.name,
                        start_line=start,
                        end_line=end,
                        signature=sig,
                        docstring=doc,
                        content=chunk,
                    ))
        except Exception:
            pass
        return symbols

    @staticmethod
    def extract_generic(file_path: str, source_code: str) -> List[CodeSymbol]:
        symbols: List[CodeSymbol] = []
        lines = source_code.splitlines()
        pattern = re.compile(r"^\s*(export\s+)?(function|class|interface|type|fn|pub fn|def|struct)\s+([a-zA-Z0-9_]+)", re.MULTILINE)
        
        for idx, line in enumerate(lines):
            match = pattern.match(line)
            if match:
                sym_type = match.group(2)
                name = match.group(3)
                start = idx + 1
                end = min(len(lines), start + 30)
                chunk = "\n".join(lines[start - 1 : end])
                symbols.append(CodeSymbol(
                    file_path=file_path,
                    symbol_type=sym_type,
                    name=name,
                    start_line=start,
                    end_line=end,
                    signature=line.strip(),
                    docstring="",
                    content=chunk,
                ))
        return symbols

class CodebaseIndex:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        self.symbols: List[CodeSymbol] = []
        self.bm25: Optional[BM25Okapi] = None
        self.tokenized_corpus: List[List[str]] = []
        self.ignored_dirs = {".git", ".venv", "__pycache__", "node_modules", "dist", "build", ".gemini"}

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        subwords = []
        for w in words:
            subwords.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", w))
            subwords.append(w)
        return [sw.lower() for sw in subwords if sw]

    def build_index(self) -> int:
        self.symbols.clear()
        self.tokenized_corpus.clear()
        
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".cpp", ".c", ".h", ".java"]:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.workspace_root)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        if ext == ".py":
                            file_symbols = SymbolExtractor.extract_python(rel_path, content)
                        else:
                            file_symbols = SymbolExtractor.extract_generic(rel_path, content)
                            
                        self.symbols.extend(file_symbols)
                    except Exception:
                        continue

        if self.symbols:
            for s in self.symbols:
                doc_text = f"{s.file_path} {s.name} {s.symbol_type} {s.signature} {s.docstring} {s.content[:300]}"
                self.tokenized_corpus.append(self._tokenize(doc_text))
            self.bm25 = BM25Okapi(self.tokenized_corpus)
            
        return len(self.symbols)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.symbols or not self.bm25:
            return []
            
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
            
        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0.0:
                sym = self.symbols[idx]
                results.append({
                    "symbol": sym.to_dict(),
                    "score": float(scores[idx]),
                    "formatted_chunk": f"# File: {sym.file_path} (Lines {sym.start_line}-{sym.end_line})\n# Symbol: {sym.name} ({sym.symbol_type})\n{sym.content}\n"
                })
                
        if not results:
            words = query.split()
            for w in words:
                if len(w) > 2:
                    for sym in self.symbols:
                        if w.lower() in sym.name.lower() or w.lower() in sym.file_path.lower():
                            results.append({
                                "symbol": sym.to_dict(),
                                "score": 0.5,
                                "formatted_chunk": f"# File: {sym.file_path} (Lines {sym.start_line}-{sym.end_line})\n# Symbol: {sym.name}\n{sym.content}\n"
                            })
                            if len(results) >= top_k:
                                break
                    if results:
                        break
                        
        return results

class WorkspaceIndexRegistry:
    def __init__(self):
        self._indices: Dict[str, CodebaseIndex] = {}

    def get_index(self, workspace_root: str) -> CodebaseIndex:
        clean_root = os.path.abspath(workspace_root)
        if clean_root not in self._indices:
            index = CodebaseIndex(clean_root)
            index.build_index()
            self._indices[clean_root] = index
        return self._indices[clean_root]

workspace_registry = WorkspaceIndexRegistry()
