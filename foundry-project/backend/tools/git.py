import subprocess
import os

class GitTransactionManager:
    def __init__(self, workspace_path: str):
        self.workspace = os.path.abspath(workspace_path)
        self._init_repo()

    def _run_git(self, *args) -> str:
        """Executes a git command in the workspace directory."""
        cmd = ["git"] + list(args)
        result = subprocess.run(cmd, cwd=self.workspace, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Git error: {' '.join(cmd)}\n{result.stderr}")
        return result.stdout.strip()

    def _init_repo(self):
        """Initializes the repo and ensures a clean main branch exists."""
        if not os.path.exists(os.path.join(self.workspace, ".git")):
            self._run_git("init")
            # Create an initial empty commit so we can branch off it
            self._run_git("commit", "--allow-empty", "-m", "Initial commit")
            self._run_git("branch", "-M", "main")
        else:
            # Ensure we are starting from a clean state on main
            self._run_git("checkout", "main")

    def start_task_branch(self, task_id: str):
        """Creates and checks out an isolated branch for the worker."""
        branch_name = f"task-{task_id}"
        # Ensure we branch from the latest main
        self._run_git("checkout", "main")
        self._run_git("checkout", "-b", branch_name)
        print(f"[Git] 🌿 Switched to new branch: {branch_name}")

    def rollback_attempt(self):
        """Wipes uncommitted changes, reverting the branch to its clean state."""
        self._run_git("reset", "--hard", "HEAD")
        self._run_git("clean", "-fd")
        print("[Git] ⏪ Rolled back failed edits.")

    def commit_and_merge(self, task_id: str, commit_msg: str):
        """Commits the verified work and merges it safely into main."""
        branch_name = f"task-{task_id}"
        
        # 1. Commit the work on the task branch
        self._run_git("add", ".")
        self._run_git("commit", "-m", commit_msg)
        
        # 2. Switch to main and merge
        self._run_git("checkout", "main")
        try:
            self._run_git("merge", branch_name, "--no-ff", "-m", f"Merge {branch_name}")
            print(f"[Git] 🔀 Successfully merged {branch_name} into main.")
        except RuntimeError as e:
            # Handle merge conflicts if another worker touched the same lines
            self._run_git("merge", "--abort")
            raise RuntimeError(f"Merge conflict merging {branch_name} into main. Aborted.") from e
            
        # 3. Clean up the branch
        self._run_git("branch", "-d", branch_name)
        
    def get_diff(self) -> str:
        """Returns the unified diff of all uncommitted changes on the current branch."""
        # Add files to staging so untracked new files appear in the diff
        self._run_git("add", "-N", ".") 
        return self._run_git("diff", "HEAD")