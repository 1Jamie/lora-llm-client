#!/bin/bash

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print section headers
print_header() {
    echo -e "\n${MAGENTA}====== $1 ======${NC}\n"
}

# Function to print success messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print info messages
print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Function to print warnings
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to ask for user input
ask_user() {
    echo -e "${BLUE}? $1${NC}"
}

# Function to check command existence
command_exists() {
    command -v "$1" &> /dev/null
}

# Function to check if a setting exists in a config file
setting_exists() {
    local file=$1
    local pattern=$2
    
    if [ ! -f "$file" ]; then
        # File doesn't exist, so the setting doesn't exist
        return 1
    fi
    
    if grep -q "$pattern" "$file"; then
        # Setting found
        return 0
    else
        # Setting not found
        return 1
    fi
}

# Function to attempt multiple connections to Meshtastic
try_meshtastic_connection() {
    local host=$1
    local port=$2
    local max_attempts=$3
    local attempt=1
    local connected=false
    
    while [ $attempt -le $max_attempts ]; do
        print_info "Connection attempt $attempt/$max_attempts to Meshtastic device at $host:$port..."
        
        if timeout 10 python3 -c "
import meshtastic
import meshtastic.tcp_interface
try:
    interface = meshtastic.tcp_interface.TCPInterface('$host', $port)
    print('SUCCESS: Connected to Meshtastic')
    # Try to get channels
    if hasattr(interface, 'localNode') and hasattr(interface.localNode, 'channels'):
        channels = interface.localNode.channels
        print(f'Found {len(channels)} channels')
        for idx, channel in enumerate(channels):
            if hasattr(channel, 'settings') and hasattr(channel.settings, 'name'):
                print(f'Channel {idx}: {channel.settings.name}')
    else:
        print('No channels found or localNode not available yet')
    exit(0)
except Exception as e:
    print(f'ERROR: {str(e)}')
    exit(1)
" 2>/dev/null; then
            print_success "Successfully connected to Meshtastic device!"
            connected=true
            break
        else
            print_warning "Connection attempt $attempt failed. Waiting before retry..."
            sleep $(( 2 ** attempt ))  # Exponential backoff
            (( attempt++ ))
        fi
    done
    
    if [ "$connected" = true ]; then
        return 0
    else
        return 1
    fi
}

# Function to extract value from Python config file
extract_config_value() {
    local config_file=$1
    local key=$2
    local default=$3
    
    if [ -f "$config_file" ]; then
        # Extract value using grep and sed, handling different formats
        # For string values (with quotes)
        value=$(grep -E "^$key\s*=\s*[\"']" "$config_file" | sed -E "s/^$key\s*=\s*[\"']([^\"']*)[\"'].*/\1/")
        
        # If empty, try for numeric or boolean values (without quotes)
        if [ -z "$value" ]; then
            value=$(grep -E "^$key\s*=\s*[^\"']" "$config_file" | sed -E "s/^$key\s*=\s*([^#]*).*/\1/" | tr -d '[:space:]')
        fi
        
        # Return the value if found, otherwise the default
        if [ -n "$value" ]; then
            echo "$value"
        else
            echo "$default"
        fi
    else
        # Config file doesn't exist, return default
        echo "$default"
    fi
}

# Welcome message
clear
print_header "Meshtastic LLM Agent Setup"
print_info "This script will help you set up the Meshtastic LLM Agent with all required components."
print_info "It will install and configure Mosquitto MQTT broker, setup Python dependencies,"
print_info "and guide you through configuring your Meshtastic device."
echo ""
read -p "Press Enter to continue..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_warning "This script requires elevated privileges to install system packages."
    print_info "We'll use sudo for the installation steps. You may be prompted for your password."
fi

# Get system information
print_header "System Information"
if command_exists lsb_release; then
    OS=$(lsb_release -d | cut -f2)
    print_info "Operating System: $OS"
elif [ -f /etc/os-release ]; then
    OS=$(grep PRETTY_NAME /etc/os-release | sed 's/PRETTY_NAME=//g' | tr -d '="')
    print_info "Operating System: $OS"
else
    OS="Unknown"
    print_warning "Unable to determine operating system"
fi

ARCH=$(uname -m)
print_info "Architecture: $ARCH"

IP_ADDRESS=$(hostname -I | awk '{print $1}')
print_info "IP Address: $IP_ADDRESS"

# Check and install required packages
print_header "Dependencies Check"

# Python check
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version)
    print_success "Python installed: $PYTHON_VERSION"
else
    print_error "Python 3 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
    if command_exists python3; then
        print_success "Python installed successfully!"
    else
        print_error "Failed to install Python. Please install Python 3 manually and run this script again."
        exit 1
    fi
fi

# Pip check
if command_exists pip3; then
    PIP_VERSION=$(pip3 --version)
    print_success "Pip installed: $PIP_VERSION"
else
    print_error "Pip not found. Installing..."
    sudo apt-get install -y python3-pip
    if command_exists pip3; then
        print_success "Pip installed successfully!"
    else
        print_error "Failed to install Pip. Please install Python3-pip manually and run this script again."
        exit 1
    fi
fi

# Mosquitto check and install
if command_exists mosquitto; then
    MOSQUITTO_VERSION=$(mosquitto -h | grep -o "mosquitto version [0-9.]*" | head -1)
    print_success "Mosquitto installed: $MOSQUITTO_VERSION"
else
    print_info "Mosquitto not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y mosquitto mosquitto-clients
    if command_exists mosquitto; then
        print_success "Mosquitto installed successfully!"
        sudo systemctl enable mosquitto
        sudo systemctl start mosquitto
    else
        print_error "Failed to install Mosquitto. Please install it manually and run this script again."
        exit 1
    fi
fi

# MQTT Configuration
print_header "MQTT Broker Configuration"

# Define configuration files
MQTT_CONFIG_FILE="/etc/mosquitto/mosquitto.conf"
MQTT_CONFIG_DIR="/etc/mosquitto/conf.d"
MESHTASTIC_CONFIG="${MQTT_CONFIG_DIR}/meshtastic.conf"
PASSWD_FILE="/etc/mosquitto/passwd"

# Check if we already have MQTT configured in either file
print_info "Checking existing MQTT configuration..."

# Check if config directory inclusion exists
NEEDS_CONFDIR=true
if setting_exists "$MQTT_CONFIG_FILE" "include_dir ${MQTT_CONFIG_DIR}"; then
    NEEDS_CONFDIR=false
    print_success "Include directive for conf.d already exists in main config."
else
    print_info "Need to add include directive for conf.d to main config."
fi

# Get MQTT broker and port
if command_exists ip; then
    MQTT_BROKER=$(ip route get 1 | awk '{print $7;exit}')
else
    MQTT_BROKER="localhost"
fi
print_info "Using MQTT broker address: $MQTT_BROKER"

MQTT_PORT=1883
print_info "Using MQTT port: $MQTT_PORT"

# Check if listener configurations exist
NEEDS_LISTENER=true
if setting_exists "$MQTT_CONFIG_FILE" "listener ${MQTT_PORT}" || setting_exists "$MESHTASTIC_CONFIG" "listener ${MQTT_PORT}"; then
    NEEDS_LISTENER=false
    print_success "MQTT listener on port ${MQTT_PORT} already configured."
else
    print_info "Need to add MQTT listener configuration."
fi

# Check if websocket listener exists
NEEDS_WEBSOCKET=true
if setting_exists "$MQTT_CONFIG_FILE" "listener 9001" || setting_exists "$MESHTASTIC_CONFIG" "listener 9001"; then
    NEEDS_WEBSOCKET=false
    print_success "WebSocket listener already configured."
else
    print_info "Need to add WebSocket listener configuration."
fi

# Default credentials
MQTT_USERNAME="meshtastic"
MQTT_PASSWORD="meshtastic"

# Check authentication configuration
NEEDS_AUTH=true
AUTH_EXISTS=false
if setting_exists "$MQTT_CONFIG_FILE" "allow_anonymous" || setting_exists "$MESHTASTIC_CONFIG" "allow_anonymous"; then
    AUTH_EXISTS=true
fi

if setting_exists "$MQTT_CONFIG_FILE" "password_file" || setting_exists "$MESHTASTIC_CONFIG" "password_file"; then
    AUTH_EXISTS=true
fi

if [ "$AUTH_EXISTS" = true ]; then
    NEEDS_AUTH=false
    print_success "Authentication already configured."
else
    print_info "Need to configure authentication."
fi

# Ask for MQTT credentials
ask_user "Enter MQTT username (default: $MQTT_USERNAME):"
read -r NEW_MQTT_USERNAME
MQTT_USERNAME=${NEW_MQTT_USERNAME:-$MQTT_USERNAME}

ask_user "Enter MQTT password (default: $MQTT_PASSWORD):"
read -r NEW_MQTT_PASSWORD
MQTT_PASSWORD=${NEW_MQTT_PASSWORD:-$MQTT_PASSWORD}

# Configure MQTT
if [ "$NEEDS_CONFDIR" = true ] || [ "$NEEDS_LISTENER" = true ] || [ "$NEEDS_AUTH" = true ] || [ "$NEEDS_WEBSOCKET" = true ]; then
    print_info "Configuring MQTT broker..."
    
    # Create conf.d directory if it doesn't exist
    if [ ! -d "$MQTT_CONFIG_DIR" ]; then
        print_info "Creating configuration directory ${MQTT_CONFIG_DIR}..."
        sudo mkdir -p "$MQTT_CONFIG_DIR"
    fi
    
    # Update main config file if needed
    if [ "$NEEDS_CONFDIR" = true ]; then
        print_info "Updating main configuration with include directive..."
        
        # Backup existing config if it exists
        if [ -f "$MQTT_CONFIG_FILE" ]; then
            sudo cp "$MQTT_CONFIG_FILE" "${MQTT_CONFIG_FILE}.backup"
        fi
        
        # Check if the file exists and has content
        if [ ! -f "$MQTT_CONFIG_FILE" ] || [ ! -s "$MQTT_CONFIG_FILE" ]; then
            # Create a new config with basic settings
            sudo bash -c "cat > $MQTT_CONFIG_FILE << EOF
# Mosquitto Configuration for Meshtastic
# Created by setup.sh

# Basic configuration
pid_file /run/mosquitto/mosquitto.pid
persistence true
persistence_location /var/lib/mosquitto/
log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information

# Include conf.d directory
include_dir ${MQTT_CONFIG_DIR}
EOF"
        else
            # Append include directive to existing file
            sudo bash -c "echo -e \"\n# Include conf.d directory\ninclude_dir ${MQTT_CONFIG_DIR}\" >> $MQTT_CONFIG_FILE"
        fi
        
        print_success "Updated main configuration file"
    fi
    
    # Create a temporary file for the config
    TEMP_CONFIG=$(mktemp)
    
    # Add header to the temp config
    cat > "$TEMP_CONFIG" << EOF
# Meshtastic-specific MQTT configuration
# Created/updated by setup.sh on $(date)
EOF
    
    # Add listener configuration if needed
    if [ "$NEEDS_LISTENER" = true ]; then
        cat >> "$TEMP_CONFIG" << EOF

# MQTT listener configuration
listener ${MQTT_PORT}
socket_domain ipv4
per_listener_settings true
protocol mqtt
EOF
        print_info "Added MQTT listener configuration"
    fi
    
    # Add authentication configuration if needed
    if [ "$NEEDS_AUTH" = true ]; then
        cat >> "$TEMP_CONFIG" << EOF

# Authentication configuration
allow_anonymous false
password_file ${PASSWD_FILE}
EOF
        print_info "Added authentication configuration"
    fi
    
    # Add WebSocket configuration if needed
    if [ "$NEEDS_WEBSOCKET" = true ]; then
        cat >> "$TEMP_CONFIG" << EOF

# WebSocket configuration
listener 9001
protocol websockets
allow_anonymous false
password_file ${PASSWD_FILE}
EOF
        print_info "Added WebSocket configuration"
    fi
    
    # Check if we need to update meshtastic.conf
    if [ -f "$MESHTASTIC_CONFIG" ]; then
        # Merge with existing file
        sudo bash -c "cat $TEMP_CONFIG >> $MESHTASTIC_CONFIG"
        print_success "Updated Meshtastic configuration"
    else
        # Create new file
        sudo bash -c "cat $TEMP_CONFIG > $MESHTASTIC_CONFIG"
        print_success "Created Meshtastic configuration"
    fi
    
    # Remove temp file
    rm "$TEMP_CONFIG"
    
    # Create password file if auth required
    if [ "$NEEDS_AUTH" = true ]; then
        print_info "Setting up authentication..."
        sudo touch "$PASSWD_FILE"
        sudo mosquitto_passwd -b "$PASSWD_FILE" "$MQTT_USERNAME" "$MQTT_PASSWORD"
        sudo chmod 600 "$PASSWD_FILE"
        print_success "Created password file with username: $MQTT_USERNAME"
    fi
    
    # Restart Mosquitto
    print_info "Restarting Mosquitto service..."
    sudo systemctl restart mosquitto
    sudo systemctl enable mosquitto
    
    # Check if service is running
    if sudo systemctl is-active --quiet mosquitto; then
        print_success "Mosquitto MQTT broker is running!"
    else
        print_error "Failed to start Mosquitto service."
        print_error "Check the service status with: sudo systemctl status mosquitto"
        exit 1
    fi
else
    print_success "MQTT already configured, no changes needed."
fi

# Virtual Environment Setup
print_header "Virtual Environment Setup"
if [ -d "venv" ]; then
    print_success "Virtual environment already exists."
    print_info "Activating existing virtual environment..."
    source venv/bin/activate
else
    print_info "Creating virtual environment..."
    python3 -m venv venv
    if [ -d "venv" ]; then
        print_success "Virtual environment created successfully."
        print_info "Activating virtual environment..."
        source venv/bin/activate
    else
        print_error "Failed to create virtual environment. Using system Python."
    fi
fi

# Install Python requirements
print_header "Installing Python Dependencies"
print_info "Installing required Python packages..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    # If requirements.txt doesn't exist, install packages directly
    print_warning "requirements.txt not found. Installing packages directly..."
    pip3 install meshtastic paho-mqtt requests tqdm torch transformers llama-cpp-python
fi

print_success "Python packages installed successfully!"

# Meshtastic device configuration
print_header "Meshtastic Device Configuration"
print_info "Now we need to configure your Meshtastic device."
print_info "You'll need to access the Meshtastic web interface on your device."

# Ask for Meshtastic device details
ask_user "Enter Meshtastic device IP address (default: 10.0.0.133):"
read -r NEW_MESHTASTIC_IP
MESHTASTIC_IP=${NEW_MESHTASTIC_IP:-10.0.0.133}

ask_user "Enter Meshtastic TCP port (default: 4403):"
read -r NEW_MESHTASTIC_PORT
MESHTASTIC_PORT=${NEW_MESHTASTIC_PORT:-4403}

# Verify connection to Meshtastic device
print_info "Checking connection to Meshtastic device at $MESHTASTIC_IP:$MESHTASTIC_PORT..."

if ! command_exists meshtastic; then
    print_warning "Meshtastic CLI not found. Installing..."
    pip3 install meshtastic
    if ! command_exists meshtastic; then
        print_error "Failed to install Meshtastic CLI. Continuing without CLI verification."
    fi
fi

# Try to connect to Meshtastic
if ! try_meshtastic_connection "$MESHTASTIC_IP" "$MESHTASTIC_PORT" 4; then
    print_warning "Couldn't connect to Meshtastic device after multiple attempts."
    print_info "Please ensure your Meshtastic device is powered on and accessible at ${MESHTASTIC_IP}:${MESHTASTIC_PORT}"
    print_info "We'll continue with the setup, but you'll need to configure the device later."
fi

# Instructions for Meshtastic channel configuration
print_header "Meshtastic Channel Configuration"
print_info "Please configure your Meshtastic device with the following channels:"
echo
print_info "1. Open your Meshtastic device web interface at http://${MESHTASTIC_IP}"
print_info "2. Go to the 'Channels' tab"
print_info "3. Create a new channel with name 'llm' (or your preferred name)"
print_info "   - Set this channel as 'Uplink' in the channel settings"
print_info "4. Create another channel with name 'llmres' (or your preferred name)"
print_info "   - Set this channel as 'Downlink' in the channel settings"
echo
print_info "5. Then go to the 'MQTT' tab and configure:"
print_info "   - Server: ${IP_ADDRESS} (this computer's IP)"
print_info "   - Username: ${MQTT_USERNAME}"
print_info "   - Password: ${MQTT_PASSWORD}"
print_info "   - Enabled: Checked"
echo

# Ask user to confirm when configuration is done
ask_user "Have you completed the Meshtastic device configuration? (y/n)"
read -r CONFIRMATION
if [[ ! $CONFIRMATION =~ ^[Yy]$ ]]; then
    print_warning "Please complete the configuration before continuing."
    print_info "You can run this script again after configuring the device."
    exit 0
fi

# Update config.py
print_header "Updating Configuration"
print_info "Now we'll update the config.py file with your settings."

if [ -f "config.py" ]; then
    # Update existing config file
    print_info "Updating existing config.py..."
    # Create a backup
    cp "config.py" "config.py.bak"
    
    # Update model configuration
    sed -i "s|MODEL_ID = .*|MODEL_ID = \"TheBloke/Mistral-7B-Instruct-v0.2-GGUF\"|" "config.py"
    sed -i "s|MODEL_LOCAL_PATH = .*|MODEL_LOCAL_PATH = \"./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf\"|" "config.py"
    
    # Update Meshtastic configuration
    sed -i "s|MESHTASTIC_IP = .*|MESHTASTIC_IP = \"$MESHTASTIC_IP\"|" "config.py"
    sed -i "s|MESHTASTIC_PORT = .*|MESHTASTIC_PORT = $MESHTASTIC_PORT|" "config.py"
    
    # Update MQTT configuration
    sed -i "s|MQTT_BROKER = .*|MQTT_BROKER = \"$MQTT_BROKER\"|" "config.py"
    sed -i "s|MQTT_PORT = .*|MQTT_PORT = $MQTT_PORT|" "config.py"
    sed -i "s|MQTT_USERNAME = .*|MQTT_USERNAME = \"$MQTT_USERNAME\"|" "config.py"
    sed -i "s|MQTT_PASSWORD = .*|MQTT_PASSWORD = \"$MQTT_PASSWORD\"|" "config.py"
    sed -i "s|LLM_CHANNEL = .*|LLM_CHANNEL = \"msh/US/2/json/llm/\"|" "config.py"
    sed -i "s|LLM_RESPONSE_CHANNEL = .*|LLM_RESPONSE_CHANNEL = \"msh/US/2/json/llmres/\"|" "config.py"
    
    print_success "Updated config.py with your settings!"
else
    # Create new config file
    print_info "Creating new config.py..."
    cat > "config.py" << EOF
# Model configuration
MODEL_ID = "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
MODEL_LOCAL_PATH = "./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
USE_GGUF = True
MAX_NEW_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.9

# Meshtastic configuration
MESHTASTIC_IP = "$MESHTASTIC_IP"
MESHTASTIC_PORT = $MESHTASTIC_PORT
MESHTASTIC_HTTP_PORT = 8080
PRIVATE_MODE = False

# MQTT configuration
MQTT_BROKER = "$MQTT_BROKER"
MQTT_PORT = $MQTT_PORT
MQTT_USERNAME = "$MQTT_USERNAME"
MQTT_PASSWORD = "$MQTT_PASSWORD"
SEND_STARTUP_MESSAGE = True
USE_LLM_CHANNEL = True
LLM_CHANNEL = "msh/US/2/json/llm/"
LLM_RESPONSE_CHANNEL = "msh/US/2/json/llmres/"

# System prompt for the conversational agent
SYSTEM_PROMPT = """You are a helpful AI assistant connected via Meshtastic mesh network.
You can communicate with users over long distances even without internet connectivity.
Keep your responses concise as they need to be transmitted over a low-bandwidth network."""
EOF
    print_success "Created new config.py with your settings!"
fi

# Create a test script for LLM channel
print_header "Creating Test Script"
print_info "Creating a test script to help you verify LLM channel communication..."

cat > test_llm_channel.py << EOF
#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
import paho.mqtt.client as mqtt

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        # Subscribe to the response channel
        client.subscribe(f"{args.llm_response_channel}#")
    else:
        logger.error(f"Failed to connect to MQTT broker, return code: {rc}")

def on_message(client, userdata, msg):
    logger.info(f"Received message on topic: {msg.topic}")
    try:
        payload = json.loads(msg.payload.decode())
        logger.info(f"Response: {payload}")
    except json.JSONDecodeError:
        logger.info(f"Raw response: {msg.payload.decode()}")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")

def main():
    global args
    parser = argparse.ArgumentParser(description="Test LLM channel communication")
    parser.add_argument("--mqtt-host", type=str, default="$MQTT_BROKER", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=$MQTT_PORT, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, default="$MQTT_USERNAME", help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, default="$MQTT_PASSWORD", help="MQTT password")
    parser.add_argument("--llm-channel", type=str, default="msh/US/2/json/llm/", help="LLM channel topic")
    parser.add_argument("--llm-response-channel", type=str, default="msh/US/2/json/llmres/", help="LLM response channel topic")
    parser.add_argument("--message", type=str, default="Hello from test script!", help="Message to send")
    args = parser.parse_args()
    
    # Create MQTT client
    client = mqtt.Client()
    client.username_pw_set(args.mqtt_username, args.mqtt_password)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        # Connect to MQTT broker
        logger.info(f"Connecting to MQTT broker at {args.mqtt_host}:{args.mqtt_port}")
        client.connect(args.mqtt_host, args.mqtt_port, 60)
        
        # Start the loop
        client.loop_start()
        
        # Wait for connection
        time.sleep(1)
        
        # Prepare message
        message = {
            "from": "test_script",
            "to": "llm",
            "id": f"test_{int(datetime.now().timestamp())}",
            "time": int(datetime.now().timestamp()),
            "text": args.message
        }
        
        # Send message
        topic = args.llm_channel
        payload = json.dumps(message)
        logger.info(f"Sending message to topic: {topic}")
        logger.info(f"Payload: {payload}")
        result = client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Message sent successfully")
        else:
            logger.error(f"Failed to send message: {result}")
        
        # Wait for response
        logger.info("Waiting for response (press Ctrl+C to exit)...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Test terminated by user")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
EOF

chmod +x test_llm_channel.py
print_success "Created test_llm_channel.py!"
print_info "You can use this script to test your LLM channel by running:"
print_info "python test_llm_channel.py --message 'Your test message here'"

# Verifying MQTT connection
print_header "Verifying Setup"
print_info "Testing MQTT connection to $MQTT_BROKER:$MQTT_PORT..."

# Install mosquitto-clients if needed
if ! command_exists mosquitto_pub; then
    print_warning "mosquitto_pub not found. Installing mosquitto-clients..."
    sudo apt-get install -y mosquitto-clients
fi

# Test MQTT connection
if mosquitto_pub -h "$MQTT_BROKER" -p "$MQTT_PORT" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" -t "test/topic" -m "Hello Meshtastic!" -q 1; then
    print_success "MQTT connection successful!"
else
    print_error "MQTT connection failed! Please check your Mosquitto configuration."
    print_info "Make sure Mosquitto is running: sudo systemctl status mosquitto"
    print_info "Check credentials and try again."
fi

# Test Meshtastic connection again
print_info "Testing Meshtastic connection to $MESHTASTIC_IP:$MESHTASTIC_PORT..."
if try_meshtastic_connection "$MESHTASTIC_IP" "$MESHTASTIC_PORT" 4; then
    print_success "Meshtastic connection successful!"
else
    print_warning "Meshtastic connection failed! Please check your device configuration."
    print_info "You may need to restart your Meshtastic device after configuring MQTT."
fi

# Final instructions
print_header "Setup Complete!"
print_info "The Meshtastic LLM Agent is now configured and ready to use!"
print_info "To start the agent, run: ./start.sh $MQTT_BROKER $MQTT_PORT $MESHTASTIC_IP $MESHTASTIC_PORT"
print_info "Or simply use: ./start.sh (which will use values from config.py)"

# Print configuration summary
print_header "Configuration Summary"
echo -e "${CYAN}Model:${NC} TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
echo -e "${CYAN}Model Path:${NC} ./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
echo -e "${CYAN}Meshtastic Device:${NC} $MESHTASTIC_IP:$MESHTASTIC_PORT"
echo -e "${CYAN}MQTT Broker:${NC} $MQTT_BROKER:$MQTT_PORT"
echo -e "${CYAN}MQTT Credentials:${NC} $MQTT_USERNAME:$MQTT_PASSWORD"
echo -e "${CYAN}LLM Channel:${NC} msh/US/2/json/llm/"
echo -e "${CYAN}LLM Response Channel:${NC} msh/US/2/json/llmres/"
echo

print_info "Important notes:"
print_info "1. Make sure your Meshtastic device is accessible at ${MESHTASTIC_IP}:${MESHTASTIC_PORT}"
print_info "2. The MQTT broker is running on ${MQTT_BROKER}:${MQTT_PORT} with username '${MQTT_USERNAME}'"
print_info "3. If you restart your computer, the MQTT broker will restart automatically"
print_info "4. If you change networks, you may need to update the IP addresses in config.py"
print_info "5. For channel issues, check your Meshtastic device configuration"
print_info "6. The config.py file contains all your settings and can be edited manually"
echo

# Troubleshooting tips
print_header "Troubleshooting Tips"
print_info "If you encounter issues:"
print_info "1. Check MQTT broker status: sudo systemctl status mosquitto"
print_info "2. Verify Meshtastic device is reachable: ping $MESHTASTIC_IP"
print_info "3. Ensure the LLM channels exist in the Meshtastic device web interface"
print_info "4. Check the connection logs in lora_llm.log"
print_info "5. Try restarting both the MQTT broker and the Meshtastic device"
print_info "6. For more help, see the MQTT_TROUBLESHOOTING.md file"
echo

print_success "Enjoy your Meshtastic LLM Agent! 🚀"

# Deactivate virtual environment
deactivate
