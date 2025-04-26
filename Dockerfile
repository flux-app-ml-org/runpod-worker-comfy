# Stage 1: Base image with common dependencies
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 as base

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1 

# Install Python, git and other necessary tools
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    wget

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /comfyui && \
    cd /comfyui && \
    git checkout 9899d187b16a9a823a98fc1df9bf1fbb58674087

# Change working directory to ComfyUI
WORKDIR /comfyui

# Install ComfyUI dependencies
RUN pip3 install torch torchvision torchaudio xformers --index-url https://download.pytorch.org/whl/cu126 \
    && pip3 install --upgrade -r requirements.txt

# Install additional dependencies from requirements.txt in the project root
COPY requirements.txt /requirements.txt
RUN pip3 install --upgrade -r /requirements.txt

# Support for the network volume
ADD src/extra_model_paths.yaml ./

# Go back to the root
WORKDIR /

# Add the start and the handler
ADD src/start.sh src/rp_handler.py test_input.json ./
RUN chmod +x /start.sh

# Add the script to clone custom nodes
COPY workflows/custom_nodes.txt /workflows/custom_nodes.txt
COPY clone_and_install.sh /clone_and_install.sh
RUN chmod +x /clone_and_install.sh

# Stage 2: Downloader stage for downloading models
FROM base as downloader

# Install wget
RUN apt-get update && apt-get install -y wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Download DepthAnything model
RUN mkdir -p /models/depthanything && \
    wget -O /models/depthanything/depth_anything_v2_vitl_fp32.safetensors \
    https://huggingface.co/Kijai/DepthAnythingV2-safetensors/resolve/main/depth_anything_v2_vitl_fp32.safetensors/

# Stage 3: Final stage
FROM base as final

# Copy the downloaded model from the downloader stage
COPY --from=downloader /models/depthanything /comfyui/models/depthanything

# Execute the script to clone repositories and install dependencies
RUN /clone_and_install.sh

# Start the container
CMD /start.sh
