# LLM Meshtastic Agent

This project runs a DeepSeek-R1-Distill-Qwen-1.5B LLM model as a conversational agent over a Meshtastic network using a hybrid approach for messaging.

## Features

- Loads the DeepSeek-R1-Distill-Qwen-1.5B model from Huggingface
- Automatically selects between transformers (for safetensors) or llama-cpp-python (for GGUF)
- Hybrid messaging:
  - Receives messages via MQTT for reliable subscription
  - Sends responses via Meshtastic TCP API for reliable delivery
- Processes incoming messages and sends AI responses back through the Meshtastic network
- Supports both broadcast and private messaging modes
- Handles direct messaging to specific nodes
- Configurable startup notification message
- Dedicated LLM channel for specialized processing
- Automatic TCP reconnection with exponential backoff
- Fallback to MQTT when TCP connection fails
- Support for Mistral-7B-Instruct-v0.2-GGUF model

## Setup

The easiest way to set up the entire system is by using our automated setup script:

```bash
./setup.sh
```

This script will:
- Install and configure the Mosquitto MQTT broker
- Set up your Meshtastic device configuration
- Configure the LLM agent with your preferred settings
- Create all necessary configuration files
- Install required dependencies
- Download the LLM model (if needed)

For manual setup, follow these steps:

### 1. Set up MQTT Broker

The Meshtastic network requires an MQTT broker (server) to handle message routing. We provide a setup script for Mosquitto MQTT broker:

```bash
sudo ./setup_mqtt_broker.sh
```

This will:
- Install Mosquitto MQTT broker
- Configure it for Meshtastic use
- Start and enable the service
- Open the necessary firewall ports

To verify the MQTT broker is working correctly:

```bash
./check_mqtt_broker.py
```

If you encounter issues, see the [MQTT Troubleshooting Guide](MQTT_TROUBLESHOOTING.md).

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Meshtastic Devices

Your Meshtastic devices need to be configured to use MQTT. You can use our configuration script:

```bash
# For a device connected via USB:
./configure_meshtastic_mqtt.py --device /dev/ttyUSB0 --mqtt-server 192.168.1.100

# For a device connected via network:
./configure_meshtastic_mqtt.py --host 192.168.1.200 --mqtt-server 192.168.1.100
```

Or manually configure using the Meshtastic mobile app or CLI:

1. Set the MQTT server address to your computer's IP address
2. Set the MQTT port to 1883 (default)
3. If you configured authentication, set the username and password

### 4. Test MQTT Messaging

Before running the agent, you can test if messages are flowing correctly through the MQTT broker:

```bash
# Send a broadcast message and listen for 30 seconds
./test_mqtt_message.py --message "Hello Meshtastic"

# Send a message to a specific node
./test_mqtt_message.py --node !abcd1234 --message "Hello specific node"

# Just listen for messages without sending
./test_mqtt_message.py --listen-only --duration 60
```

### 5. Test Direct Messaging

To specifically test if direct messaging is working correctly:

```bash
# Test direct messaging with the agent
./test_direct_messaging.py

# If you know the agent's node ID
./test_direct_messaging.py --agent-id !abcd1234
```

This will:
- Connect to the MQTT broker
- Discover all nodes on the network
- Identify the agent node (or use the provided ID)
- Send a direct message to the agent
- Wait for a response
- Verify the direct messaging is working correctly

### 6. Simulate a Meshtastic Node

For testing without physical Meshtastic devices, you can use the simulation script:

```bash
# Start a simulated node with interactive mode
./simulate_meshtastic_node.py

# Specify a custom node ID
./simulate_meshtastic_node.py --node-id !mynode1234

# Auto-respond to direct messages
./simulate_meshtastic_node.py --auto-respond

# Send a direct message to the agent at startup
./simulate_meshtastic_node.py --agent-id !agent1234 --message "Hello agent"

# Send a broadcast message at startup
./simulate_meshtastic_node.py --message "Hello network" --broadcast
```

In interactive mode, you can:
- Send broadcast messages with `b <message>`
- Send direct messages with `d <node_id> <message>`
- View node info with `i`
- Quit with `q`

This is useful for:
- Testing the agent without physical devices
- Debugging MQTT communication
- Simulating multiple nodes for testing
- Verifying direct messaging functionality

### 7. Run the Agent

```bash
python main.py --mqtt-host <MQTT_HOST> --mqtt-port <MQTT_PORT> --tcp-host <TCP_HOST> --tcp-port <TCP_PORT>
```

Or use the start script with the hybrid messaging parameters:
```bash
./start.sh [mqtt_host] [mqtt_port] [tcp_host] [tcp_port] [mode] [startup_message] [llm_channel]
```

Where:
- `mqtt_host` is your MQTT broker's IP address (default: 10.0.0.159)
- `mqtt_port` is your MQTT broker's port (default: 1883)
- `tcp_host` is your Meshtastic device's IP address for TCP API (default: 10.0.0.213)
- `tcp_port` is your Meshtastic device's TCP port (default: 4403)
- `mode` can be "private" (default) or "broadcast"
- `startup_message` can be "yes", "no", or "default" (uses config.py setting)
- `llm_channel` can be "yes", "no", or "default" (uses config.py setting)

### 8. Testing Hybrid Messaging

The system now uses a hybrid approach where it:
- Receives messages via MQTT
- Sends responses via the Meshtastic TCP API

This resolves reliability issues with MQTT message delivery while maintaining the benefits of MQTT for subscription and listening.

To test the hybrid messaging feature:

```bash
python test_hybrid_messaging.py --mqtt-host 10.0.0.159 --mqtt-port 1883 --tcp-host 10.0.0.213 --tcp-port 4403
```

Additional options:
```bash
# Test with LLM channel enabled
python test_hybrid_messaging.py --use-llm-channel

# Only respond to direct messages
python test_hybrid_messaging.py --private

# Test for a specific duration
python test_hybrid_messaging.py --test-duration 120
```

For more detailed information on the hybrid messaging approach, see the [Hybrid Messaging Documentation](docs/hybrid_messaging.md).

## Testing

We provide several testing tools to verify your setup and diagnose issues:

### Testing MQTT Broker

To check if your MQTT broker is working correctly:

```bash
./check_mqtt_broker.py
```

If you have issues with MQTT, refer to the [MQTT Troubleshooting Guide](MQTT_TROUBLESHOOTING.md).

### Testing TCP Connectivity

To verify your TCP connection to the Meshtastic device is working properly:

```bash
./test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT
```

For more advanced testing, including reconnection testing:

```bash
./test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT --test-reconnection
```

If you encounter TCP connection issues, refer to the [TCP Troubleshooting Guide](TCP_TROUBLESHOOTING.md).

### Testing LLM Channel Communication

To test the dedicated LLM channel:

```bash
./test_llm_channel.py --message "Test message for LLM processing"
```

For more details on channel configuration, see the [Channel Configuration Guide](CHANNEL_CONFIGURATION.md).

### Testing Direct Message Sending

To test sending messages directly through the Meshtastic mesh network:

```bash
./test_send_message.py --mode direct --node-id YOUR_NODE_ID --message "Direct test message"
```

For broadcast messages:

```bash
./test_send_message.py --mode broadcast --message "Broadcast test message"
```

### Comprehensive Testing

For a full suite of tests covering all aspects of the system:

```bash
# Start the agent in one terminal
./start.sh

# In another terminal, run tests
python -m pytest tests/
```

For detailed testing instructions, see the [Testing Guide](TESTING.md).

## Configuration

The system is highly configurable through the `config.py` file. Key configuration options include:

- **Model settings**: Choose between different models and adjust parameters
- **MQTT settings**: Configure broker connections and authentication
- **TCP settings**: Set up TCP connection parameters and retry behavior
- **LLM channel settings**: Configure dedicated channels for AI communication
- **Message handling**: Control broadcast vs. private messaging behavior

For detailed channel configuration instructions, see the [Channel Configuration Guide](CHANNEL_CONFIGURATION.md).

## Troubleshooting

If you encounter issues, we provide several troubleshooting guides:

- [MQTT Troubleshooting Guide](MQTT_TROUBLESHOOTING.md) - For issues with MQTT connectivity
- [TCP Troubleshooting Guide](TCP_TROUBLESHOOTING.md) - For TCP connection problems
- [Testing Guide](TESTING.md) - For comprehensive testing procedures
- [Channel Configuration Guide](CHANNEL_CONFIGURATION.md) - For LLM channel setup and issues

## Advanced Usage

### Custom Models

The system supports various GGUF models. To use a different model:

1. Edit `config.py` to update the model path and ID
2. Run `download_model.py` to fetch the new model
3. Restart the agent

### Custom Channels

You can create custom LLM channels for different purposes:

1. Configure the channels in your Meshtastic device
2. Update `config.py` with the channel names
3. Restart the agent

For detailed instructions, see the [Channel Configuration Guide](CHANNEL_CONFIGURATION.md).

### Multiple Interfaces

For advanced setups with multiple Meshtastic devices:

1. Configure each device with unique channel names
2. Update `config.py` to include all channel mappings
3. Use the appropriate channel name when sending messages

## Command Line Options

```
usage: main.py [-h] [--model MODEL] [--mqtt-host MQTT_HOST]
               [--mqtt-port MQTT_PORT] [--mqtt-username MQTT_USERNAME]
               [--mqtt-password MQTT_PASSWORD] [--private] [--broadcast]
               [--startup-message] [--no-startup-message] [--gguf] [--cpu-only]
               [--use-llm-channel] [--no-llm-channel] [--llm-channel LLM_CHANNEL]
               [--llm-response-channel LLM_RESPONSE_CHANNEL]

LLM Meshtastic Agent

options:
  -h, --help            show this help message and exit
  --model MODEL         Model ID or path
  --mqtt-host MQTT_HOST
                        MQTT broker host
  --mqtt-port MQTT_PORT
                        MQTT broker port (default: 1883)
  --mqtt-username MQTT_USERNAME
                        MQTT username for authentication
  --mqtt-password MQTT_PASSWORD
                        MQTT password for authentication
  --private             Only respond to direct messages
  --broadcast           Respond to all messages (overrides private)
  --startup-message     Send a startup message when the agent starts
  --no-startup-message  Don't send a startup message when the agent starts
  --gguf                Use GGUF model format (requires local model path)
  --cpu-only            Use CPU for inference only
  --use-llm-channel     Use a dedicated LLM channel
  --no-llm-channel      Don't use a dedicated LLM channel
  --llm-channel LLM_CHANNEL
                        Dedicated channel for LLM messages
  --llm-response-channel LLM_RESPONSE_CHANNEL
                        Channel for LLM responses
