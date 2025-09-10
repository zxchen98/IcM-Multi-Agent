"""
Azure CLI Tool for container management operations - ASYNC VERSION
Integrated with streaming callbacks for real-time output

Prerequisites:
- Azure CLI installed and configured
- Appropriate Azure permissions for container operations
"""

import asyncio
import json
import sys
from typing import List, Dict, Any, Optional

# Import streaming callbacks
from streaming.callbacks import get_current_callbacks


class AzureCliTool:
    """Tool for Azure CLI operations with streaming support"""
    
    def __init__(self):
        self.available = None  # Will be set by async_init()
        self.is_windows = sys.platform.startswith('win')
    
    async def async_init(self):
        """Async initialization"""
        self.available = await self._check_azure_cli()
    
    async def _execute_command(self, command: str, timeout: int = 60):
        """
        Execute Azure CLI command in a cross-platform way
        
        Args:
            command (str): Full command to execute (e.g., 'az --version')
            timeout (int): Timeout in seconds
            
        Returns:
            tuple: (returncode, stdout, stderr)
        """
        try:
            if self.is_windows:
                # On Windows, use shell to handle .cmd files
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                # On Linux/Mac, use exec for better security and performance
                cmd_parts = command.split()
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return process.returncode, stdout, stderr
            
        except asyncio.TimeoutError:
            if 'process' in locals():
                process.kill()
                await process.wait()
            raise asyncio.TimeoutError(f"Command timed out after {timeout} seconds: {command}")
        except Exception as e:
            raise Exception(f"Command execution failed: {command} - {str(e)}")

    async def _check_azure_cli(self) -> bool:
        """Check if Azure CLI is available"""
        try:
            # Simple check: run 'az --version' to verify CLI is installed and working
            returncode, stdout, stderr = await self._execute_command('az --version', timeout=10)
            return returncode == 0
        except (asyncio.TimeoutError, FileNotFoundError, Exception):
            return False
            
    async def list_containers(self, resource_group: str, subscription: str) -> List[Dict[str, Any]]:
        """
        List containers in a specific resource group
        
        Args:
            resource_group (str): Azure resource group name
            subscription (str): Azure subscription ID
            
        Returns:
            List[Dict[str, Any]]: List of container information
        """
        if not self.available:
            print("🔧 Azure CLI not available, skipping container list")
            return []
        
        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            command = f"az container list --resource-group {resource_group} --subscription {subscription}"
            
            # Stream tool start
            if callbacks:
                await callbacks.on_tool_start("Azure CLI Tool", "Azure CLI", {
                    "command": command,
                    "operation": "list_containers",
                    "resource_group": resource_group,
                    "subscription": subscription
                })
            
            print(f"🔧 Executing: {command}")
            
            returncode, stdout, stderr = await self._execute_command(command, timeout=60)
            
            if returncode == 0:
                containers = json.loads(stdout.decode()) if stdout.strip() else []
                container_names = [container.get('name', 'Unknown') for container in containers]
                
                print(f"✅ Found {len(containers)} containers in {resource_group}")
                if containers:
                    print(f"📋 Container names: {', '.join(container_names)}")
                
                # Stream tool end with result with container names
                result_msg = f"Found {len(containers)} containers"
                if containers:
                    result_msg += f": {', '.join(container_names)}"
                
                if callbacks:
                    await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", result_msg)
                
                return containers
            else:
                error_msg = f"List command failed: {stderr.decode()}"
                print(f"❌ {error_msg}")
                if callbacks:
                    await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
                return []
                
        except asyncio.TimeoutError:
            error_msg = "List command timed out"
            print(f"❌ {error_msg}")
            if callbacks:
                await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
            return []
        except Exception as e:
            error_msg = f"Error listing containers: {str(e)}"
            print(f"❌ {error_msg}")
            if callbacks:
                await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
            return []

    async def show_container(self, container_name: str, resource_group: str, subscription: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific container
        
        Args:
            container_name (str): Name of the container
            resource_group (str): Azure resource group name
            subscription (str): Azure subscription ID
            
        Returns:
            Optional[Dict[str, Any]]: Container details or None if not found
        """
        if not self.available:
            print("🔧 Azure CLI not available, skipping container show")
            return None
        
        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            command = f"az container show --name {container_name} --resource-group {resource_group} --subscription {subscription}"
            
            # Stream tool start
            if callbacks:
                await callbacks.on_tool_start("Azure CLI Tool", "Azure CLI", {
                    "command": command,
                    "operation": "show_container",
                    "container_name": container_name,
                    "resource_group": resource_group,
                    "subscription": subscription
                })
            
            print(f"🔧 Executing: {command}")
            
            returncode, stdout, stderr = await self._execute_command(command, timeout=60)
            
            if returncode == 0:
                container_info = json.loads(stdout.decode())
                print(f"✅ Retrieved details for container {container_name}")
                
                if callbacks:
                    await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", f"Retrieved container details: {container_name}. {str(container_info)[:300]}...")
                
                return container_info
            else:
                error_msg = f"Show command failed: {stderr.decode()}"
                print(f"❌ {error_msg}")
                if callbacks:
                    await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
                return None
                
        except asyncio.TimeoutError:
            error_msg = "Show command timed out"
            print(f"❌ {error_msg}")
            if callbacks:
                await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
            return None
        except Exception as e:
            error_msg = f"Error showing container: {str(e)}"
            print(f"❌ {error_msg}")
            if callbacks:
                await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
            return None

    async def restart_container(self, container_name: str, resource_group: str, subscription: str) -> bool:
        """
        Restart a container by stopping and then starting it
        
        Args:
            container_name (str): Name of the container
            resource_group (str): Azure resource group name
            subscription (str): Azure subscription ID
            
        Returns:
            bool: True if restart was successful, False otherwise
        """
        if not self.available:
            print("🔧 Azure CLI not available, skipping container restart")
            return False

        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            # Step 1: Stop the container
            stop_command = f"az container stop --name {container_name} --resource-group {resource_group} --subscription {subscription}"
            
            if callbacks:
                await callbacks.on_tool_start("Azure CLI Tool", "Azure CLI", {
                    "command": stop_command,
                    "operation": "stop_container",
                    "container_name": container_name,
                    "resource_group": resource_group,
                    "subscription": subscription
                })
            
            print(f"🛑 Stopping container: {container_name}")
            print(f"🔧 Executing: {stop_command}")
            
            # Execute stop with streaming output
            stop_success = await self._execute_with_streaming(stop_command, "Stopping container", callbacks, timeout=180)
            
            if stop_success:
                print(f"✅ Container {container_name} stopped successfully")
            else:
                print(f"⚠️ Container {container_name} stop failed, continuing with start...")
            
            # Step 2: Start the container (regardless of stop result)
            start_command = f"az container start --name {container_name} --resource-group {resource_group} --subscription {subscription}"
            
            if callbacks:
                await callbacks.on_tool_start("Azure CLI Tool", "Azure CLI", {
                    "command": start_command,
                    "operation": "start_container",
                    "container_name": container_name,
                    "resource_group": resource_group,
                    "subscription": subscription
                })
            
            print(f"� Starting container: {container_name}")
            print(f"�🔧 Executing: {start_command}")
            
            # Execute start with streaming output
            start_success = await self._execute_with_streaming(start_command, "Starting container", callbacks, timeout=180)
            
            if start_success:
                restart_status = "stop + start" if stop_success else "start only (stop failed)"
                print(f"✅ Container {container_name} restarted successfully ({restart_status})")
                if callbacks:
                    await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", f"Container {container_name} restarted successfully ({restart_status})")
                return True
            else:
                error_msg = f"Failed to start container {container_name}"
                print(f"❌ {error_msg}")
                if callbacks:
                    await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
                return False
                
        except asyncio.TimeoutError:
            error_msg = f"Container restart timed out (3 minutes) for {container_name}"
            print(f"❌ {error_msg}")
            if callbacks:
                await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
            return False
        except Exception as e:
            error_msg = f"Error restarting container {container_name}: {str(e)}"
            print(f"❌ {error_msg}")
            if callbacks:
                await callbacks.on_tool_end("Azure CLI Tool", "Azure CLI", error_msg)
            return False

    async def _execute_with_streaming(self, command: str, operation_name: str, callbacks, timeout: int = 180) -> bool:
        """
        Execute command with streaming output and progress updates
        
        Args:
            command (str): Command to execute
            operation_name (str): Name of the operation for logging
            callbacks: Callback object for streaming
            timeout (int): Timeout in seconds (default 3 minutes)
            
        Returns:
            bool: True if command succeeded, False otherwise
        """
        try:
            if self.is_windows:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                cmd_parts = command.split()
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            # Start progress indicator
            progress_task = None
            if callbacks:
                progress_task = asyncio.create_task(self._show_progress(operation_name, callbacks))
            
            try:
                # Wait for process to complete with timeout
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                
                # Stop progress indicator
                if progress_task:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
                
                # Check result
                if process.returncode == 0:
                    # Success - no output or minimal output
                    if stdout.strip():
                        print(f"📄 Output: {stdout.decode().strip()}")
                    return True
                else:
                    # Error - show error message
                    error_output = stderr.decode().strip() if stderr else "Unknown error"
                    print(f"❌ Error: {error_output}")
                    return False
                    
            except asyncio.TimeoutError:
                # Stop progress indicator
                if progress_task:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
                
                # Kill the process
                process.kill()
                await process.wait()
                print(f"❌ {operation_name} timed out after {timeout} seconds")
                raise asyncio.TimeoutError(f"{operation_name} timed out")
                
        except Exception as e:
            print(f"❌ Command execution failed: {str(e)}")
            return False

    async def _show_progress(self, operation_name: str, callbacks, interval: float = 2.0):
        """
        Show progress dots while operation is running
        
        Args:
            operation_name (str): Name of the operation
            callbacks: Callback object
            interval (float): Update interval in seconds
        """
        dots = 0
        try:
            while True:
                dots = (dots + 1) % 4
                progress_msg = f"{operation_name}{'.' * dots}"
                if callbacks:
                    await callbacks.on_agent_message("System", progress_msg)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            # Operation completed
            if callbacks:
                await callbacks.on_agent_message("System", f"{operation_name} completed")
            raise

    async def find_container_by_type(self, resource_group: str, runner_type: str, subscription: str = None) -> Optional[str]:
        """
        Find container by runner type in a resource group
        
        Args:
            resource_group (str): Azure resource group name
            runner_type (str): Type of runner to find
            subscription (str): Azure subscription ID (optional)
            
        Returns:
            Optional[str]: Container name if found, None otherwise
        """
        if not self.available:
            print("🔧 Azure CLI not available, skipping container search")
            return None
        
        try:
            # List containers in the resource group (this will send its own callback)
            containers = await self.list_containers(resource_group, subscription) if subscription else await self.list_all_containers()
            
            # Search for container matching the runner type
            for container in containers:
                container_name = container.get('name', '')
                # Simple matching - look for runner_type in container name
                if runner_type.lower() in container_name.lower():
                    print(f"✅ Found container '{container_name}' for runner type '{runner_type}'")
                    return container_name
            
            print(f"❌ No container found for runner type '{runner_type}' in resource group '{resource_group}'")
            return None
            
        except Exception as e:
            print(f"❌ Error searching for container: {str(e)}")
            return None


# Create singleton instance
azure_cli_tool = AzureCliTool()
