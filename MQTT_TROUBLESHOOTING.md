# MQTT Troubleshooting Guide

This guide helps you troubleshoot common issues with the MQTT setup for Meshtastic.

## Checking MQTT Broker Status

First, check if the Mosquitto MQTT broker is running:

```bash
sudo systemctl status mosquitto
```

If it's not running, start it:

```bash
sudo systemctl start mosquitto
```

## Verifying MQTT Configuration

Check the Mosquitto configuration:

```bash
cat /etc/mosquitto/mosquitto.conf
```

Make sure it includes:
- `listener 1883` (or your configured port)
- `allow_anonymous true` (if not using authentication)

## Testing MQTT Connectivity

Use our test script to verify the MQTT broker is working:

```bash
./check_mqtt_broker.py
```

If this fails, check:
1. Firewall settings
2. Network connectivity
3. Mosquitto logs

## Common Issues and Solutions

### 1. Connection Refused

**Symptoms:**
- "Connection refused" errors
- Devices can't connect to broker

**Solutions:**
- Check if Mosquitto is running
- Verify the correct IP address is being used
- Check firewall settings: `sudo ufw status`
- Ensure port 1883 is open: `sudo ufw allow 1883`

### 2. Authentication Failures

**Symptoms:**
- "Not authorized" errors
- Return code 4 or 5 when connecting

**Solutions:**
- Verify username and password are correct
- Check if authentication is properly configured in mosquitto.conf
- Ensure password file exists and has correct permissions

### 3. Messages Not Being Received

**Symptoms:**
- Devices connect but messages aren't received
- No errors, but no communication

**Solutions:**
- Check topic subscriptions
- Verify Meshtastic devices are properly configured for MQTT
- Use `mosquitto_sub` to monitor topics:
  ```bash
  mosquitto_sub -v -t "msh/#"
  ```

### 4. Meshtastic Device Not Connecting to MQTT

**Symptoms:**
- Meshtastic device doesn't show as connected in MQTT
- No messages from device

**Solutions:**
- Verify MQTT settings on the device:
  ```bash
  meshtastic --getconfig mqtt
  ```
- Make sure the device has the correct server address and port
- Check if the device has internet connectivity
- Try rebooting the device:
  ```bash
  meshtastic --reboot
  ```

## Debugging Tools

### Monitor All MQTT Traffic

```bash
mosquitto_sub -v -t "#"
```

### Send Test Message

```bash
mosquitto_pub -t "msh/broadcast/txt" -m "Test message"
```

### Check MQTT Logs

```bash
sudo journalctl -u mosquitto -f
```

## Advanced Troubleshooting

### Network Issues

If you suspect network issues:

```bash
# Check if port 1883 is open
sudo netstat -tulpn | grep 1883

# Test connectivity from another machine
telnet your_server_ip 1883
```

### Permissions Issues

If you suspect permissions issues:

```bash
# Check Mosquitto user and permissions
ls -la /var/lib/mosquitto/
sudo chown -R mosquitto:mosquitto /var/lib/mosquitto/
```

### Reinstalling Mosquitto

If all else fails, you can reinstall Mosquitto:

```bash
sudo apt remove --purge mosquitto mosquitto-clients
sudo apt autoremove
sudo apt install mosquitto mosquitto-clients
```

Then run our setup script again:

```bash
sudo ./setup_mqtt_broker.sh
```

## Getting Help

If you're still having issues:

1. Check the Meshtastic documentation: https://meshtastic.org/docs/
2. Join the Meshtastic community: https://meshtastic.org/docs/community
3. Open an issue on our GitHub repository
