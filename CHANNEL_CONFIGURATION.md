# Meshtastic LLM Channel Configuration Guide

This guide explains how to set up and configure the LLM channels for your Meshtastic mesh network.

## Understanding LLM Channels

The Meshtastic LLM Agent uses dedicated channels for AI-powered communication:

1. **LLM Channel** (`msh/us/2/json/llm` by default): 
   - Used for incoming messages that need LLM processing
   - Messages sent to this channel will be processed by the LLM agent

2. **LLM Response Channel** (`msh/us/2/json/llmres` by default):
   - Used for responses from the LLM agent
   - The agent publishes its responses to this channel

These channels work over both MQTT and direct Meshtastic mesh communication.

## Channel Configuration in Config.py

The LLM channels are configured in your `config.py` file:

```python
# LLM Channel Configuration
USE_LLM_CHANNEL = True
LLM_CHANNEL = "msh/us/2/json/llm"  # Channel for LLM requests
LLM_RESPONSE_CHANNEL = "msh/us/2/json/llmres"  # Channel for LLM responses
```

You can customize these channel names to fit your network topology, but ensure they follow the Meshtastic MQTT topic pattern (`msh/REGION/NODE/TYPE/CHANNEL`).

## Setting Up Meshtastic Channels

To properly configure your Meshtastic device for LLM communication:

### Via Meshtastic Web Interface

1. Access your Meshtastic device's web interface
2. Go to the "Channels" section
3. Create a new channel with the following parameters:
   - **Name**: "llm" (or your custom channel name)
   - **Type**: "JSON"
   - **Enabled**: Checked
4. Create another channel:
   - **Name**: "llmres" (or your custom response channel name)
   - **Type**: "JSON"
   - **Enabled**: Checked
5. Save the configuration

### Via Meshtastic CLI

```bash
# Set up the LLM request channel
meshtastic --seturl 'https://www.meshtastic.org/d/#{"n":"llm","t":5}'

# Set up the LLM response channel
meshtastic --seturl 'https://www.meshtastic.org/d/#{"n":"llmres","t":5}'
```

Note: Type 5 represents "JSON" channel type.

## Testing Channel Configuration

After setting up your channels, verify they're working correctly:

```bash
# Test sending a message to the LLM channel
./test_llm_channel.py --message "Test message to LLM channel"

# Test using the direct messaging approach
./test_send_message.py --mode channel --message "Test message via mesh"
```

## Channel Message Format

Messages sent to the LLM channel should use this JSON format:

```json
{
  "from": "user_id_or_name",
  "to": "llm",
  "id": "unique_message_id",
  "time": 1234567890,
  "text": "Your message content here"
}
```

The LLM agent will respond with:

```json
{
  "from": "llm",
  "to": "user_id_or_name",
  "id": "response_to_unique_message_id",
  "time": 1234567891,
  "text": "LLM response text"
}
```

## Advanced Channel Configuration

### Custom Channel Names

If you use custom channel names, update both your Meshtastic device and the `config.py` file.

### Channel Security

For enhanced security:
- Use channel encryption (PSK) on your Meshtastic device
- Configure restricted channel access
- Use authentication for MQTT

### Multi-Channel Setup

For complex networks, you can create multiple LLM channels:
1. Configure additional channels in the Meshtastic device
2. Update the `config.py` file to include multiple channel mappings
3. Use different channels for different purposes (e.g., "llm-public", "llm-private")

## Troubleshooting Channel Issues

If you experience issues with the LLM channels:

1. **Check channel existence**: Verify the channels exist on your Meshtastic device
2. **Check channel names**: Ensure the channel names match exactly in `config.py` and on the device
3. **Test MQTT connectivity**: Use `mosquitto_sub` to verify MQTT topics
4. **Check channel type**: Ensure the channels are configured as "JSON" type
5. **Verify message format**: Ensure messages follow the correct JSON format
6. **Check logs**: Look for channel-related errors in `lora_llm.log`

## Getting Help

If you continue to have issues with channel configuration:
1. Check the Meshtastic documentation
2. Join the Meshtastic community forum
3. File an issue in the project repository
