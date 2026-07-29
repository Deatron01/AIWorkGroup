import docker
import os
import asyncio

class AsyncDockerSandbox:
    # Updated default image to the custom testing container
    def __init__(self, workspace_path: str, image: str = "mimir-tester:latest"):
        self.client = docker.from_env()
        self.workspace_path = os.path.abspath(workspace_path)
        self.image = image
        self.container = None
        self.lock = asyncio.Lock()  # Prevents race conditions in the workspace
        self._ensure_image()

    def _ensure_image(self):
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            # Prevent Docker SDK from trying to pull a local image from the web
            if "mimir-tester" in self.image:
                raise RuntimeError(
                    f"Local image '{self.image}' not found! "
                    "Run 'docker build -t mimir-tester:latest .' first."
                )
            self.client.images.pull(self.image)

    def start(self):
        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",
            volumes={self.workspace_path: {'bind': '/workspace', 'mode': 'rw'}},
            working_dir='/workspace',
            detach=True,
            auto_remove=True
        )

    async def execute(self, cmd: str, workdir: str = None) -> str:
        """Executes safely without blocking the main async event loop."""
        if not self.container:
            return "Error: Sandbox down."
        
        async with self.lock:
            # Run the blocking Docker API call in a thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._sync_execute, cmd)

    def _sync_execute(self, cmd: str) -> str:
        exit_code, output = self.container.exec_run(["/bin/bash", "-c", cmd], workdir="/workspace")
        result = output.decode("utf-8").strip()
        # Note: We will look for "Failed" in the Supervisor to detect errors
        return result if exit_code == 0 else f"Failed (Code {exit_code}):\n{result}"

    def stop(self):
        if self.container:
            self.container.stop()