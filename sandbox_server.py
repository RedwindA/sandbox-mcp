from mcp.server.fastmcp import FastMCP
import docker
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional

class SandboxServer:
    def __init__(self):
        self.mcp = FastMCP("sandbox-server")
        self.docker_client = docker.from_env()
        # Map of container IDs to their info
        self.containers: Dict[str, dict] = {}
        
        # Register all tools
        self._register_tools()
    
    def _register_tools(self):
        @self.mcp.tool()
        async def create_container_environment(image: str, persist: bool) -> str:
            """Create a new container with the specified base image.
            
            Args:
                image: Docker image to use (e.g., python:3.9-slim, ubuntu:latest)
            
            Returns:
                Container ID of the new container
            """
            try:
                # Create a temporary directory for file mounting
                temp_dir = tempfile.mkdtemp()
                
                # Create container with the temp directory mounted
                container = self.docker_client.containers.run(
                    image=image,
                    command="tail -f /dev/null",  # Keep container running
                    volumes={
                        temp_dir: {
                            'bind': '/workspace',
                            'mode': 'rw'
                        }
                    },
                    working_dir='/workspace',
                    detach=True,
                    remove=not persist
                )
                
                # Store container info
                self.containers[container.id] = {
                    'temp_dir': temp_dir,
                    'files': {}
                }
                
                return f"""Container created with ID: {container.id}
Working directory is /workspace
Container is ready for commands"""
                
            except docker.errors.ImageNotFound:
                return f"Error: Image {image} not found. Please verify the image name."
            except Exception as e:
                return f"Error creating container: {str(e)}"

        @self.mcp.tool()
        async def create_file_in_container(container_id: str, filename: str, content: str) -> str:
            """Create a file in the specified container.
            
            Args:
                container_id: ID of the container
                filename: Name of the file to create
                content: Content of the file
            
            Returns:
                Status message
            """
            if container_id not in self.containers:
                return f"Container {container_id} not found"
                
            try:
                container_info = self.containers[container_id]
                temp_dir = container_info['temp_dir']
                
                # Create file in the mounted directory
                file_path = Path(temp_dir) / filename
                with open(file_path, 'w') as f:
                    f.write(content)
                
                # Update container info
                container_info['files'][filename] = content
                
                return f"File {filename} has been created in /workspace"
                
            except Exception as e:
                return f"Error creating file: {str(e)}"

        @self.mcp.tool()
        async def execute_command_in_container(container_id: str, command: str) -> str:
            """Execute a command in the specified container.
            
            Args:
                container_id: ID of the container
                command: Command to execute
            
            Returns:
                Command output
            """
            try:
                container = self.docker_client.containers.get(container_id)
                result = container.exec_run(
                    command, 
                    workdir='/workspace',
                    environment={
                        "DEBIAN_FRONTEND": "noninteractive"  # For apt-get
                    }
                )
                return result.output.decode('utf-8')
            except docker.errors.NotFound:
                return f"Container {container_id} not found"
            except Exception as e:
                return f"Error executing command: {str(e)}"
            
        @self.mcp.tool()
        async def save_container_state(container_id: str, name: str) -> str:
            """Save the current state of a container as a new image.
            
            Args:
                container_id: ID of the container to save
                name: Name for the saved image (e.g., 'my-python-env:v1')
            
            Returns:
                Instructions for using the saved image
            """
            try:
                container = self.docker_client.containers.get(container_id)
                repository, tag = name.split(':') if ':' in name else (name, 'latest')
                container.commit(repository=repository, tag=tag)
                
                return f"""Environment saved as image: {name}

To use this environment later:
1. Create new container: docker run -it {name}
2. Or use with this MCP server: create_container("{name}")

The image contains all installed packages and configurations."""
            except docker.errors.NotFound:
                return f"Container {container_id} not found"
            except Exception as e:
                return f"Error saving container: {str(e)}"

        @self.mcp.tool()
        async def export_dockerfile(container_id: str) -> str:
            """Generate a Dockerfile that recreates the current container state.
            
            Args:
                container_id: ID of the container to export
                
            Returns:
                Dockerfile content and instructions
            """
            try:
                container = self.docker_client.containers.get(container_id)
                
                # Get container info
                info = container_info = self.containers.get(container_id, {})
                image = container.attrs['Config']['Image']
                
                # Get history of commands (if available)
                history = []
                if 'files' in info:
                    history.extend([f"COPY {file} /workspace/{file}" for file in info['files'].keys()])
                
                # Create Dockerfile content
                dockerfile = [
                    f"FROM {image}",
                    "WORKDIR /workspace",
                    *history,
                    '\n# Add any additional steps needed:',
                    '# RUN pip install <packages>',
                    '# COPY <src> <dest>',
                    '# etc.'
                ]
                
                return f"""Here's a Dockerfile to recreate this environment:

{chr(10).join(dockerfile)}

To use this Dockerfile:
1. Save it to a file named 'Dockerfile'
2. Build: docker build -t your-image-name .
3. Run: docker run -it your-image-name"""
            except docker.errors.NotFound:
                return f"Container {container_id} not found"
            except Exception as e:
                return f"Error generating Dockerfile: {str(e)}"
            
        @self.mcp.tool()
        async def exit_container(container_id: str, force: bool = False) -> str:
            """Stop and remove a running container.
            
            Args:
                container_id: ID of the container to stop and remove
                force: Force remove the container even if it's running
            
            Returns:
                Status message about container cleanup
            """
            try:
                container = self.docker_client.containers.get(container_id)
                container_info = self.containers.get(container_id, {})
                
                # Try to stop container gracefully first
                if not force:
                    try:
                        container.stop(timeout=10)
                    except Exception as e:
                        return f"Failed to stop container gracefully: {str(e)}. Try using force=True if needed."
                
                # Remove container and cleanup
                container.remove(force=force)
                
                # Clean up temp directory if it exists
                if 'temp_dir' in container_info:
                    try:
                        import shutil
                        shutil.rmtree(container_info['temp_dir'])
                    except Exception as e:
                        print(f"Warning: Failed to remove temp directory: {str(e)}")
                
                # Remove from our tracking
                if container_id in self.containers:
                    del self.containers[container_id]
                
                return f"Container {container_id} has been stopped and removed."
                
            except docker.errors.NotFound:
                return f"Container {container_id} not found"
            except Exception as e:
                return f"Error cleaning up container: {str(e)}"



    def run(self):
        """Start the MCP server."""
        self.mcp.run()

def main():
    server = SandboxServer()
    server.run()

if __name__ == "__main__":
    main()
