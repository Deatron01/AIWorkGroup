import subprocess
import os
import threading

class GitTransactionManager:
    def __init__(self, workspace_path: str):
        self.workspace = os.path.abspath(workspace_path)
        # Dedicated directory physically separated from main workspace to house active worktrees
        self.worktrees_dir = os.path.abspath(os.path.join(self.workspace, "..", "worktrees"))
        os.makedirs(self.worktrees_dir, exist_ok=True)
        
        self.git_lock = threading.Lock()
        self._init_repo()

    def _run_git(self, *args, cwd=None) -> str:
        """Executes a git command in the target directory (defaults to main workspace)."""
        cmd = ["git"] + list(args)
        target_cwd = cwd if cwd else self.workspace
        
        with self.git_lock:
            result = subprocess.run(cmd, cwd=target_cwd, capture_output=True, text=True)
            
        if result.returncode != 0:
            raise RuntimeError(f"Git error: {' '.join(cmd)}\n{result.stderr}")
        return result.stdout.strip()

    def _init_repo(self):
        """Initializes the repo in the main workspace and ensures a clean main branch."""
        if not os.path.exists(os.path.join(self.workspace, ".git")):
            self._run_git("init")
            self._run_git("commit", "--allow-empty", "-m", "Initial commit")
            self._run_git("branch", "-M", "main")
        else:
            self._run_git("checkout", "main")

    def start_task_branch(self, task_id: str) -> str:
        """
        Creates a dedicated Git Worktree (a physical folder) tied to a new isolated branch.
        Returns the absolute path to this new worktree folder.
        """
        branch_name = f"task-{task_id}"
        worktree_path = os.path.join(self.worktrees_dir, branch_name)
        
        # Creates a new worktree directory, branches off main, and checks it out physically
        self._run_git("worktree", "add", "-b", branch_name, worktree_path, "main")
        print(f"[Git] Spun up isolated worktree for: {branch_name}")
        
        return worktree_path

    def commit_and_merge(self, task_id: str, commit_msg: str, worktree_path: str):
        """Commits inside the worktree, merges into main, and cleans up the physical folder."""
        branch_name = f"task-{task_id}"
        
        # 1. Commit the work inside the specific worktree directory
        self._run_git("add", ".", cwd=worktree_path)
        status = self._run_git("status", "--porcelain", cwd=worktree_path)
        
        if not status:
            print(f"[Git] No changes made for {task_id}. Skipping commit.")
        else:
            self._run_git("commit", "-m", commit_msg, cwd=worktree_path)
        
        # 2. Switch to main workspace and merge
        try:
            self._run_git("merge", branch_name, "--no-ff", "-m", f"Merge {branch_name}", cwd=self.workspace)
            print(f"[Git] Successfully merged {branch_name} into main.")
        except RuntimeError as e:
            self._run_git("merge", "--abort", cwd=self.workspace)
            raise RuntimeError(f"Merge conflict merging {branch_name} into main. Aborted.") from e
            
        # 3. Clean up the physical worktree and branch
        self._run_git("worktree", "remove", "-f", worktree_path, cwd=self.workspace)
        self._run_git("branch", "-d", branch_name, cwd=self.workspace)
        
    def rollback_attempt(self, worktree_path: str):
        """Wipes uncommitted changes, reverting the isolated worktree to its clean state."""
        self._run_git("reset", "--hard", "HEAD", cwd=worktree_path)
        self._run_git("clean", "-fd", cwd=worktree_path)
        print("[Git] ⏪ Rolled back failed edits in worktree.")
        
    def get_diff(self, worktree_path: str) -> str:
        """Returns the unified diff of all uncommitted changes in the isolated worktree."""
        self._run_git("add", "-N", ".", cwd=worktree_path) 
        return self._run_git("diff", "HEAD", cwd=worktree_path)