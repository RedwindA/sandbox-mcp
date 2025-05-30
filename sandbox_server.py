from mcp.server.fastmcp import FastMCP
import docker
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional
import requests
from urllib.parse import urlparse
import re

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
        async def create_container_environment(image: str, persist: bool, host_workspace_path: Optional[str] = None, download_url: Optional[str] = None) -> str:
            """Create a new container with the specified base image. Optionally download a file into its workspace.
            
            Args:
                image: Docker image to use (e.g., python:3.9-slim, ubuntu:latest)
                persist: Whether to persist the container after it exits.
                host_workspace_path: Optional path on the host to bind mount to /workspace in the container. If None, a temporary directory will be created.
                download_url: Optional URL of a file to download into the /workspace directory upon creation.
            
            Returns:
                Container ID of the new container and status of file download if attempted.
            """
            try:
                is_temp_dir = False
                if host_workspace_path:
                    # Ensure the user-provided path exists
                    Path(host_workspace_path).mkdir(parents=True, exist_ok=True)
                    mount_path = host_workspace_path
                else:
                    # Create a temporary directory for file mounting
                    mount_path = tempfile.mkdtemp()
                    is_temp_dir = True
                
                # Create container with the mount_path directory mounted
                container = self.docker_client.containers.run(
                    image=image,
                    command="tail -f /dev/null",  # Keep container running
                    volumes={
                        mount_path: {
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
                    'mount_path': mount_path,
                    'is_temp_dir': is_temp_dir,
                    'files': {}
                }
                
                downloaded_filename = None
                download_status_message = ""

                if download_url:
                    try:
                        # Attempt to download the file from the URL
                        response = requests.get(download_url, stream=True, timeout=30) # Added timeout
                        response.raise_for_status()  # Raise an exception for bad status codes
                        
                        # Determine filename
                        parsed_url = urlparse(download_url)
                        filename_from_url = os.path.basename(parsed_url.path)
                        
                        # Try to get filename from Content-Disposition header if not in URL path
                        if not filename_from_url:
                            content_disposition = response.headers.get('content-disposition')
                            if content_disposition:
                                # Regex to find filename in content-disposition header
                                # Handles cases like: filename="example.txt" or filename=example.txt
                                fname_match = re.search(r'filename="?([^"]+)"?', content_disposition)
                                if fname_match:
                                    filename_from_url = fname_match.group(1).strip("'\"") # Strip quotes

                        if not filename_from_url:  # Fallback filename if still not found
                            filename_from_url = "downloaded_file"

                        downloaded_filepath = Path(mount_path) / filename_from_url
                        
                        with open(downloaded_filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        downloaded_filename = filename_from_url
                        download_status_message = f"\nFile '{downloaded_filename}' downloaded to /workspace."
                        
                    except requests.exceptions.Timeout:
                        download_status_message = f"\nFailed to download file from {download_url}: Timeout."
                    except requests.exceptions.RequestException as e:
                        download_status_message = f"\nFailed to download file from {download_url}: {str(e)}."
                    except Exception as e:  # Catch any other unforeseen errors during download
                        download_status_message = f"\nError processing download for {download_url}: {str(e)}."

                return_message = f"""Container created with ID: {container.id}
Working directory is /workspace
Container is ready for commands"""
                return_message += download_status_message
                
                return return_message
                
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
                mount_path = container_info['mount_path']
                
                # Create file in the mounted directory
                file_path = Path(mount_path) / filename
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
                
                # Clean up temp directory if it exists and was temporary
                if container_info.get('is_temp_dir') and 'mount_path' in container_info:
                    try:
                        import shutil
                        shutil.rmtree(container_info['mount_path'])
                    except Exception as e:
                        print(f"Warning: Failed to remove temp directory: {container_info['mount_path']}: {str(e)}")
                
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
