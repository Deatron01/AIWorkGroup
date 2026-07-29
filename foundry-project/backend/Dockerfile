# Use a slim Python image to save space and build time
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root workspace directory
WORKDIR /workspace

# Install pytest and any other baseline testing/async tools you need
RUN pip install --no-cache-dir pytest pytest-asyncio

# The default command simply keeps the container alive so your 
# AsyncDockerSandbox can execute commands inside it dynamically.
CMD ["tail", "-f", "/dev/null"]