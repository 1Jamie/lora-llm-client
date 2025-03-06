# Hybrid Messaging in LoRa-LLM

This document explains the hybrid messaging approach implemented in the LoRa-LLM agent to improve message reliability.

## Overview

The hybrid messaging approach combines the strengths of two different communication channels:

1. **MQTT for receiving messages** - Provides reliable subscription and message reception
2. **Meshtastic TCP API for sending responses** - Offers direct access to the Meshtastic network for reliable message delivery

This approach solves reliability issues that can occur when using a single channel for both directions.

## Architecture

The hybrid messaging architecture consists of:

- `MeshtasticHybridClient` - Core component that:
  - Receives messages via MQTT subscription
  - Processes messages using the agent's LLM
  - Sends responses directly via the Meshtastic TCP API
  - Handles both direct and broadcast messaging modes

## Setup Requirements

To use the hybrid messaging approach, you need:

1. A running MQTT broker accessible to the system
2. A Meshtastic device connected to your network via TCP/IP (typically running meshtastic-web)
3. Proper network configuration to allow communication with both services

## Configuration

The hybrid messaging can be configured through command-line arguments:

```bash
python main.py --mqtt-host <MQTT_HOST> --mqtt-port <MQTT_PORT> \
               --tcp-host <TCP_HOST> --tcp-port <TCP_PORT> \
               [--private | --broadcast] [--use-llm-channel | --no-llm-channel]
```

Or using the provided start script:

```bash
./start.sh <MQTT_HOST> <MQTT_PORT> <TCP_HOST> <TCP_PORT> <PRIVATE_MODE> <STARTUP_MSG> <LLM_CHANNEL>
```

### Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| MQTT_HOST | Hostname/IP of MQTT broker | 10.0.0.159 |
| MQTT_PORT | Port of MQTT broker | 1883 |
| TCP_HOST | Hostname/IP of Meshtastic device | 10.0.0.213 |
| TCP_PORT | Port of Meshtastic TCP API | 4403 |
| PRIVATE_MODE | "private" or "broadcast" | "private" |
| STARTUP_MSG | "yes" or "no" | "default" |
| LLM_CHANNEL | "yes" or "no" | "default" |

## Testing

You can test the hybrid messaging system using the provided test script:

```bash
python test_hybrid_messaging.py --mqtt-host <MQTT_HOST> --mqtt-port <MQTT_PORT> \
                              --tcp-host <TCP_HOST> --tcp-port <TCP_PORT> \
                              [--use-llm-channel] [--message "Your test message"]
```

## Troubleshooting

Common issues and solutions:

1. **Messages are received but no response is sent**
   - Check that the TCP connection to the Meshtastic device is working
   - Verify that the TCP host and port are correct
   - Ensure the Meshtastic device is properly connected to the network

2. **Cannot connect to MQTT broker**
   - Verify the MQTT broker is running
   - Check network connectivity to the MQTT host
   - Confirm that firewall rules allow the connection

3. **Cannot connect to Meshtastic TCP interface**
   - Ensure the Meshtastic device is running with the HTTP server enabled
   - Verify the correct IP address and port
   - Check that meshtastic-web is running if using it as the TCP interface

## Benefits of Hybrid Approach

1. **Improved Reliability** - Messages are less likely to be lost during delivery
2. **Separation of Concerns** - Each interface handles the task it's best suited for
3. **Flexibility** - Can be configured for different network setups
4. **Fallback Options** - Can degrade gracefully if one interface is unavailable

## Future Improvements

Potential enhancements to the hybrid messaging system:

1. Automatic fallback to pure MQTT or TCP if one interface is unavailable
2. Dynamic discovery of Meshtastic devices on the network
3. Support for multiple Meshtastic devices
4. Web interface for monitoring message delivery status
