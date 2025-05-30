# Sandbox MCP Server

An MCP server that provides isolated Docker environments for code execution. This server allows you to:
- Create containers with any Docker image
- Write and execute code in multiple programming languages
- Install packages and set up development environments
- Run commands in isolated containers
- Download files directly into containers during creation
- Mount host directories for persistent storage

## Prerequisites

- Python 3.9 or higher
- Docker installed and running
- uv package manager (recommended)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/RedwindA/sandbox-mcp
cd sandbox-mcp
```

2. Create and activate a virtual environment with uv:
```bash
uv venv
source .venv/bin/activate  # On Unix/MacOS
# Or on Windows:
# .venv\Scripts\activate
```

3. Install dependencies:
```bash
uv pip install .
```

## Integration with Claude Desktop

1. Open Claude Desktop's configuration file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the sandbox server configuration:
```json
{
    "mcpServers": {
        "sandbox": {
            "command": "uv",
            "args": [
                "--directory",
                "/absolute/path/to/sandbox_server",
                "run",
                "sandbox_server.py"
            ],
            "env": {
                "PYTHONPATH": "/absolute/path/to/sandbox_server"
            }
        }
    }
}
```

Replace `/absolute/path/to/sandbox_server` with the actual path to your project directory.

3. Restart Claude Desktop

## Usage Examples

### Basic Usage

Once connected to Claude Desktop, you can:

1. Create a Python container:
```
Could you create a Python container and write a simple hello world program?
```

2. Run code in different languages:
```
Could you create a C program that calculates the fibonacci sequence and run it?
```

3. Install packages and use them:
```
Could you create a Python script that uses numpy to generate and plot some random data?
```

### Advanced Features

#### Download Files During Container Creation

You can download files directly into the container workspace during creation:
```
Create a Python container and download the dataset from https://example.com/data.csv
```

#### Mount Host Directories

Mount a specific host directory to persist data between sessions:
```
Create a container with the host directory /path/to/my/project mounted as workspace
```

### Saving and Reproducing Environments

The server provides several ways to save and reproduce your development environments:

#### Creating Persistent Containers

When creating a container, you can make it persistent:
```
Could you create a persistent Python container with numpy and pandas installed?
```

This will create a container that:
- Stays running after Claude Desktop closes
- Can be accessed directly through Docker
- Preserves all installed packages and files

#### Saving Container State

After setting up your environment, you can save it as a Docker image:
```
Could you save the current container state as an image named 'my-ds-env:v1'?
```

This will:
1. Create a new Docker image with all your:
   - Installed packages
   - Created files
   - Configuration changes
2. Provide instructions for reusing the environment

You can then share this image or use it as a starting point for new containers:
```
Could you create a new container using the my-ds-env:v1 image?
```

#### Generating Dockerfiles

To make your environment fully reproducible, you can generate a Dockerfile:
```
Could you export a Dockerfile that recreates this environment?
```

The generated Dockerfile will include:
- Base image specification
- Created files
- Template for additional setup steps

You can use this Dockerfile to:
1. Share your environment setup with others
2. Version control your development environment
3. Modify and customize the build process
4. Deploy to different systems

#### Container Cleanup

When you're done with a container, clean it up:
```
Could you exit and clean up the container?
```

This will:
- Stop the container gracefully
- Remove the container
- Clean up temporary directories if created
- Remove from tracking

#### Recommended Workflow

For reproducible development environments:

1. Create a persistent container with file download:
```
Create a persistent Python container and download requirements.txt from my repository
```

2. Install needed packages:
```
Install the packages listed in requirements.txt
```

3. Test your setup:
```
Create and run a test script to verify the environment
```

4. Save the state:
```
Save this container as 'ds-workspace:v1'
```

5. Export a Dockerfile:
```
Generate a Dockerfile for this environment
```

6. Clean up when done:
```
Exit and clean up the container
```

This gives you multiple options for recreating your environment:
- Use the saved Docker image directly
- Build from the Dockerfile with modifications
- Access the original container if needed

## Security Notes

- All code executes in isolated Docker containers
- Containers can be automatically removed after use (when persist=False)
- File systems are isolated between containers
- Host system access is restricted to mounted directories only
- Downloads are performed with timeout protection

## Project Structure

```
sandbox_server/
├── sandbox_server.py     # Main server implementation
├── pyproject.toml        # Project configuration
├── README.md            # This file
├── .gitignore           # Git ignore patterns
├── .python-version      # Python version specification
└── uv.lock             # UV lock file
```

## Available Tools

The server provides six main tools:

1. **`create_container_environment`**: Creates a new Docker container with specified image
   - Parameters: `image`, `persist`, `host_workspace_path` (optional), `download_url` (optional)
   - Creates containers with optional file downloads and host directory mounting

2. **`create_file_in_container`**: Creates a file in a container
   - Parameters: `container_id`, `filename`, `content`
   - Files are created in the `/workspace` directory

3. **`execute_command_in_container`**: Runs commands in a container
   - Parameters: `container_id`, `command`
   - Executes in `/workspace` with non-interactive environment

4. **`save_container_state`**: Saves the container state as a Docker image
   - Parameters: `container_id`, `name`
   - Creates a reusable Docker image from current container state

5. **`export_dockerfile`**: Generates a Dockerfile to recreate the environment
   - Parameters: `container_id`
   - Exports a Dockerfile with base image and file copies

6. **`exit_container`**: Stops and removes a running container
   - Parameters: `container_id`, `force` (optional)
   - Cleans up containers and temporary directories

## Error Handling

The server includes robust error handling for:
- Missing Docker images
- Network timeouts during downloads
- Container not found scenarios
- File system operations
- Docker daemon connectivity issues

Each tool provides clear error messages to help diagnose and resolve issues.