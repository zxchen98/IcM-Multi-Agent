"""
Azure CLI Tool for container management operations

Prerequisites:
- Azure CLI installed and configured
- Appropriate Azure permissions for container operations
"""

import subprocess
import json
from typing import List, Dict, Any, Optional

class AzureCliTool:
    """Tool for Azure CLI operations"""
    
    def __init__(self):
        self.available = self._check_azure_cli()
    
    def _check_azure_cli(self) -> bool:
        """Check if Azure CLI is available"""
        try:
            # Simple check: run 'az --version' to verify CLI is installed and working
            # Use shell=True on Windows to handle .bat files properly
            result = subprocess.run(['az', '--version'], 
                                  capture_output=True, text=True, timeout=10, shell=True)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False
            
    
    def list_containers(self, resource_group: str, subscription: str) -> List[Dict[str, Any]]:
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
        
        try:
            command = f"az container list --resource-group {resource_group} --subscription {subscription}"
            print(f"🔧 Executing: {command}")
            
            result = subprocess.run(
                ['az', 'container', 'list', '--resource-group', resource_group, '--subscription', subscription],
                capture_output=True,
                text=True,
                timeout=60,
                shell=True
            )
            
            if result.returncode == 0:
                containers = json.loads(result.stdout) if result.stdout.strip() else []
                container_names = [container.get('name', 'Unknown') for container in containers]
                
                print(f"✅ Found {len(containers)} containers in {resource_group}")
                if containers:
                    print(f"📋 Container names: {', '.join(container_names)}")
                
                return containers
            else:
                error_msg = f"Command failed: {result.stderr}"
                print(f"❌ {error_msg}")
                return []
                
        except Exception as e:
            error_msg = f"Error executing Azure CLI: {str(e)}"
            print(f"❌ {error_msg}")
            return []
    
    def show_container(self, container_name: str, resource_group: str, subscription: str) -> Optional[Dict[str, Any]]:
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
        
        try:
            command = f"az container show --name {container_name} --resource-group {resource_group} --subscription {subscription}"
            print(f"🔧 Executing: {command}")
            
            result = subprocess.run(
                ['az', 'container', 'show', '--name', container_name, '--resource-group', resource_group, '--subscription', subscription],
                capture_output=True,
                text=True,
                timeout=60,
                shell=True
            )
            
            if result.returncode == 0:
                container_details = json.loads(result.stdout) if result.stdout.strip() else None
                print(f"✅ Retrieved details for container {container_name}")
                return container_details
            else:
                error_msg = f"Command failed: {result.stderr}"
                print(f"❌ {error_msg}")
                return None
                
        except Exception as e:
            error_msg = f"Error executing Azure CLI: {str(e)}"
            print(f"❌ {error_msg}")
            return None
    
    def _check_container_running(self, container_name: str, resource_group: str, subscription: str) -> bool:
        """
        Check if a container is actually running by querying its status
        
        Args:
            container_name (str): Name of the container
            resource_group (str): Azure resource group name
            subscription (str): Azure subscription ID
            
        Returns:
            bool: True if container is running, False otherwise
        """
        try:
            container_status = self.show_container(container_name, resource_group, subscription)
            if container_status:
                sub_container_status = [
                    container_dict.get("instanceView", {}).get("currentState", {}).get("state") 
                    for container_dict in container_status.get("containers", []) 
                    if container_dict.get("name") == container_name
                ]
                return any(status == "Running" for status in sub_container_status)
            return False
        except Exception as check_error:
            print(f"⚠️ Could not verify container status: {check_error}")
            return False

    def restart_container(self, container_name: str, resource_group: str, subscription: str) -> bool:
        """
        Restart a container
        
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
        
        try:
            # Step 1: Stop the container
            stop_command = f"az container stop --name {container_name} --resource-group {resource_group} --subscription {subscription}"
            print(f"🔧 Executing: {stop_command}")

            stop_result = subprocess.run(
                ['az', 'container', 'stop', '--name', container_name, '--resource-group', resource_group, '--subscription', subscription],
                capture_output=True,
                text=True,
                timeout=180,  # Stop might take longer
                shell=True
            )
            
            if stop_result.returncode == 0:
                print(f"✅ Successfully stopped container {container_name}")
            else:
                error_msg = f"Stop failed: {stop_result.stderr}"
                print(f"❌ {error_msg}")
                
            # Step 2: Start the container
            start_command = f"az container start --name {container_name} --resource-group {resource_group} --subscription {subscription}"
            print(f"🔧 Executing: {start_command}")

            start_result = subprocess.run(
                ['az', 'container', 'start', '--name', container_name, '--resource-group', resource_group, '--subscription', subscription],
                capture_output=True,
                text=True,
                timeout=300,  # Increased timeout for start operation
                shell=True
            )

            if start_result.returncode == 0:
                print(f"✅ Successfully started container {container_name}")
                return True
            else:
                error_msg = f"Start failed: {start_result.stderr}"
                print(f"❌ {error_msg}")
                
                # Check actual container status as fallback
                if self._check_container_running(container_name, resource_group, subscription):
                    print(f"✅ Container {container_name} appears to be running despite start command failure")
                    return True
                return False

        except subprocess.TimeoutExpired as e:
            error_msg = f"Command '{' '.join(e.cmd)}' timed out after {e.timeout} seconds"
            print(f"❌ Error restarting container: {error_msg}")
            
            # For timeout on start command, check if container actually started
            if 'start' in ' '.join(e.cmd):
                print("⏱️ Start command timed out - checking if container actually started...")
                import time
                time.sleep(10)  # Brief wait
                if self._check_container_running(container_name, resource_group, subscription):
                    print(f"✅ Container {container_name} is running despite timeout")
                    return True
            
            return False
            
        except Exception as e:
            error_msg = f"Error restarting container: {str(e)}"
            print(f"❌ {error_msg}")
            return False
    
    def find_container_by_type(self, resource_group: str, runner_type: str, subscription: str = None) -> Optional[str]:
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
            # List containers in the resource group
            containers = self.list_containers(resource_group, subscription) if subscription else self.list_all_containers()
            
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