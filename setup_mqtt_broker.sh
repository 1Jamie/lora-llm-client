#!/bin/bash

# MQTT Broker Setup Script for Meshtastic
# This script installs and configures the Mosquitto MQTT broker for use with Meshtastic devices

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "\n${CYAN}===== $1 =====${NC}"
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

# Check if script is run with sudo
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Get local IP address
IP_ADDRESS=$(hostname -I | awk '{print $1}')
if [ -z "$IP_ADDRESS" ]; then
    print_warning "Could not determine local IP address automatically."
    read -p "Please enter your local IP address: " IP_ADDRESS
fi

# Parse command line arguments
MQTT_PORT=1883
MQTT_USERNAME="meshtastic"
MQTT_PASSWORD="meshtastic"
ALLOW_ANONYMOUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            MQTT_PORT="$2"
            shift 2
            ;;
        --username)
            MQTT_USERNAME="$2"
            shift 2
            ;;
        --password)
            MQTT_PASSWORD="$2"
            shift 2
            ;;
        --allow-anonymous)
            ALLOW_ANONYMOUS=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Usage: sudo $0 [--port PORT] [--username USERNAME] [--password PASSWORD] [--allow-anonymous]"
            exit 1
            ;;
    esac
done

print_header "Meshtastic MQTT Broker Setup"
print_info "This script will install and configure Mosquitto MQTT broker for Meshtastic"
print_info "IP Address: $IP_ADDRESS"
print_info "MQTT Port: $MQTT_PORT"
print_info "MQTT Username: $MQTT_USERNAME"
if [ "$ALLOW_ANONYMOUS" = true ]; then
    print_info "Anonymous connections: Allowed"
else
    print_info "Anonymous connections: Disallowed (using password authentication)"
fi
echo

# Confirm installation
read -p "Continue with installation? [y/N]: " -n 1 -r CONFIRM
echo
if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    print_info "Installation cancelled."
    exit 0
fi

# Install Mosquitto
print_header "Installing Mosquitto MQTT Broker"
print_info "Updating package lists..."
apt-get update -qq

print_info "Installing Mosquitto MQTT broker and utilities..."
apt-get install -y mosquitto mosquitto-clients

# Check existing configuration
print_header "Checking Existing Configuration"
print_info "Analyzing current Mosquitto configuration..."

CONFIG_DIR="/etc/mosquitto/conf.d"
CONFIG_FILE="/etc/mosquitto/mosquitto.conf"
MESHTASTIC_CONFIG="${CONFIG_DIR}/meshtastic.conf"
PASSWD_FILE="/etc/mosquitto/passwd"

# Create conf.d directory if it doesn't exist
if [ ! -d "$CONFIG_DIR" ]; then
    print_info "Creating configuration directory ${CONFIG_DIR}..."
    mkdir -p "$CONFIG_DIR"
fi

# Check if base configurations exist
NEEDS_CONFDIR=true
if setting_exists "$CONFIG_FILE" "include_dir ${CONFIG_DIR}"; then
    NEEDS_CONFDIR=false
    print_info "Include directive for conf.d already exists in main config."
else
    print_info "Need to add include directive for conf.d to main config."
fi

# Check if listener configurations exist
NEEDS_LISTENER=true
if setting_exists "$CONFIG_FILE" "listener ${MQTT_PORT}" || setting_exists "$MESHTASTIC_CONFIG" "listener ${MQTT_PORT}"; then
    NEEDS_LISTENER=false
    print_info "MQTT listener on port ${MQTT_PORT} already configured."
else
    print_info "Need to add MQTT listener configuration."
fi

# Check if websocket listener exists
NEEDS_WEBSOCKET=true
if setting_exists "$CONFIG_FILE" "listener 9001" || setting_exists "$MESHTASTIC_CONFIG" "listener 9001"; then
    NEEDS_WEBSOCKET=false
    print_info "WebSocket listener already configured."
else
    print_info "Need to add WebSocket listener configuration."
fi

# Check authentication configuration
NEEDS_AUTH=true
if [ "$ALLOW_ANONYMOUS" = true ]; then
    if setting_exists "$CONFIG_FILE" "allow_anonymous true" || setting_exists "$MESHTASTIC_CONFIG" "allow_anonymous true"; then
        NEEDS_AUTH=false
        print_info "Anonymous access already configured."
    else
        print_info "Need to configure anonymous access."
    fi
else
    if (setting_exists "$CONFIG_FILE" "allow_anonymous false" && setting_exists "$CONFIG_FILE" "password_file") || \
       (setting_exists "$MESHTASTIC_CONFIG" "allow_anonymous false" && setting_exists "$MESHTASTIC_CONFIG" "password_file"); then
        NEEDS_AUTH=false
        print_info "Authentication already configured."
    else
        print_info "Need to configure authentication."
    fi
fi

# Backup existing files
if [ -f "$CONFIG_FILE" ]; then
    print_info "Backing up main configuration to ${CONFIG_FILE}.backup"
    cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"
fi

if [ -f "$MESHTASTIC_CONFIG" ]; then
    print_info "Backing up Meshtastic configuration to ${MESHTASTIC_CONFIG}.backup"
    cp "$MESHTASTIC_CONFIG" "${MESHTASTIC_CONFIG}.backup"
fi

# Update main config file if needed
if [ "$NEEDS_CONFDIR" = true ]; then
    print_info "Updating main configuration with include directive..."
    
    # Check if the file exists and has content
    if [ ! -f "$CONFIG_FILE" ] || [ ! -s "$CONFIG_FILE" ]; then
        # Create a new config with basic settings
        cat > "$CONFIG_FILE" << EOF
# Mosquitto Configuration for Meshtastic
# Created by setup_mqtt_broker.sh

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
include_dir ${CONFIG_DIR}
EOF
    else
        # Append include directive to existing file
        echo -e "\n# Include conf.d directory\ninclude_dir ${CONFIG_DIR}" >> "$CONFIG_FILE"
    fi
    
    print_success "Updated main configuration file"
fi

# Create or update meshtastic.conf
print_info "Preparing Meshtastic configuration file..."

# Create a temporary file to build the config
TEMP_CONFIG=$(mktemp)

# Add header to the temp config
cat > "$TEMP_CONFIG" << EOF
# Meshtastic-specific MQTT configuration
# Created/updated by setup_mqtt_broker.sh on $(date)
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
    if [ "$ALLOW_ANONYMOUS" = true ]; then
        cat >> "$TEMP_CONFIG" << EOF

# Authentication configuration
allow_anonymous true
EOF
    else
        cat >> "$TEMP_CONFIG" << EOF

# Authentication configuration
allow_anonymous false
password_file ${PASSWD_FILE}
EOF

        # Create password file
        print_info "Setting up authentication..."
        touch "$PASSWD_FILE"
        mosquitto_passwd -b "$PASSWD_FILE" "$MQTT_USERNAME" "$MQTT_PASSWORD"
        chmod 600 "$PASSWD_FILE"
        print_success "Created password file with username: $MQTT_USERNAME"
    fi
    
    print_info "Added authentication configuration"
fi

# Add WebSocket configuration if needed
if [ "$NEEDS_WEBSOCKET" = true ]; then
    cat >> "$TEMP_CONFIG" << EOF

# WebSocket configuration
listener 9001
protocol websockets
EOF

    # Add authentication for WebSocket if not anonymous
    if [ "$ALLOW_ANONYMOUS" = false ]; then
        cat >> "$TEMP_CONFIG" << EOF
allow_anonymous false
password_file ${PASSWD_FILE}
EOF
    fi
    
    print_info "Added WebSocket configuration"
fi

# Check if we added any configurations
if [ "$NEEDS_LISTENER" = true ] || [ "$NEEDS_AUTH" = true ] || [ "$NEEDS_WEBSOCKET" = true ]; then
    # Check if the meshtastic.conf file exists
    if [ -f "$MESHTASTIC_CONFIG" ]; then
        # Compare the temp config with what we want to add
        TEMP_MERGED=$(mktemp)
        cat "$MESHTASTIC_CONFIG" "$TEMP_CONFIG" > "$TEMP_MERGED"
        mv "$TEMP_MERGED" "$MESHTASTIC_CONFIG"
    else
        # Just use our new config
        mv "$TEMP_CONFIG" "$MESHTASTIC_CONFIG"
    fi
    
    print_success "Updated Meshtastic configuration"
else
    print_info "No configuration changes needed for Meshtastic"
    rm "$TEMP_CONFIG"
fi

# Create check_mqtt_broker.py script
print_header "Creating Test Script"
print_info "Creating a script to check MQTT broker functionality..."

cat > "check_mqtt_broker.py" << EOF
#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import time
import sys
import argparse

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT broker successfully!")
        print(f"Testing message publishing...")
        client.publish("test/connection", "MQTT Broker is working!", qos=1)
        
        print(f"Subscribing to Meshtastic topics...")
        client.subscribe("msh/#")
    else:
        print(f"Failed to connect to MQTT broker with result code {rc}")
        if rc == 1:
            print("Connection refused - incorrect protocol version")
        elif rc == 2:
            print("Connection refused - invalid client identifier")
        elif rc == 3:
            print("Connection refused - server unavailable")
        elif rc == 4:
            print("Connection refused - bad username or password")
        elif rc == 5:
            print("Connection refused - not authorized")
        
def on_message(client, userdata, msg):
    print(f"Received message on topic: {msg.topic}")
    print(f"Message: {msg.payload.decode()}")
    
def on_publish(client, userdata, mid):
    print(f"Message published successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test MQTT broker connection")
    parser.add_argument("--host", default="$IP_ADDRESS", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=$MQTT_PORT, help="MQTT broker port")
    parser.add_argument("--username", default="$MQTT_USERNAME", help="MQTT username")
    parser.add_argument("--password", default="$MQTT_PASSWORD", help="MQTT password")
    parser.add_argument("--duration", type=int, default=10, help="How many seconds to listen for messages")
    args = parser.parse_args()
    
    print(f"Testing connection to MQTT broker at {args.host}:{args.port}")
    
    client = mqtt.Client()
    
    # Set up callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish
    
    # Set username and password if provided
    if args.username and args.password:
        print(f"Using authentication with username: {args.username}")
        client.username_pw_set(args.username, args.password)
    
    try:
        client.connect(args.host, args.port, 60)
        client.loop_start()
        
        print(f"Listening for messages for {args.duration} seconds...")
        time.sleep(args.duration)
        
        print("Test completed!")
        print("If you didn't see any 'Received message' lines, there were no messages on the network.")
        print("This is normal if no Meshtastic devices are actively sending messages.")
        
    except KeyboardInterrupt:
        print("Test interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()
EOF

chmod +x check_mqtt_broker.py
print_success "Created check_mqtt_broker.py"

# Configure firewall
print_header "Configuring Firewall"
if command -v ufw > /dev/null 2>&1; then
    print_info "Configuring UFW firewall..."
    ufw allow $MQTT_PORT/tcp comment "Mosquitto MQTT"
    ufw allow 9001/tcp comment "Mosquitto WebSockets"
    print_success "Firewall rules added for ports $MQTT_PORT and 9001"
else
    print_warning "UFW not installed. Skipping firewall configuration."
    print_warning "Please manually ensure that ports $MQTT_PORT and 9001 are open in your firewall."
fi

# Restart Mosquitto
print_header "Starting Mosquitto Service"
print_info "Restarting Mosquitto service..."
systemctl restart mosquitto
systemctl enable mosquitto

# Check if service is running
if systemctl is-active --quiet mosquitto; then
    print_success "Mosquitto MQTT broker is running!"
else
    print_error "Failed to start Mosquitto service."
    print_error "Check the service status with: systemctl status mosquitto"
    exit 1
fi

# Final instructions
print_header "Setup Complete!"
print_success "Mosquitto MQTT broker has been installed and configured for Meshtastic!"
echo
print_info "MQTT Broker Details:"
echo -e "  ${CYAN}Host:${NC} $IP_ADDRESS"
echo -e "  ${CYAN}Port:${NC} $MQTT_PORT"
if [ "$ALLOW_ANONYMOUS" = false ]; then
    echo -e "  ${CYAN}Username:${NC} $MQTT_USERNAME"
    echo -e "  ${CYAN}Password:${NC} $MQTT_PASSWORD"
fi
echo
print_info "To test the MQTT broker:"
echo -e "  ${CYAN}./check_mqtt_broker.py${NC}"
echo
print_info "To subscribe to all Meshtastic messages:"
if [ "$ALLOW_ANONYMOUS" = false ]; then
    echo -e "  ${CYAN}mosquitto_sub -h $IP_ADDRESS -p $MQTT_PORT -u $MQTT_USERNAME -P $MQTT_PASSWORD -t \"msh/#\" -v${NC}"
else
    echo -e "  ${CYAN}mosquitto_sub -h $IP_ADDRESS -p $MQTT_PORT -t \"msh/#\" -v${NC}"
fi
echo
print_info "To configure your Meshtastic devices to use this MQTT broker:"
echo -e "  ${CYAN}./configure_meshtastic_mqtt.py --device /dev/ttyUSB0 --mqtt-server $IP_ADDRESS --mqtt-port $MQTT_PORT${NC}"
if [ "$ALLOW_ANONYMOUS" = false ]; then
    echo -e "  Add ${CYAN}--mqtt-username $MQTT_USERNAME --mqtt-password $MQTT_PASSWORD${NC} for authentication"
fi
echo
print_info "Next steps:"
echo -e "  1. Configure your Meshtastic devices to use this MQTT broker"
echo -e "  2. Test the MQTT broker with check_mqtt_broker.py"
echo -e "  3. Run the Meshtastic LLM Agent"
echo
print_success "MQTT setup complete! 🚀"
