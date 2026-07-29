import docker
import os

class DockerSandbox:
    def __init__(self, workspace_path: str, image: str = "tester:latest"):
        self.client = docker.from_env()
        self.workspace_path = os.path.abspath(workspace_path)
        self.image = image
        self.container = None
        self._ensure_image()

    def _ensure_image(self):
        """Checks if the image exists locally before trying to pull."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            # If it's your local custom image, don't attempt to pull from Docker Hub
            if "mimir-tester" in self.image:
                raise RuntimeError(
                    f"Local image '{self.image}' not found! "
                    "Run 'docker build -t tester:latest .' in your terminal first."
                )
            print(f"Pulling sandbox image {self.image}... This might take a minute.")
            self.client.images.pull(self.image)

    def start(self):
        """Starts a background container with the workspace mounted."""
        print(f"Starting Docker sandbox mapped to {self.workspace_path}")
        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",  # Keep the container running infinitely
            volumes={
                self.workspace_path: {
                    'bind': '/workspace',
                    'mode': 'rw'
                }
            },
            working_dir='/workspace',
            detach=True,
            auto_remove=True,  # Destroy container when stopped
            mem_limit="1g",    # Hard cap to prevent runaway processes
            cpuset_cpus="0"    # Restrict to a single CPU core for safety
        )

    def execute(self, cmd: str) -> str:
        """Executes a bash command inside the running container."""
        if not self.container:
            return "Error: Sandbox not running."
        
        try:
            # We use bash -c to support piping and logical operators in commands
            exit_code, output = self.container.exec_run(
                ["/bin/bash", "-c", cmd],
                workdir="/workspace"
            )
            
            result = output.decode("utf-8").strip()
            if exit_code != 0:
                return f"Command failed with exit code {exit_code}.\nOutput:\n{result}"
            return result if result else "Execution successful with no output."
        except Exception as e:
            return f"Sandbox execution error: {str(e)}"

    def stop(self):
        """Stops and destroys the container."""
        if self.container:
            print("Stopping Docker sandbox...")
            self.container.stop()
            self.container = None