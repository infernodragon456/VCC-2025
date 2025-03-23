# VM Auto-Scaling: Local to GCP

This project implements a mechanism to monitor local VM resource usage and automatically scale to Google Cloud Platform (GCP) when resource usage exceeds 75%.

## Architecture

![Auto-scaling Architecture](https://i.imgur.com/YYPdCN2.png)

The system consists of the following components:

1. **Demo Application**: A simple Flask web application that can be stressed to simulate high CPU and memory usage
2. **Prometheus & Node Exporter**: For monitoring resource usage 
3. **Nginx**: Acts as a load balancer between local and GCP instances
4. **Autoscaler**: Python script that monitors resource usage and creates/destroys GCP instances as needed

## Prerequisites

- Lubuntu or similar Linux distribution
- Docker and Docker Compose
- Google Cloud Platform account
- GCP Service Account with appropriate permissions
- GCP Service Account key JSON file

## Setup Instructions

1. **Clone the Repository**

```bash
cd vm-autoscaler
```

2. **Place your GCP Service Account key in the project directory**

```bash
# Copy your service account key to the vm-autoscaler directory
cp /path/to/your-service-account-key.json vm-autoscaler/service-account-key.json
```

3. **Run the setup script**

```bash
# Make the script executable
chmod +x setup.sh

# Run the setup script with sudo
sudo ./setup.sh
```

4. **Edit the autoscaler configuration**

Open `scripts/autoscaler.py` and update the `DEFAULT_PROJECT_ID` with your GCP project ID:

```python
DEFAULT_PROJECT_ID = "your-gcp-project-id"  # Replace with your actual GCP project ID
```

5. **Start the Docker containers**

```bash
docker-compose up -d
```

6. **Run the autoscaler**

```bash
# Run in normal mode
python3 scripts/autoscaler.py --project-id=YOUR_PROJECT_ID --credentials=./service-account-key.json

# Or run in dry-run mode (no actual changes to GCP)
python3 scripts/autoscaler.py --project-id=YOUR_PROJECT_ID --credentials=./service-account-key.json --dry-run
```

## Usage

1. **Access the demo application**

Open your browser and navigate to:
```
http://localhost
```

2. **Monitor resources**

Access Prometheus to view resource metrics:
```
http://localhost:9090
```

3. **Generate load**

Use the "Stress CPU" and "Stress Memory" buttons on the demo application to generate load.

When resource usage exceeds 75% for 3 consecutive checks, the autoscaler will create a new GCP instance and configure Nginx to balance the load between the local VM and the GCP instance. This will reduce the load on your local VM.

## Monitoring Autoscaling

The autoscaler will print its status to the console. You can monitor it to see when it scales out to GCP or scales back in.

## Clean Up

To stop all containers:

```bash
docker-compose down
```

To delete GCP instances created by the autoscaler:

```bash
gcloud compute instances list --filter="name~'app-instance'"
gcloud compute instances delete INSTANCE_NAME --zone=us-central1-a
```

## How It Works

1. **Resource Monitoring**: 
   - Prometheus and Node Exporter collect system metrics
   - The autoscaler queries Prometheus every 30 seconds

2. **Scale-Out Process**:
   - When resource usage exceeds 75% for 3 consecutive checks
   - Creates a new GCP VM instance
   - Deploys the application container to GCP
   - Updates Nginx configuration to distribute traffic

3. **Scale-In Process**:
   - When resource usage falls below 30% for 5 consecutive checks
   - Removes a GCP instance
   - Updates Nginx configuration

4. **Load Balancing**:
   - Nginx distributes incoming requests between local and GCP instances
   - Reduces load on the local VM

## Troubleshooting

**Problem**: Unable to connect to Prometheus
**Solution**: Make sure the containers are running with `docker ps` and check Prometheus logs with `docker logs prometheus`

**Problem**: Autoscaler can't create GCP instances
**Solution**: Verify your service account key has the correct permissions (Compute Admin, Storage Admin)

**Problem**: High resource usage doesn't trigger scaling
**Solution**: Check the Prometheus queries in the autoscaler script and verify they're returning correct values 