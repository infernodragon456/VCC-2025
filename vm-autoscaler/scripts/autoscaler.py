#!/usr/bin/env python3
import os
import time
import json
import subprocess
import requests
import threading
import argparse
import base64  # Add base64 for encoding the service account key
from google.cloud import compute_v1
import google.auth

# Configuration Parameters
DEFAULT_PROJECT_ID = "PROJECT_ID"  # Replace with your GCP project ID
ZONE = "us-central1-a"
MACHINE_TYPE = "e2-standard-2"
INSTANCE_PREFIX = "app-instance"
PROMETHEUS_URL = "http://localhost:9090"
HIGH_THRESHOLD = 75  # Scale out when usage exceeds this percentage
LOW_THRESHOLD = 30   # Scale in when usage is below this percentage
CHECK_INTERVAL = 30  # Check resource usage every 30 seconds

class VMAutoscaler:
    def __init__(self, project_id, credentials_file, dry_run=False):
        self.project_id = project_id
        self.credentials_file = os.path.abspath(credentials_file)
        self.dry_run = dry_run
        self.gcp_instances = []
        self.lock = threading.Lock()
        
        # Set GCP credentials
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_file
        
        print(f"Autoscaler initialized with project: {project_id}")
        print(f"Credentials file: {self.credentials_file}")
        print(f"Dry run mode: {dry_run}")
        
        if not self.dry_run:
            # Initialize GCP clients
            self.instance_client = compute_v1.InstancesClient()
            
            # Create firewall rule for port 8080 if it doesn't exist
            self.ensure_firewall_rule_exists()
    
    def ensure_firewall_rule_exists(self):
        """Create a firewall rule for port 8080 if it doesn't exist"""
        try:
            # Initialize the firewall client
            firewall_client = compute_v1.FirewallsClient()
            
            # Try to get the firewall rule
            try:
                firewall_client.get(project=self.project_id, firewall="allow-app-traffic")
                print("Firewall rule 'allow-app-traffic' already exists")
                return
            except Exception:
                # Rule doesn't exist, create it
                pass
            
            print("Creating firewall rule to allow traffic on port 8080...")
            
            # Create the firewall rule
            firewall_rule = compute_v1.Firewall()
            firewall_rule.name = "allow-app-traffic"
            firewall_rule.direction = "INGRESS"
            firewall_rule.priority = 1000
            
            # Define allowed ports
            allowed = compute_v1.Allowed()
            allowed.I_p_protocol = "tcp"
            allowed.ports = ["8080"]
            firewall_rule.allowed = [allowed]
            
            # Apply to instances with the allow-8080 tag
            firewall_rule.target_tags = ["allow-8080"]
            
            # Allow from any source
            firewall_rule.source_ranges = ["0.0.0.0/0"]
            
            # Create the rule
            operation = firewall_client.insert(
                project=self.project_id,
                firewall_resource=firewall_rule
            )
            
            # Wait for the operation to complete
            print("Waiting for firewall rule creation to complete...")
            firewall_operations_client = compute_v1.GlobalOperationsClient()
            while True:
                result = firewall_operations_client.get(
                    project=self.project_id,
                    operation=operation.name
                )
                if result.status == compute_v1.Operation.Status.DONE:
                    if result.error:
                        print(f"Error creating firewall rule: {result.error.errors}")
                    else:
                        print("Firewall rule created successfully")
                    break
                time.sleep(1)
        
        except Exception as e:
            print(f"Error ensuring firewall rule exists: {e}")
            # Continue anyway - we don't want to fail the whole program if firewall rule creation fails
    
    def get_resource_usage(self):
        """Get CPU and memory usage from Prometheus"""
        cpu_query = "100 - (avg by(instance) (irate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"
        mem_query = "100 * (1 - ((node_memory_MemAvailable_bytes) / (node_memory_MemTotal_bytes)))"
        
        try:
            cpu_response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={'query': cpu_query})
            mem_response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={'query': mem_query})
            
            cpu_usage = 0
            mem_usage = 0
            
            if cpu_response.status_code == 200:
                result = cpu_response.json()['data']['result']
                if result:
                    cpu_usage = float(result[0]['value'][1])
                    
            if mem_response.status_code == 200:
                result = mem_response.json()['data']['result']
                if result:
                    mem_usage = float(result[0]['value'][1])
            
            print(f"Current usage - CPU: {cpu_usage:.1f}%, Memory: {mem_usage:.1f}%")
            return max(cpu_usage, mem_usage)  # Return the higher usage value
            
        except Exception as e:
            print(f"Error getting resource usage: {e}")
            return 0
    
    def list_instances(self):
        """List all GCP instances created by this autoscaler"""
        if self.dry_run:
            return self.gcp_instances
            
        try:
            request = compute_v1.ListInstancesRequest(
                project=self.project_id,
                zone=ZONE
            )
            instances = self.instance_client.list(request=request)
            
            managed_instances = []
            for instance in instances:
                if instance.name.startswith(INSTANCE_PREFIX):
                    for nic in instance.network_interfaces:
                        for config in nic.access_configs:
                            if hasattr(config, 'nat_ip'):
                                ip = config.nat_ip
                            elif hasattr(config, 'nat_i_p'):
                                ip = config.nat_i_p  # New field name
                            else:
                                continue
                                
                            managed_instances.append({
                                "name": instance.name,
                                "ip": ip,
                                "status": instance.status
                            })
                            break
            
            self.gcp_instances = managed_instances
            return managed_instances
            
        except Exception as e:
            print(f"Error listing instances: {e}")
            return []
    
    def create_instance(self, instance_id):
        """Create a new GCP instance running our application"""
        instance_name = f"{INSTANCE_PREFIX}-{instance_id}"
        
        if self.dry_run:
            print(f"[DRY RUN] Would create GCP instance: {instance_name}")
            self.gcp_instances.append({
                "name": instance_name,
                "ip": f"10.0.0.{instance_id}",  # Fake IP for dry run
                "status": "RUNNING"
            })
            return True
        
        try:
            # Configure the machine
            machine_type = f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}"
            
            # Configure the boot disk
            disk = compute_v1.AttachedDisk()
            disk.boot = True
            initialize_params = compute_v1.AttachedDiskInitializeParams()
            initialize_params.source_image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2004-lts"
            initialize_params.disk_size_gb = 20
            disk.initialize_params = initialize_params
            
            # Configure network interface
            network_interface = compute_v1.NetworkInterface()
            network_interface.name = "global/networks/default"
            access_config = compute_v1.AccessConfig()
            access_config.name = "External NAT"
            access_config.type_ = "ONE_TO_ONE_NAT"
            network_interface.access_configs = [access_config]
            
            # Read and extract service account email
            with open(self.credentials_file, 'rb') as f:
                key_content = f.read()
                key_data = json.loads(key_content)
                # Extract service account email from the key file
                service_account_email = key_data.get("client_email")
            
            # Create startup script to pull and run our app container
            startup_script = f"""#!/bin/bash
# Startup script for Ubuntu VM with GCS image
set -e

# Add proper logging
function log() {{
  echo "[$(date)] $1"
}}

log "Starting VM initialization"

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    log "Installing Docker"
    apt-get update
    apt-get install -y apt-transport-https ca-certificates curl software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
    add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
    apt-get update
    apt-get install -y docker-ce
fi

# Download the image from GCS
log "Downloading container image from GCS"
apt-get update && apt-get install -y wget
mkdir -p /tmp/docker
wget -O /tmp/docker/app-image.tar https://storage.googleapis.com/{self.project_id}-vm-images2/app-image.tar

# Load the image into Docker
log "Loading container image"
docker load -i /tmp/docker/app-image.tar

# Run the container 
log "Starting application container"
docker run -d --name app -p 8080:8080 gcr.io/{self.project_id}/vm-autoscaler-app:latest

# Open firewall port for the app
log "Configuring firewall"
ufw allow 8080/tcp

log "VM initialization complete"
"""
            
            # Add metadata
            metadata = compute_v1.Metadata()
            metadata_items = [
                compute_v1.Items(
                    key="startup-script",
                    value=startup_script
                )
            ]
            metadata.items = metadata_items
            
            # Define scopes
            scopes = [
                "https://www.googleapis.com/auth/devstorage.read_only",
                "https://www.googleapis.com/auth/logging.write",
                "https://www.googleapis.com/auth/monitoring.write",
                "https://www.googleapis.com/auth/servicecontrol",
                "https://www.googleapis.com/auth/service.management.readonly"
            ]
            
            # Create service account for the VM
            service_account = compute_v1.ServiceAccount(
                email=service_account_email,
                scopes=scopes
            )
            
            # Add network tags for firewall rules
            instance = compute_v1.Instance()
            instance.name = instance_name
            instance.machine_type = machine_type
            instance.disks = [disk]
            instance.network_interfaces = [network_interface]
            instance.metadata = metadata
            instance.tags = compute_v1.Tags(items=["http-server", "allow-8080"])
            instance.service_accounts = [service_account]  # Attach service account to VM
            
            print(f"Creating GCP instance: {instance_name}...")
            operation = self.instance_client.insert(
                project=self.project_id,
                zone=ZONE,
                instance_resource=instance
            )
            
            print(f"Waiting for instance creation to complete...")
            # Get the operations client
            operations_client = compute_v1.ZoneOperationsClient()
            while True:
                result = operations_client.get(
                    project=self.project_id,
                    zone=ZONE,
                    operation=operation.name
                )
                if result.status == compute_v1.Operation.Status.DONE:
                    if result.error:
                        print(f"Error creating instance: {result.error.errors}")
                        return False
                    break
                time.sleep(5)
            
            # Wait a bit more for the instance to initialize
            print("Waiting for instance to initialize...")
            time.sleep(10)
            
            # Update our instance list
            self.list_instances()
            
            # Update NGINX configuration
            self.update_load_balancer()
            
            return True
            
        except Exception as e:
            print(f"Error creating instance: {e}")
            return False
    
    def delete_instance(self, instance_name):
        """Delete a GCP instance"""
        if self.dry_run:
            print(f"[DRY RUN] Would delete GCP instance: {instance_name}")
            self.gcp_instances = [i for i in self.gcp_instances if i["name"] != instance_name]
            return True
        
        try:
            print(f"Deleting instance: {instance_name}")
            operation = self.instance_client.delete(
                project=self.project_id,
                zone=ZONE,
                instance=instance_name
            )
            
            print(f"Waiting for instance deletion to complete...")
            try:
                operations_client = compute_v1.ZoneOperationsClient()
                while True:
                    result = operations_client.get(
                        project=self.project_id,
                        zone=ZONE,
                        operation=operation.name
                    )
                    if result.status == compute_v1.Operation.Status.DONE:
                        break
                    time.sleep(5)
            except Exception:
                # Instance is already gone
                pass
            
            # Update our list of instances
            with self.lock:
                self.gcp_instances = [i for i in self.gcp_instances if i["name"] != instance_name]
            
            # Update NGINX configuration
            self.update_load_balancer()
            
            return True
            
        except Exception as e:
            print(f"Error deleting instance: {e}")
            return False
    
    def update_load_balancer(self):
        """Update NGINX load balancer configuration"""
        # Path to NGINX configuration
        nginx_conf_path = "/home/vighumandy/Study/sem6/vcc/VCC-2025/vm-autoscaler/config/nginx.conf"        
        # Create updated upstream config
        upstream_config = "upstream app_servers {\n"
        upstream_config += "    server app:8080 weight=10;\n"  # Local container
        
        with self.lock:
            for instance in self.gcp_instances:
                if instance.get("status", "") == "RUNNING":
                    upstream_config += f"    server {instance['ip']}:8080 weight=10;\n"
        
        upstream_config += "}\n"
        
        # Create the rest of the configuration
        server_config = """
server {
    listen 80;
    server_name localhost;
    
    location / {
        proxy_pass http://app_servers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""
        
        # Full configuration
        full_config = upstream_config + server_config
        
        # If not in dry run mode, actually update the file
        if not self.dry_run:
            try:
                with open(nginx_conf_path, 'w') as f:
                    f.write(full_config)
                
                # Reload NGINX (in a production environment, we'd use Docker/Kubernetes API)
                subprocess.run(["docker", "exec", "load-balancer", "nginx", "-s", "reload"])
                print("Updated NGINX load balancer configuration")
            except Exception as e:
                print(f"Error updating NGINX configuration: {e}")
        else:
            print(f"[DRY RUN] Would update NGINX configuration with {len(self.gcp_instances)} instances")
    
    def push_container_to_gcr(self):
        """Build and push our container to Google Container Registry"""
        if self.dry_run:
            print("[DRY RUN] Would build and push container to GCR")
            return True
        
        try:
            # Build the Docker image
            print("Building Docker image...")
            subprocess.run([
                "docker", "build", "-t", f"gcr.io/{self.project_id}/vm-autoscaler-app:latest", "/home/vighumandy/Study/sem6/vcc/VCC-2025/vm-autoscaler/app"
            ], check=True)
            
            # Save the Docker image to a file
            print("Saving Docker image to a tar file...")
            subprocess.run([
                "docker", "save", "-o", "/tmp/app-image.tar", f"gcr.io/{self.project_id}/vm-autoscaler-app:latest"
            ], check=True)
            
            # Create GCS bucket if it doesn't exist
            print("Creating GCS bucket (if it doesn't exist)...")
            subprocess.run([
                "/home/vighumandy/google-cloud-sdk/bin/gsutil", "mb", "-l", "us-central1", 
                f"gs://{self.project_id}-vm-images2"
            ], check=False)  # Don't check return code as it may already exist
            
            # Upload the image to GCS
            print("Uploading Docker image to GCS...")
            subprocess.run([
                "/home/vighumandy/google-cloud-sdk/bin/gsutil", "cp", "/tmp/app-image.tar", 
                f"gs://{self.project_id}-vm-images2/app-image.tar"
            ], check=True)
            
            # Make the object publicly accessible
            print("Making the uploaded image publicly accessible...")
            subprocess.run([
                "/home/vighumandy/google-cloud-sdk/bin/gsutil", "acl", "ch", "-u", "AllUsers:R", 
                f"gs://{self.project_id}-vm-images2/app-image.tar"
            ], check=True)
            
            print("Container successfully uploaded to GCS and made public")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error uploading container to GCS: {e}")
            return False
    
    def run(self):
        """Main autoscaling loop"""
        print("VM Autoscaler started")
        print(f"Resource threshold for scale-out: {HIGH_THRESHOLD}%")
        print(f"Resource threshold for scale-in: {LOW_THRESHOLD}%")
        print(f"Checking resource usage every {CHECK_INTERVAL} seconds")
        
        # Push our container to GCR
        if not self.push_container_to_gcr():
            print("Failed to push container to GCR. Autoscaler may not function correctly.")
        
        # Initial instance listing
        self.list_instances()
        
        # Tracking for consecutive threshold crossings
        high_usage_count = 0
        low_usage_count = 0
        
        try:
            while True:
                # Get current resource usage
                usage = self.get_resource_usage()
                
                # Check for scale-out (high usage)
                if usage > HIGH_THRESHOLD:
                    high_usage_count += 1
                    low_usage_count = 0
                    
                    if high_usage_count >= 3:  # Require consistent high usage
                        print(f"Resource usage exceeded {HIGH_THRESHOLD}% for 3 consecutive checks")
                        instance_id = len(self.gcp_instances) + 1
                        if self.create_instance(instance_id):
                            print(f"Created new instance: {INSTANCE_PREFIX}-{instance_id}")
                        high_usage_count = 0
                        
                        # Allow some time for the new instance to take effect
                        time.sleep(120)
                
                # Check for scale-in (low usage)
                elif usage < LOW_THRESHOLD and self.gcp_instances:
                    low_usage_count += 1
                    high_usage_count = 0
                    
                    if low_usage_count >= 5:  # More consecutive checks for scale-in
                        print(f"Resource usage below {LOW_THRESHOLD}% for 5 consecutive checks")
                        if self.gcp_instances:
                            # Remove the last added instance
                            instance_to_remove = self.gcp_instances[-1]["name"]
                            if self.delete_instance(instance_to_remove):
                                print(f"Deleted instance: {instance_to_remove}")
                            low_usage_count = 0
                            
                            # Allow some time for the scale-in to take effect
                            time.sleep(60)
                else:
                    # Reset counters if usage is in the normal range
                    high_usage_count = 0
                    low_usage_count = 0
                
                # Sleep before checking again
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\nAutoscaler stopped by user")
        except Exception as e:
            print(f"Error in autoscaler: {e}")
            
        print("Autoscaler stopped")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VM Autoscaler for GCP")
    parser.add_argument("--project-id", required=True, help="GCP Project ID")
    parser.add_argument("--credentials", required=True, help="Path to GCP service account key JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no actual changes)")
    
    args = parser.parse_args()
    
    autoscaler = VMAutoscaler(
        project_id=args.project_id,
        credentials_file=args.credentials,
        dry_run=args.dry_run
    )
    
    autoscaler.run() 