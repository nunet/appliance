# LLM Deployment - Personal AI Demo

This demo showcases a private, multi-node AI assistant deployment using the Nunet Appliance platform. It demonstrates how to build a personal AI system where your conversations and data remain completely private while leveraging distributed computing resources.

## Overview

The demo implements a personal AI assistant using:
- **OpenWebUI** - A modern, user-friendly web interface for AI interactions (deployed locally)
- **Ollama** - A lightweight LLM server for running AI models (deployed remotely)

This architecture ensures that all conversation history is stored locally on your machine, maintaining complete privacy while allowing you to harness computational resources from remote nodes.

## Video Recording

[LLM Deployment on Nunet](https://drive.google.com/file/d/1B1XAepb7Kwsqfkou5k-R2SR3b9CEIj-s/view?usp=drive_link)

## Nunet Ensemble

The demo uses the [openwebui-local-ollama-remote.yaml](openwebui-local-ollama-remote.yaml) ensemble configuration to deploy a distributed AI system across multiple nodes.

### Services

**OpenWebUI Service** (Local Node):
- Docker container running the OpenWebUI web interface
- Resource allocation: 1 CPU core, 2GB RAM, 5GB disk
- Environment configuration for authentication and backend connection
- Accessible via public port 17000, private port 8080

**Ollama Service** (Remote Node):
- Docker container running the Ollama LLM server
- Resource allocation: 3 CPU cores, 12GB RAM, 15GB disk, NVIDIA GPU
- Persistent volume for model storage at `/home/ubuntu/ollama`
- GPU acceleration enabled with NVIDIA runtime
- Accessible via public port 17600, private port 11434

### Networking

The ensemble establishes secure inter-service communication:
- **Local Node**: Runs OpenWebUI with public exposure through DDNS
- **Remote Node**: Hosts Ollama service accessible from the local node
- **Service Discovery**: Automatic DNS resolution between services
- **Port Mapping**: External ports mapped to internal container ports

The configuration ensures all conversation data remains on the local node while leveraging GPU resources from the remote node for model inference.

### Dynamic DNS

Secure https access to OpenWebUI web interface using the DDNS url generated as part of the deployment manifest

### Data Persistence

Nunet supports multiple data persistence options for production use. 

#### Local Volume Persistence

For cases with access to remote machines, you can configure local volume mounts in the ensemble:

```yaml
allocations:
  <allocation_name>:
    # ... other configuration
    volume:
      - type: local
        src: "/path/to/local/storage"
        mount_destination: "/workspace/output"
        read_only: false
```

#### GlusterFS Distributed Storage

It is possible to setup your own GlusterFS servers and specify the same in the ensemble.

```yaml
allocations:
  <allocation_name>:
    # ... other configuration
    volume:
      - type: glusterfs
        name: <volume_name>
        mount_destination: "/workspace/output"
        servers: ["glusterfs-server"]
        client_private_key: /path/to/glusterfs.key
        client_pem: /path/to/glusterfs.pem
        client_ca: /path/to/glusterfs.ca
```

This demo uses local volume option.

## Prerequisites

Nunet Appliance running on both nodes and onboarding process completed to join an organisation.

## Getting Help

- Join the Nunet community for support
- Check the Nunet Appliance documentation
- Review OpenWebUI and Ollama documentation

## License

This demo configuration is provided under the same license as the Nunet Appliance project.