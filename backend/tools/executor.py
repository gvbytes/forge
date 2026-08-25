import os
import re
import asyncio
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import git

class ToolResult:
    def __init__(self, output: str, is_error: bool = False, requires_approval: bool = False, metadata: Optional[Dict[str, Any]] = None):
        self.output = output
        self.is_error = is_error
        self.requires_approval = requires_approval
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output": self.output,
            "is_error": self.is_error,
            "requires_approval": self.requires_approval,
            "metadata": self.metadata,
        }

class DiffHunk:
    def __init__(self, file_path: str, hunk_index: int, header: str, lines: List[str], is_approved: bool = True):
        self.file_path = file_path
        self.hunk_index = hunk_index
        self.header = header
        self.lines = lines
        self.is_approved = is_approved

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "hunk_index": self.hunk_index,
            "header": self.header,
            "lines": self.lines,
            "is_approved": self.is_approved,
        }

class ToolExecutor:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)

    def is_side_effect(self, command: str) -> bool:
        cmd = command.strip().lower()
        side_effect_patterns = [
            r"\brm\b", r"\bmv\b", r"\bcp\b", r"\bmkdir\b", r"\btouch\b",
            r"\bpip\s+install\b", r"\bnpm\s+install\b", r"\byarn\s+add\b",
            r"\bgit\s+(commit|push|merge|rebase|reset|checkout\s+-b)\b",
            r"\bchmod\b", r"\bchown\b", r"\bkill\b", r"\bpkill\b",
            r">\s*", r">>\s*", r"\btee\b"
        ]
        return any(re.search(pat, cmd) for pat in side_effect_patterns)

    async def execute_bash(self, command: str, approved: bool = False) -> ToolResult:
        if self.is_side_effect(command) and not approved:
            return ToolResult(
                output=f"Approval required for mutating command: `{command}`",
                is_error=False,
                requires_approval=True,
                metadata={"command": command, "type": "bash"}
            )
            
        try:
            import os as _os
            env = {**_os.environ, "TERM": "xterm"}
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workspace_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")
            
            combined = out_str
            if err_str:
                combined += f"\n[stderr]\n{err_str}" if combined else err_str
                
            return ToolResult(
                output=combined or "(Command executed with no output)",
                is_error=(proc.returncode != 0),
                metadata={"returncode": proc.returncode}
            )
        except asyncio.TimeoutError:
            return ToolResult(output="Command execution timed out after 60 seconds.", is_error=True)
        except Exception as e:
            return ToolResult(output=f"Execution error: {str(e)}", is_error=True)

    def read_file(self, rel_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> ToolResult:
        full_path = os.path.join(self.workspace_root, rel_path)
        if not os.path.exists(full_path):
            return ToolResult(output=f"File not found: {rel_path}", is_error=True)
            
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                
            if start_line is not None and end_line is not None:
                start_idx = max(0, start_line - 1)
                end_idx = min(len(lines), end_line)
                selected = lines[start_idx:end_idx]
                numbered = [f"{i + start_idx + 1:4d} | {line}" for i, line in enumerate(selected)]
                return ToolResult(output="".join(numbered))
            else:
                numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
                return ToolResult(output="".join(numbered))
        except Exception as e:
            return ToolResult(output=f"Error reading file {rel_path}: {str(e)}", is_error=True)

    def write_file(self, rel_path: str, content: str, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(
                output=f"Approval required to write to file: `{rel_path}`",
                requires_approval=True,
                metadata={"file_path": rel_path, "content": content, "type": "file_write"}
            )
            
        full_path = os.path.join(self.workspace_root, rel_path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(output=f"Successfully wrote {len(content)} characters to {rel_path}")
        except Exception as e:
            return ToolResult(output=f"Error writing to {rel_path}: {str(e)}", is_error=True)

    def parse_git_diff_hunks(self, diff_text: str) -> List[DiffHunk]:
        hunks: List[DiffHunk] = []
        current_file = ""
        current_header = ""
        current_lines: List[str] = []
        hunk_index = 0

        for line in diff_text.splitlines():
            if line.startswith("diff --git") or line.startswith("--- a/") or line.startswith("+++ b/"):
                if line.startswith("+++ b/"):
                    current_file = line[6:].strip()
                continue
                
            if line.startswith("@@"):
                if current_file and current_lines:
                    hunks.append(DiffHunk(current_file, hunk_index, current_header, current_lines))
                    hunk_index += 1
                    current_lines = []
                current_header = line
            else:
                if current_header:
                    current_lines.append(line)

        if current_file and current_lines:
            hunks.append(DiffHunk(current_file, hunk_index, current_header, current_lines))

        return hunks

    def apply_diff_hunk(self, hunk: DiffHunk) -> bool:
        full_path = os.path.join(self.workspace_root, hunk.file_path)
        if not os.path.exists(full_path):
            return False
            
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                file_lines = f.read().splitlines()
                
            m = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", hunk.header)
            if not m:
                return False
                
            old_start = int(m.group(1)) - 1
            new_lines = []
            
            old_idx = 0
            for line in hunk.lines:
                if line.startswith(" "):
                    old_idx += 1
                elif line.startswith("-"):
                    old_idx += 1
                elif line.startswith("+"):
                    pass
                    
            prefix = file_lines[:old_start]
            suffix = file_lines[old_start + old_idx:]
            
            replacement = []
            for line in hunk.lines:
                if line.startswith(" "):
                    replacement.append(line[1:])
                elif line.startswith("+"):
                    replacement.append(line[1:])
                    
            updated_content = "\n".join(prefix + replacement + suffix)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
                
            return True
        except Exception:
            return False

    def git_status_and_diff(self) -> Dict[str, Any]:
        try:
            repo = git.Repo(self.workspace_root)
            diff_text = repo.git.diff()
            untracked = repo.untracked_files
            return {
                "branch": repo.active_branch.name if not repo.head.is_detached else "main",
                "is_dirty": repo.is_dirty(),
                "diff": diff_text,
                "untracked": untracked,
            }
        except Exception:
            # Fallback: scan workspace files
            files = []
            for root, dirs, fnames in os.walk(self.workspace_root):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {".git", ".venv", "venv"}]
                for f in fnames:
                    if not f.startswith(".") and not f.endswith((".pyc", ".db", ".log")):
                        files.append(os.path.relpath(os.path.join(root, f), self.workspace_root))
            return {
                "branch": "main",
                "is_dirty": len(files) > 0,
                "diff": "",
                "untracked": files,
            }
