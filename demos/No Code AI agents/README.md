# No-Code AI Agents Demo

This demo showcases how to build AI agents and automation workflows without writing any code, using the Nunet Appliance. It demonstrates the integration of n8n (workflow automation) with Ollama (LLM server) to create intelligent, automated workflows that can process data, make decisions, and perform complex tasks.

## Overview

The demo implements a complete no-code AI agent platform using:
- **n8n** - Visual workflow automation platform for building complex workflows
- **Ollama** - Local LLM server for AI-powered decision making and text generation
- **Persistent Storage** - Data persistence for workflows and AI models

## Video Recording

[No code AI agents on Nunet](https://drive.google.com/file/d/1eB7V_4YbqMlLxP5c3kRaleM8WgBVYWz5/view?usp=drive_link)

## Nunet Ensemble

The demo uses the [n8n-ollama.yaml](n8n-ollama.yaml) ensemble configuration to deploy a complete no-code AI agent platform on a single node.

### Configuration

**Ollama LLM Service**:
- Docker container based on `ollama/ollama:latest`
- Resource allocation: 2 CPU cores, 8GB RAM, 20GB disk, NVIDIA GPU with 16GB VRAM
- Persistent volume for model storage at `/home/ubuntu/ollama`
- GPU acceleration with CUDA support
- Accessible via internal port 11434, external port 17500

**n8n Workflow Service**:
- Docker container based on `n8nio/n8n:latest`
- Resource allocation: 2 CPU cores, 4GB RAM, 5GB disk
- Persistent volume for workflow data at `/home/ubuntu/n8n_data`
- Integrated with Ollama service via internal networking
- Configured for DDNS access and proxy support

### Service Integration

The ensemble establishes seamless integration between n8n and Ollama:
- **Internal Networking**: n8n connects to Ollama via `http://ollama-llm.internal:17500`
- **Data Persistence**: Both services maintain persistent data storage
- **GPU Resource Sharing**: Ollama leverages GPU resources for LLM inference
- **Workflow Persistence**: n8n workflows are saved persistently

### Data Persistence

This demo uses local volume persistence for both services:

**Ollama Model Storage**:
```yaml
volume:
  - type: local
    src: "/home/ubuntu/ollama"
    mount_destination: "/root/.ollama"
    read_only: false
```

**n8n Workflow Data**:
```yaml
volume:
  - type: local
    src: "/home/ubuntu/n8n_data"
    mount_destination: "/home/node/.n8n"
    read_only: false
```

**Persisted Data Types**:
- **LLM Models**: Downloaded models stored persistently
- **Workflow Definitions**: Created workflows saved permanently
- **Execution History**: Workflow run logs and results
- **Configuration Data**: Service settings and credentials

### Dynamic DNS
Secure https access to n8n web interface using the DDNS url generated as part of the deployment manifest

## Prerequisites

### Hardware Requirements
GPU Node with sufficient memory and storage

### Software Requirements
- Nunet Appliance running on the nodes
- Completed onboarding process to join an organisation

## Installation & Setup

### 1. Deploy the Ensemble

Deploy the no-code AI agent platform via Nunet Appliance web interface

### 2. Access the Services

Once deployed, you can access services:

- **n8n Interface**: Access via the DDNS URL provided in the deployment manifest
- **Ollama API**: Available internally at `http://ollama-llm.internal:17500`

## Building AI Agents with n8n

### Getting Started with n8n

1. **Access n8n**: Open the n8n interface via your browser
2. **Create First Workflow**: Start with a simple AI-powered workflow
3. **Configure Ollama Connection**: Set up connection to Ollama by using the internal DNS and port

It is possible to use API keys of other providers like OpenAI, Anthropic etc

### Getting Help

- Join the Nunet community for support
- Review n8n and Ollama documentation

## External Resources

- [n8n Documentation](https://docs.n8n.io/)
- [Ollama Documentation](https://ollama.com/docs)
- [n8n Community](https://community.n8n.io/)
- [Ollama Model Library](https://ollama.com/library)

## License

This demo configuration is provided under the same license as the Nunet Appliance project.