# TCP Troubleshooting Guide

This guide helps you troubleshoot common issues with the TCP interface for the Meshtastic LLM Agent.

## Understanding the TCP Interface

The TCP interface provides a direct communication path to the Meshtastic LLM Agent. It features:

- Automatic reconnection with exponential backoff
- Fallback to MQTT when TCP is unavailable
- Reliable message delivery with retry mechanisms
- Channel-based messaging compatible with Meshtastic topics

## Checking TCP Connection Status

First, check if the TCP server is running and accessible:

```bash
# Test the TCP connection
python test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT
```

## Common TCP Issues and Solutions

### 1. Connection Refused

**Symptoms:**
- "Connection refused" errors
- Automatic retries fail
- Log shows "Connection attempt failed: [Errno 111] Connection refused"

**Solutions:**
- Check if the TCP server is running on the target host
- Verify the correct IP address and port are configured in config.py
- Check firewall settings: `sudo ufw status`
- Ensure the port is open: `sudo ufw allow YOUR_PORT`
- Try connecting from another machine to isolate the issue

### 2. Connection Timeouts

**Symptoms:**
- "Socket timeout" errors
- Connection attempts take a long time before failing
- Log shows "Connection attempt failed: timed out"

**Solutions:**
- Check network connectivity between client and server
- Verify that the network allows TCP traffic on the configured port
- Check if there are any network devices (routers, firewalls) blocking the connection
- Try increasing the socket timeout setting in the code
- Use `ping` to verify basic connectivity

### 3. Connection Drops

**Symptoms:**
- Connection established but frequently drops
- "Broken pipe" or "Connection reset by peer" errors
- Unstable connection behavior

**Solutions:**
- Check for network stability issues
- Verify that keep-alive settings are properly configured
- Ensure the server isn't overloaded
- Check for any network throttling or bandwidth limitations
- Monitor the connection using the test_tcp_connection.py tool with --test-reconnection flag

### 4. Channel Messaging Problems

**Symptoms:**
- Connection works but messages don't reach intended recipients
- Wrong channel routing
- Messages sent but no responses received

**Solutions:**
- Verify channel names match exactly between sender and receiver
- Check channel subscriptions in the Meshtastic device
- Use the log debug mode to trace message routing
- Test with a simple channel to isolate the issue

## Testing TCP Interface with Debug Logging

For more detailed debugging, enable debug logging:

```bash
# Set the logging level to DEBUG
export LOG_LEVEL=DEBUG

# Run the test script
python test_tcp_connection.py --host YOUR_TCP_HOST --port YOUR_TCP_PORT
```

## Advanced TCP Troubleshooting

### Network Analysis

Use network analysis tools to diagnose connection issues:

```bash
# Check if the port is open and listening
sudo netstat -tulpn | grep YOUR_PORT

# Use tcpdump to analyze the TCP traffic
sudo tcpdump -i any port YOUR_PORT -vv

# Check for connectivity using telnet
telnet YOUR_TCP_HOST YOUR_PORT
```

### Testing TCP Server

Make sure the TCP server component is working correctly:

```bash
# Check if the process is running
ps aux | grep "tcp_server"

# Check the server logs
tail -f tcp_server.log
```

### Testing Fallback Mechanism

To test if the fallback to MQTT is working correctly:

1. Start the agent with both interfaces enabled
2. Test that TCP communication works
3. Stop the TCP server
4. Send another message - the system should automatically fall back to MQTT
5. Check logs to verify the fallback behavior

## Reinstating TCP Connectivity

If you need to completely reset TCP connectivity:

1. Stop any running TCP server instances
2. Restart the network interface: `sudo systemctl restart NetworkManager`
3. Verify port availability: `sudo netstat -tulpn | grep YOUR_PORT`
4. Restart the Meshtastic LLM Agent
5. Run the TCP connection test again

## Getting Help

If you're still having issues with the TCP interface:

1. Check the full system logs for more details
2. Post your issue on the Meshtastic community forums
3. Include the output from the test_tcp_connection.py script
4. Share relevant sections from your logs (with sensitive information removed)
