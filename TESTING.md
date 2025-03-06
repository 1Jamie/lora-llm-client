# Testing Guide for Meshtastic LLM Agent

This guide provides instructions for testing the various components of the Meshtastic LLM Agent system, including MQTT, TCP, and LLM channel communications.

## Prerequisites

Before testing, make sure you have:

1. Completed the setup process using `setup.sh`
2. Have a running MQTT broker (Mosquitto)
3. Have a Meshtastic device properly configured and connected

## 1. Testing MQTT Communication

The MQTT broker is the foundation of the system's communication. Test it with:

```bash
# Check if the MQTT broker is running
sudo systemctl status mosquitto

# Test publishing a message
mosquitto_pub -h localhost -p 1883 -u YOUR_USERNAME -P YOUR_PASSWORD -t "test/topic" -m "Test message"

# Listen for messages on all Meshtastic topics
mosquitto_sub -h localhost -p 1883 -u YOUR_USERNAME -P YOUR_PASSWORD -t "msh/#" -v
```

If you encounter issues, refer to the `MQTT_TROUBLESHOOTING.md` file.

## 2. Testing LLM Channel Communication

The LLM channel allows non-Meshtastic devices to interact with the LLM agent. Test it with:

```bash
# Run the test script with default values from your config
python test_llm_channel.py

# Run with custom parameters
python test_llm_channel.py --mqtt-host YOUR_HOST --mqtt-port YOUR_PORT --message "Custom test message"
```

Expected behavior:
1. The script should connect to the MQTT broker
2. It should send your test message to the LLM channel
3. The LLM agent should process the message and respond
4. The script should receive and display the response

## 3. Testing TCP Connection Reliability

The TCP connection provides a direct communication path with enhanced reliability through auto-reconnection. Test it with:

```bash
# Basic connection test
python test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT

# Test reconnection capabilities
python test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT --test-reconnection --num-reconnects 5
```

Expected behavior:
1. The script should attempt to connect to the TCP server
2. If connection fails, it should automatically retry with exponential backoff
3. In reconnection test mode, it should perform multiple connect-disconnect cycles
4. The script should report success or failure for each test

## 4. Testing End-to-End Communication

For complete end-to-end testing, start the agent and test communication via different interfaces:

```bash
# Start the agent
./start.sh

# In another terminal, send a test message via MQTT
python test_llm_channel.py --message "Testing via MQTT"

# Test via TCP (if TCP interface is enabled)
python test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT --message "Testing via TCP"

# Send a message via Meshtastic device
# This can be done through the Meshtastic app or CLI
```

## 5. Testing Failover Mechanisms

To test the system's resilience and failover mechanisms:

1. Start the agent with both MQTT and TCP interfaces enabled
2. Send a test message via TCP
3. Disconnect the TCP server (e.g., stop the service)
4. Send another message - it should automatically fall back to MQTT
5. Restart the TCP server
6. Send another message - it should reconnect to TCP and use it

## 6. Testing Model Functionality

To test the language model itself:

```bash
# Send a specific prompt to test the model's capabilities
python test_llm_channel.py --message "Summarize the capabilities of Meshtastic in 3 sentences."
```

## Troubleshooting

If you encounter issues during testing:

1. Check the logs: `tail -f lora_llm.log`
2. Verify all services are running
3. Ensure your Meshtastic device is properly connected
4. Check network connectivity between all components
5. Refer to the troubleshooting guides for specific components

## Advanced Testing

For advanced users, you can create custom test scripts to:

1. Simulate network outages
2. Test with high message volumes
3. Test with multiple devices simultaneously
4. Measure response times and system performance

## Getting Help

If you need additional assistance with testing or troubleshooting, please:

1. Check the Meshtastic documentation: https://meshtastic.org/docs/
2. Join the Meshtastic community forums
3. Open an issue on the project's GitHub repository
