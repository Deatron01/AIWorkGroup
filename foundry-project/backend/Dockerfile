# Use a lightweight Python image
FROM python:3.11-slim

# Install basic testing and system tools
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pytest asyncio

# Set the working directory where the AI will inject code
WORKDIR /workspace

# Keep the container alive indefinitely so the sandbox can execute commands inside it
CMD ["tail", "-f", "/dev/null"]