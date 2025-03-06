#!/bin/bash

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting LLM Meshtastic Agent with Hybrid Messaging...${NC}"

# Check if CUDA is available
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}CUDA found. Using GPU for inference.${NC}"
    USE_CPU=""
else
    echo -e "${YELLOW}CUDA not found. Using CPU for inference (this will be slow).${NC}"
    USE_CPU="--cpu-only"
fi

# Check if MQTT broker is reachable
MQTT_HOST=${1:-"10.0.0.159"}
MQTT_PORT=${2:-"1883"}
TCP_HOST=${3:-"10.0.0.133"}
TCP_PORT=${4:-"4403"}
PRIVATE_MODE=${5:-"broadcast"}
STARTUP_MSG=${6:-"default"}
LLM_CHANNEL=${7:-"default"}

if ping -c 1 $MQTT_HOST &> /dev/null; then
    echo -e "${GREEN}MQTT broker at $MQTT_HOST is reachable.${NC}"
else
    echo -e "${RED}Cannot reach MQTT broker at $MQTT_HOST${NC}"
    echo -e "${YELLOW}Will try to connect anyway...${NC}"
fi

if ping -c 1 $TCP_HOST &> /dev/null; then
    echo -e "${GREEN}Meshtastic TCP device at $TCP_HOST is reachable.${NC}"
else
    echo -e "${RED}Cannot reach Meshtastic TCP device at $TCP_HOST${NC}"
    echo -e "${YELLOW}Will try to connect anyway...${NC}"
fi

# Check if model exists locally
GGUF_MODEL_PATH="./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
if [ -f "$GGUF_MODEL_PATH" ]; then
    echo -e "${GREEN}Found local GGUF model at $GGUF_MODEL_PATH${NC}"
    MODEL_ARGS="--model TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
else
    echo -e "${YELLOW}Local GGUF model not found. Downloading from HuggingFace.${NC}"
    # Install tqdm if not already installed
    pip install tqdm --quiet
    
    # Create models directory if it doesn't exist
    mkdir -p ./models
    
    # Download the model
    echo -e "${GREEN}Downloading GGUF model from HuggingFace. This might take a while...${NC}"
    python download_model.py --gguf --model TheBloke/Mistral-7B-Instruct-v0.2-GGUF --gguf-file mistral-7b-instruct-v0.2.Q4_K_M.gguf
    
    if [ -f "$GGUF_MODEL_PATH" ]; then
        echo -e "${GREEN}Successfully downloaded GGUF model${NC}"
        MODEL_ARGS="--model TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
    else
        echo -e "${RED}Failed to download GGUF model${NC}"
        exit 1
    fi
fi

# Set private mode flag
if [ "$PRIVATE_MODE" = "private" ]; then
    echo -e "${GREEN}Running in private mode (only responding to direct messages)${NC}"
    PRIVATE_ARGS="--private"
elif [ "$PRIVATE_MODE" = "broadcast" ]; then
    echo -e "${GREEN}Running in broadcast mode (responding to all messages)${NC}"
    PRIVATE_ARGS="--broadcast"
else
    echo -e "${YELLOW}Using default mode from config.py${NC}"
    PRIVATE_ARGS=""
fi

# Set startup message flag
if [ "$STARTUP_MSG" = "yes" ]; then
    echo -e "${GREEN}Will send startup message${NC}"
    STARTUP_ARGS="--startup-message"
elif [ "$STARTUP_MSG" = "no" ]; then
    echo -e "${GREEN}Will NOT send startup message${NC}"
    STARTUP_ARGS="--no-startup-message"
else
    echo -e "${YELLOW}Using default startup message setting from config.py${NC}"
    STARTUP_ARGS=""
fi

# Set LLM channel flag
if [ "$LLM_CHANNEL" = "yes" ]; then
    echo -e "${GREEN}Will use dedicated LLM channel${NC}"
    LLM_ARGS="--use-llm-channel"
elif [ "$LLM_CHANNEL" = "no" ]; then
    echo -e "${GREEN}Will NOT use dedicated LLM channel${NC}"
    LLM_ARGS="--no-llm-channel"
else
    echo -e "${YELLOW}Using default LLM channel setting from config.py${NC}"
    LLM_ARGS=""
fi

# Start the agent
echo -e "${GREEN}Starting agent with hybrid messaging:${NC}"
echo -e "${GREEN}python3 main.py $MODEL_ARGS --mqtt-host $MQTT_HOST --mqtt-port $MQTT_PORT --tcp-host $TCP_HOST --tcp-port $TCP_PORT $PRIVATE_ARGS $STARTUP_ARGS $LLM_ARGS $USE_CPU${NC}"
python3 main.py $MODEL_ARGS --mqtt-host $MQTT_HOST --mqtt-port $MQTT_PORT --tcp-host $TCP_HOST --tcp-port $TCP_PORT $PRIVATE_ARGS $STARTUP_ARGS $LLM_ARGS $USE_CPU
