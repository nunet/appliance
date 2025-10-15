# LLM Fine Tuning Demo

This demo showcases how to perform fine-tuning of Large Language Models using the Nunet Appliance platform. It demonstrates the complete process of setting up a GPU-enabled environment and running a fine-tuning job on Llama 3.2 1B model using the DMS README dataset in Alpaca format.

## Overview

The demo implements a complete LLM fine-tuning pipeline using:
- **HuggingFace Transformers** - State-of-the-art transformer models and fine-tuning framework
- **Llama 3.2 1B Model** - Efficient small-scale model for demonstration
- **DMS README Dataset** - Custom dataset in Alpaca instruction format
- **GPU Acceleration** - NVIDIA GPU support for efficient training

This approach demonstrates how to leverage distributed GPU resources through Nunet Appliance to perform computationally intensive fine-tuning tasks while maintaining control over the training environment.

## Video Recording

[LLM fine tuning on Nunet](https://drive.google.com/file/d/1uBzMZTfzTtexzcRF6yNLvoFRe2g9VAhe/view?usp=drive_link)

## Nunet Ensemble

The demo uses the [llm-fine-tuning.yaml](llm-fine-tuning.yaml) ensemble configuration to deploy a GPU-accelerated fine-tuning environment.

### Configuration

**LLM Fine-Tuning Service**:
- Docker container based on `huggingface/transformers-pytorch-gpu:latest`
- Resource allocation: 3 CPU cores, 15GB RAM, 15GB disk, NVIDIA GPU
- Automatic execution of fine-tuning script on container startup
- HuggingFace authentication via environment variable

Note: We can also configure ensemble to specify allocaiton `llm-finetune`as `type: task` instead of `service` in case we want the deployment to finish once the fine tuning script is executed.

### Provisioning

The ensemble uses the [finetune-setup.sh](finetune-setup.sh) provision script to automatically set up the fine-tuning environment:

**Environment Setup**:
- System package installation (Python3, pip, wget, SSH server)
- Python dependencies installation for ML training
- Dataset and script download from Nunet GitLab repository
- HuggingFace authentication configuration
- Verification of installed packages

**Downloaded Training Assets**:
- **Training Script**: `ft-llama3.2-1b-dms-readme-alpaca-packing.py` - Main fine-tuning script with PEFT configuration
  [Download Link](https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/raw/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/ft-llama3.2-1b-dms-readme-alpaca-packing.py)
- **Requirements File**: `requirements.txt` - Python dependencies specification
  [Download Link](https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/raw/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/requirements.txt)
- **Dataset**: `dms_readme_alpaca.jsonl` - DMS documentation in Alpaca instruction format
  [Download Link](https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/raw/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/dms_readme_alpaca.jsonl)

**Key Dependencies**:
- `bitsandbytes>=0.41.1` - 4-bit optimizers and quantization
- `peft>=0.5.0` - Parameter-Efficient Fine-Tuning
- `flash-attn` - Optimized attention mechanism
- Additional ML libraries for training

### Training Process

The ensemble automatically executes the fine-tuning pipeline using the downloaded [fine-tuning script](https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/blob/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/ft-llama3.2-1b-dms-readme-alpaca-packing.py).

1. **Environment Setup** - Runs provision script to prepare the container
2. **Asset Download** - Downloads training script, requirements, and dataset
3. **Model Download** - Downloads Llama 3.2 1B model from HuggingFace
4. **Dataset Loading** - Loads `dms_readme_alpaca.jsonl` in Alpaca format
5. **Fine-Tuning** - Applies PEFT (Parameter-Efficient Fine-Tuning) techniques
6. **Model Saving** - Saves the fine-tuned model for later use

**Training Script Features**:
- **PEFT Configuration**: LoRA (Low-Rank Adaptation) setup for efficient fine-tuning
- **Quantization**: 4-bit model loading with bitsandbytes
- **Packing**: Efficient sequence packing for optimal GPU utilization
- **Batch Processing**: Configurable batch sizes for memory management
- **Checkpointing**: Automatic model checkpoint saving during training
- **Tensorboard Logs**: For monitoring tranining performance

### Data Persistence

The fine-tuning process generates valuable outputs including trained models, logs, and configuration files. While this demo runs in a stateless container, Nunet supports multiple data persistence options for production use.

#### Local Volume Persistence

For cases with access to remote machines, you can configure local volume mounts in the ensemble:

```yaml
allocations:
  llm-finetune:
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
  llm-finetune:
    # ... other configuration
    volume:
      - type: glusterfs
        name: llm-model-storage
        mount_destination: "/workspace/output"
        servers: ["glusterfs-server"]
        client_private_key: /path/to/glusterfs.key
        client_pem: /path/to/glusterfs.pem
        client_ca: /path/to/glusterfs.ca
```

#### Configuration Example

Here's how to modify the ensemble to include persistent storage:

```yaml
version: "V1"

allocations:
  llm-finetune:
    type: service
    executor: docker
    resources:
      cpu:
        cores: 3
      ram:
        size: 15
      disk:
        size: 15
      gpus:
        - vendor: NVIDIA
    execution:
      type: docker
      image: huggingface/transformers-pytorch-gpu:latest
      cmd: ["bash","-c","echo starting && date && python3 /LLM/ft-llama3.2-1b-dms-readme-alpaca-packing.py --output_dir /workspace/output && echo script-finished && date && tail -f /dev/null"]
      environment:
       - HF_TOKEN=<HuggingFace_Auth_Token>
    volume:
      - type: local
        src: "/home/ubuntu/models"
        mount_destination: "/workspace/output"
        read_only: false
    provision:
      - setup
```

## Prerequisites

### Hardware Requirements
- GPU Node with sufficient memory and storage

### Software Requirements
- Nunet Appliance running on all nodes
- Completed onboarding process to join an organisation
- HuggingFace account and access token for model downloads

### HuggingFace Setup

Before deploying, ensure you have:
1. A HuggingFace account with access to Llama models
2. Generated HuggingFace access token
3. Token configured in the ensemble environment variables

## Fine-Tuning Details

### Model Configuration
- **Base Model**: Llama 3.2 1B
- **Technique**: Parameter-Efficient Fine-Tuning (PEFT) using LoRA (Low Rank Adaptation)
- **Quantization**: 4-bit optimization with bitsandbytes
- **Attention**: Flash attention for improved performance

### Dataset Format
The demo uses a sample dataset made from Nunet [DMS readme](https://gitlab.com/nunet/device-management-service/-/blob/main/README.md?ref_type=heads). This dataset is automatically downloaded by the provision script from the Nunet GitLab repository.

**Dataset Structure**:
```json
{
  "instruction": "Human instruction about DMS functionality",
  "input": "Additional context or parameters (optional)",
  "output": "Expected model response explaining the concept"
}
```

**Dataset Characteristics**:
- **Format**: JSON Lines (.jsonl) for efficient loading
- **Content**: DMS README documentation and usage instructions
- **Purpose**: Trains the model to understand and explain DMS concepts
- **Source**: Nunet GitLab repository (downloaded during provisioning)

### Training Optimization
- **Memory Efficiency**: 4-bit quantization reduces memory usage
- **Speed Optimization**: Flash attention accelerates training
- **Parameter Efficiency**: PEFT reduces trainable parameters
- **Gradient Checkpointing**: Further memory optimization

## Output and Results

### Generated Artifacts
- **Fine-tuned model weights** - Saved adapter layers for the base model
- **Training logs** - Detailed loss metrics and training statistics
- **Configuration files** - Model hyperparameters and training settings

### Model Usage
After fine-tuning, the model can be:
- Loaded with the base Llama 3.2 1B model. A reference script to merge base model with the LoRA adapter can be found [here](https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/blob/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/model-merging.py).
- Used for inference on similar tasks
- Further fine-tuned with additional data
- Deployed in production environments

## Customization Options

### Dataset Customization
Replace the dataset with your own data:
1. Upload your dataset to the container
2. Ensure it's in Alpaca format
3. Update the data loading script

### Model Selection
Use different base models:
- Larger Llama variants (7B, 70B)
- Other open-source models
- Domain-specific models

### Training Parameters
Modify training hyperparameters in the fine tuning script:
- Learning rate and schedule
- Batch size and epochs
- LoRA parameters for PEFT
- etc

## Troubleshooting

### Common Issues

1. **HuggingFace Authentication Error**
   - Verify your HF_TOKEN is correct and valid
   - Ensure you have access to the Llama models
   - Check token permissions in HuggingFace settings

2. **GPU Memory Issues**
   - Reduce batch size in training script
   - Enable gradient checkpointing
   - Use smaller model variants

3. **Dependency Installation Failures**
   - Check container logs using the Nunet Appliance Web UI 

### Getting Help

- Join the Nunet community for support
- Review HuggingFace and PyTorch documentation

## External Resources

- [HuggingFace Transformers Documentation](https://huggingface.co/docs/transformers/)
- [PEFT Library Documentation](https://huggingface.co/docs/peft/)
- [Llama 3.2 Model Card](https://huggingface.co/meta-llama/Llama-3.2-1B)
- [Alpaca Dataset Format](https://crfm.stanford.edu/2023/03/13/alpaca.html)

## License

This demo configuration and scripts are provided under the same license as the Nunet Appliance project.