#!/usr/bin/env python3
import logging
import time
import json
import threading
import queue
from typing import Dict, Any, List, Optional, Callable
import traceback

import paho.mqtt.client as mqtt

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeshtasticMqttClient:
    """Client for interacting with Meshtastic over MQTT"""
    
    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: str = None,
        password: str = None,
        private_mode: bool = False,
        send_startup_message: bool = False,
        use_llm_channel: bool = False,
        llm_channel: str = None,
        llm_response_channel: str = None
    ):
        """
        Initialize the Meshtastic MQTT client
        
        Args:
            broker: MQTT broker host
            port: MQTT broker port
            username: MQTT username
            password: MQTT password
            private_mode: If True, only respond to direct messages
            send_startup_message: If True, send a startup message when connected
            use_llm_channel: If True, use a dedicated LLM channel
            llm_channel: MQTT topic for LLM channel
            llm_response_channel: MQTT topic for LLM response channel
        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.private_mode = private_mode
        self.send_startup_message = send_startup_message
        self.use_llm_channel = use_llm_channel
        self.llm_channel = llm_channel
        self.llm_response_channel = llm_response_channel
        
        # Connection status
        self.connected = False
        
        # Message handling
        self.message_queue = queue.Queue()
        self.message_callback = None
        self.running = False
        self.message_thread = None
        
        # Topic configuration
        self.base_topic = "msh"
        self.rx_topic_prefix = f"{self.base_topic}/+/rx"  # Receive messages from all nodes
        self.tx_topic = f"{self.base_topic}/broadcast/txt"  # Send broadcast messages
        self.nodeinfo_topic_prefix = f"{self.base_topic}/+/nodeinfo"  # Node information
        
        # Node info
        self.my_node_id = None
        self.nodes = {}
        
    def connect(self) -> bool:
        """
        Connect to the MQTT broker
        
        Returns:
            bool: True if connection is successful, False otherwise
        """
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}")
            
            # Create a new MQTT client instance
            client_id = f"meshtastic-llm-agent-{int(time.time())}"
            self.client = mqtt.Client(client_id=client_id)
            
            # Set username and password if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            # Connect to the broker
            self.client.connect(self.broker, self.port, keepalive=60)
            
            # Start the MQTT loop in a background thread
            self.client.loop_start()
            
            # Wait for connection to be established
            start_time = time.time()
            while not self.connected and time.time() - start_time < 10:
                time.sleep(0.1)
            
            return self.connected
            
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {str(e)}")
            return False
    
    def disconnect(self):
        """
        Disconnect from the MQTT broker
        """
        if self.connected:
            try:
                self.client.disconnect()
                self.client.loop_stop()
                self.connected = False
                logger.info("Disconnected from MQTT broker")
            except Exception as e:
                logger.error(f"Error disconnecting from MQTT broker: {str(e)}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback for when the client connects to the broker
        """
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            self.connected = True
            
            # Subscribe to Meshtastic topics
            self.client.subscribe(self.rx_topic_prefix)
            self.client.subscribe(self.nodeinfo_topic_prefix)
            
            # Subscribe to LLM channel if enabled
            if self.use_llm_channel and self.llm_channel:
                self.client.subscribe(self.llm_channel)
                logger.info(f"Subscribed to LLM channel: {self.llm_channel}")
                
                # Also subscribe to all channel messages that might come from Meshtastic
                # Format: msh/[region]/[channel_index]/#
                # This ensures we catch all messages on all channels
                channel_base = "/".join(self.llm_channel.split("/")[:-1])
                self.client.subscribe(f"{channel_base}/#")
                logger.info(f"Subscribed to all channel messages: {channel_base}/#")
                
                # Log that we'll be responding on a different channel
                logger.info(f"Will respond on LLM response channel: {self.llm_response_channel}")
            
            # Request node information
            self.request_node_info()
            
            # Send startup message if enabled
            if self.send_startup_message:
                self.send_broadcast("📢 LLM Agent is now online")
        else:
            logger.error(f"Failed to connect to MQTT broker, return code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """
        Callback for when the client disconnects from the broker
        """
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker, return code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_message(self, client, userdata, msg):
        """
        Callback for when a message is received from the broker
        """
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logger.debug(f"Received message on topic: {topic}")
            logger.debug(f"Payload: {payload[:100]}...")  # Log first 100 chars
            
            # Check if this is a message from the LLM channel
            is_llm_channel = False
            if self.use_llm_channel and self.llm_channel:
                # Check if the topic starts with the LLM channel prefix
                if topic.startswith(self.llm_channel.rstrip('/')) or topic.startswith(self.llm_channel):
                    is_llm_channel = True
                    logger.info(f"Detected message from LLM channel: {topic}")
                    
                    # Log the full payload for debugging
                    logger.info(f"LLM channel payload: {payload}")
            
            # Process LLM channel messages first
            if is_llm_channel:
                try:
                    # Extract the message text and metadata
                    text = None
                    from_id = None
                    to_id = None
                    
                    try:
                        data = json.loads(payload)
                        logger.info(f"Parsed JSON data: {data}")
                        
                        # Extract key information - assume fields may be missing
                        text = None
                        from_id = None
                        to_id = None
                        message_type = data.get('type', '')
                        
                        # Process based on message type and format
                        
                        # Case 1: Meshtastic native 'text' type message
                        if message_type == 'text' and isinstance(data.get('payload'), dict):
                            text = data['payload'].get('text', '')
                            from_id = data.get('sender') or str(data.get('from', ''))
                            to_id = str(data.get('to', 'broadcast'))
                            logger.info(f"Detected native Meshtastic text message from {from_id}: {text[:50]}...")
                            
                            # Create message object and process it directly
                            if text:
                                message = {
                                    "text": text,
                                    "from_id": from_id,
                                    "to_id": to_id,
                                    "sender": from_id,
                                    "timestamp": time.time(),
                                    "is_direct": to_id != "broadcast" and to_id != 4294967295,
                                    "is_llm_channel": True
                                }
                                logger.info(f"Processing native Meshtastic text message: {text}")
                                self._process_message(message)
                            return  # Skip further processing
                        
                        # Case 2: Our custom 'sendtext' format
                        elif message_type == 'sendtext' and isinstance(data.get('payload'), dict):
                            text = data['payload'].get('text', '')
                            from_id = data['payload'].get('from_id') or str(data.get('from', ''))
                            to_id = data['payload'].get('to_id')
                            logger.info(f"Detected custom sendtext message from {from_id}: {text[:50]}...")
                        
                        # Case 3: Any JSON with a payload containing text field
                        elif isinstance(data.get('payload'), dict) and 'text' in data.get('payload', {}):
                            text = data['payload']['text']
                            from_id = data.get('sender') or str(data.get('from', ''))
                            to_id = str(data.get('to', 'broadcast'))
                            logger.info(f"Detected JSON message with text payload from {from_id}: {text[:50]}...")
                        
                        # Case 4: Direct text field
                        elif 'text' in data:
                            text = data.get('text', '')
                            from_id = data.get('from_id') or data.get('sender', 'unknown')
                            to_id = data.get('to_id') or data.get('to', 'broadcast')
                            logger.info(f"Detected JSON with direct text field from {from_id}: {text[:50]}...")
                        
                        # Case 5: Any other format - try common field names
                        else:
                            # Try to extract text from any field that might contain it
                            for key in ['text', 'message', 'content', 'body']:
                                if key in data and isinstance(data[key], str):
                                    text = data[key]
                                    break
                            
                            # If no text found, use the entire payload as text
                            if not text:
                                text = payload
                            
                            # Try to extract sender info
                            for key in ['from', 'from_id', 'sender', 'user', 'userId']:
                                if key in data:
                                    from_id = str(data[key])
                                    break
                            
                            # If no sender found, extract from topic if possible
                            if not from_id:
                                topic_parts = topic.split('/')
                                if len(topic_parts) >= 1:
                                    last_part = topic_parts[-1]
                                    if last_part.startswith('!'):
                                        from_id = last_part
                                    else:
                                        from_id = "unknown"
                                else:
                                    from_id = "unknown"
                            
                            logger.info(f"Detected generic JSON message from {from_id}: {text[:50]}...")
                        
                    except json.JSONDecodeError:
                        # Not JSON, treat as plain text
                        text = payload
                        from_id = "unknown"
                        
                        # Try to extract from_id from topic
                        topic_parts = topic.split('/')
                        if len(topic_parts) >= 1:
                            last_part = topic_parts[-1]
                            if last_part.startswith('!'):
                                from_id = last_part
                            else:
                                from_id = "unknown"
                        
                        logger.info(f"Detected plain text message from {from_id}: {text[:50]}...")
                    
                    # Skip empty messages
                    if not text:
                        logger.debug("Ignoring empty message")
                        return
                    
                    # Skip messages that are just echoes of our startup message
                    if text.startswith("📢 LLM Agent is now online"):
                        logger.debug("Ignoring startup message echo")
                        return
                        
                    # Create message object
                    message = {
                        "text": text,
                        "from_id": from_id,
                        "to_id": to_id or "broadcast",
                        "sender": from_id,
                        "timestamp": time.time(),
                        "is_direct": True,  # Treat LLM channel messages as direct
                        "is_llm_channel": True
                    }
                    
                    # Process message directly instead of queueing
                    logger.info(f"Processing LLM channel message from {from_id}: {text}")
                    self._process_message(message)
                    
                except Exception as e:
                    logger.error(f"Error processing LLM channel message: {str(e)}")
                    logger.error(traceback.format_exc())
                
                return  # Skip further processing
            
            # Process regular Meshtastic messages
            # Process based on topic
            if topic.startswith(self.rx_topic_prefix):
                try:
                    # Parse JSON payload
                    data = json.loads(payload)
                    
                    # Extract message data
                    packet_id = data.get('id', 'unknown')
                    from_node_id = data.get('fromId', 'unknown')
                    to_node_id = data.get('toId', 'broadcast')
                    channel = data.get('channel', 0)
                    text = data.get('text', '')
                    
                    # Skip our own messages to avoid feedback loops
                    if from_node_id == self.my_node_id:
                        logger.debug(f"Ignoring our own message: {text[:50]}...")
                        return
                    
                    # Create message object
                    message = {
                        "text": text,
                        "from_id": from_node_id,
                        "to_id": to_node_id,
                        "sender": from_node_id,
                        "channel": channel,
                        "packet_id": packet_id,
                        "timestamp": time.time(),
                        "is_direct": to_node_id != "broadcast",
                        "is_llm_channel": False
                    }
                    
                    # Add to processing queue
                    self.message_queue.put(message)
                    logger.info(f"Queued message from {from_node_id}: {text}")
                    
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in message: {payload}")
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
            
            # Process node info
            elif topic.startswith(self.nodeinfo_topic_prefix):
                try:
                    # Parse JSON payload
                    try:
                        data = json.loads(payload)
                        
                        # Extract node info
                        node_id = data.get('num', 'unknown')
                        node_name = data.get('user', {}).get('longName', 'unknown')
                        
                        # Store node info
                        self.nodes[node_id] = {
                            "id": node_id,
                            "name": node_name,
                            "last_seen": time.time()
                        }
                        
                        logger.info(f"Updated node info for {node_id} ({node_name})")
                        
                        # If this is our node, store our node ID
                        if node_name == "llm_agent":
                            self.my_node_id = node_id
                            logger.info(f"Identified our node ID: {node_id}")
                            
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in node info: {payload}")
                        
                except Exception as e:
                    logger.error(f"Error processing node info: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
    
    def _process_message(self, message):
        """
        Process a message from the queue
        """
        try:
            # Extract message data
            text = message.get('text', '')
            from_id = message.get('from_id', 'unknown')
            to_id = message.get('to_id', 'broadcast')
            is_direct = message.get('is_direct', False)
            is_llm_channel = message.get('is_llm_channel', False)
            
            logger.info(f"Processing message from {from_id}: {text[:50]}...")
            logger.info(f"Message details: is_direct={is_direct}, is_llm_channel={is_llm_channel}")
            
            # Skip empty messages
            if not text:
                logger.debug("Ignoring empty message")
                return
            
            # Skip our own messages to avoid feedback loops
            if from_id == self.my_node_id or from_id == "llm_agent":
                logger.debug(f"Ignoring our own message: {text[:50]}...")
                return
            
            # Generate response using the agent
            try:
                # Generate response
                if self.message_callback:
                    logger.info("Calling message callback function to generate response")
                    response = self.message_callback(message)
                    logger.info(f"Callback returned response: {response[:50] if response else 'None'}...")
                else:
                    logger.warning("No message callback set")
                    return
                
                # Skip empty responses
                if not response:
                    logger.warning("Empty response from agent")
                    return
                
                logger.info(f"Generated response: {response[:50]}...")
                
                # Send response
                if is_llm_channel:
                    # For LLM channel messages, send response to the LLM response channel
                    # Format the response as a Meshtastic JSON message
                    response_data = {
                        "from": 1234567890,  # Placeholder ID for LLM agent
                        "type": "sendtext",
                        "payload": {
                            "text": response,
                            "from_id": "llm_agent",
                            "to_id": from_id if is_direct else "broadcast"
                        }
                    }
                    
                    # Send to LLM response channel
                    success = self.publish_to_llm_response_channel(response_data)
                    if success:
                        logger.info(f"Sent response to {self.llm_response_channel} for {from_id}: {response[:50]}...")
                    else:
                        logger.error(f"Failed to send response to {self.llm_response_channel} for {from_id}")
                else:
                    # For regular Meshtastic messages
                    # Send direct or broadcast response based on private mode and message type
                    if self.private_mode or is_direct:
                        # Send direct response to the sender
                        success = self.send_direct_message(from_id, response)
                        if success:
                            logger.info(f"Sent direct response to {from_id}: {response[:50]}...")
                        else:
                            logger.error(f"Failed to send direct response to {from_id}")
                    else:
                        # Send broadcast response
                        success = self.send_broadcast_message(response)
                        if success:
                            logger.info(f"Sent broadcast response: {response[:50]}...")
                        else:
                            logger.error(f"Failed to send broadcast response")
            
            except Exception as e:
                logger.error(f"Error generating response: {str(e)}")
                logger.error(traceback.format_exc())
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            logger.error(traceback.format_exc())
    
    def send_broadcast(self, text: str) -> bool:
        """
        Send a broadcast message to all nodes
        
        Args:
            text: Text message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.connected:
            logger.error("Cannot send message, not connected")
            return False
        
        try:
            # Send to broadcast topic
            topic = self.tx_topic
            payload = text
            
            result = self.client.publish(topic, payload, qos=1)
            if result.rc != 0:
                logger.error(f"Failed to send broadcast message: {result.rc}")
                return False
            
            logger.info(f"Broadcast message sent: {text}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending broadcast message: {str(e)}")
            return False
    
    def send_message(self, text: str, to_id: str = None) -> bool:
        """
        Send a message to a specific node or broadcast
        
        Args:
            text: Text message to send
            to_id: Node ID to send to, or None for broadcast
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.connected:
            logger.error("Cannot send message, not connected")
            return False
        
        try:
            if to_id is None:
                # Send broadcast
                return self.send_broadcast(text)
            
            # If we don't know our node ID yet, use broadcast with 'to' field
            if self.my_node_id is None:
                logger.warning("Our node ID is unknown, sending via broadcast topic with 'to' field")
                topic = self.tx_topic
                payload = json.dumps({
                    "text": text,
                    "to": to_id
                })
            else:
                # Send via our node's txt topic with 'to' field
                topic = f"{self.base_topic}/{self.my_node_id}/c/{to_id}/txt"
                payload = text
            
            result = self.client.publish(topic, payload, qos=1)
            if result.rc != 0:
                logger.error(f"Failed to send direct message to {to_id}: {result.rc}")
                return False
            
            logger.info(f"Direct message sent to {to_id}: {text}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending direct message: {str(e)}")
            return False
    
    def set_message_callback(self, callback: Callable[[Dict[str, Any]], Optional[str]]):
        """
        Set callback for processing messages
        
        Args:
            callback: Function that takes a message dict and returns a response string or None
        """
        self.message_callback = callback
    
    def start(self):
        """
        Start the message processing thread
        """
        if not self.connected:
            logger.error("Cannot start - not connected to MQTT broker")
            return False
        
        self.running = True
        
        # Start message processing thread
        self.message_thread = threading.Thread(target=self._process_queue)
        self.message_thread.daemon = True
        self.message_thread.start()
        
        logger.info("Message processing started")
        return True
    
    def stop(self):
        """
        Stop the message processing thread
        """
        self.running = False
        
        # Wait for thread to finish
        if self.message_thread and self.message_thread.is_alive():
            self.message_thread.join(timeout=2.0)
        
        logger.info("Message processing stopped")
        
        # Disconnect
        self.disconnect()
    
    def _process_queue(self):
        """
        Process messages from the queue
        """
        while self.running:
            try:
                # Get message from queue with timeout
                try:
                    message = self.message_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Process the message
                self._process_message(message)
                
                self.message_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in message processing thread: {str(e)}")
    
    def request_node_info(self):
        """
        Request node information from all nodes
        """
        if not self.connected:
            logger.error("Not connected to MQTT broker")
            return False
        
        try:
            # Publish to the nodeinfo request topic
            topic = f"{self.base_topic}/request/nodeinfo"
            self.client.publish(topic, "", qos=1)
            logger.info("Requested node information")
            return True
        except Exception as e:
            logger.error(f"Error requesting node information: {str(e)}")
            return False

    def publish_to_llm_response_channel(self, data):
        """
        Publish a message to the LLM response channel
        
        Args:
            data: Data to publish (will be converted to JSON)
            
        Returns:
            bool: True if published successfully, False otherwise
        """
        try:
            if not self.client or not self.client.is_connected():
                logger.warning("MQTT client not connected, attempting to reconnect")
                self.connect()
                if not self.client or not self.client.is_connected():
                    logger.error("Failed to reconnect to MQTT, cannot publish response")
                    return False
                    
            if not self.llm_response_channel:
                logger.error("LLM response channel not specified")
                return False
                
            logger.info(f"Publishing to LLM response channel: {self.llm_response_channel}")
            
            # Convert to JSON if needed
            if isinstance(data, dict):
                json_data = json.dumps(data)
            else:
                json_data = data
                
            # Publish the message
            result = self.client.publish(self.llm_response_channel, json_data)
            
            # Check if the message was published successfully
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Successfully published response to LLM response channel: {str(data)[:50]}...")
                return True
            else:
                logger.error(f"Failed to publish to LLM response channel, error code: {result.rc}")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing to LLM response channel: {str(e)}")
            return False
            
    def send_to_llm_channel(self, payload):
        """
        Send a message to the LLM channel
        
        Args:
            payload: Message payload (string or JSON object)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.use_llm_channel:
                logger.warning("LLM channel not enabled")
                return False
            
            if not self.llm_response_channel:
                logger.warning("LLM response channel not configured")
                return False
            
            # Ensure payload is a string
            if not isinstance(payload, str):
                if isinstance(payload, dict):
                    # Extract to_id for direct messaging if it exists
                    to_id = None
                    is_direct = False
                    
                    if 'payload' in payload and 'to_id' in payload['payload']:
                        to_id = payload['payload']['to_id']
                        # Check if this is a direct message (not broadcast)
                        is_direct = to_id != 'broadcast'
                    
                    payload_str = json.dumps(payload)
                else:
                    payload_str = str(payload)
                    is_direct = False
                    to_id = None
            else:
                payload_str = payload
                is_direct = False
                to_id = None
            
            # Use user-specific response channel for direct messages
            response_channel = self.llm_response_channel
            if is_direct and to_id:
                # If the to_id doesn't start with '!', add it
                if not to_id.startswith('!'):
                    user_suffix = f"!{to_id}"
                else:
                    user_suffix = to_id
                
                # Add the user ID to the response channel
                if response_channel.endswith('/'):
                    response_channel = f"{response_channel}{user_suffix}"
                else:
                    response_channel = f"{response_channel}/{user_suffix}"
                
                logger.info(f"Using user-specific response channel: {response_channel}")
            
            # Publish to the appropriate response channel
            logger.info(f"Publishing to LLM response channel: {response_channel}")
            result = self.client.publish(response_channel, payload_str, qos=1)
            
            if result.rc != 0:
                logger.error(f"Failed to publish to LLM response channel: {result.rc}")
                return False
            else:
                logger.info(f"Successfully sent message to LLM response channel: {payload_str[:50]}...")
                return True
                
        except Exception as e:
            logger.error(f"Error sending to LLM response channel: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def send_direct_message(self, to_id: str, text: str) -> bool:
        """
        Send a direct message to a specific node
        
        Args:
            to_id: Node ID to send to
            text: Text message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.connected:
            logger.error("Cannot send message, not connected")
            return False
        
        try:
            # If we don't know our node ID yet, use broadcast with 'to' field
            if self.my_node_id is None:
                logger.warning("Our node ID is unknown, sending via broadcast topic with 'to' field")
                topic = self.tx_topic
                payload = json.dumps({
                    "text": text,
                    "to": to_id
                })
            else:
                # Send via our node's txt topic with 'to' field
                topic = f"{self.base_topic}/{self.my_node_id}/c/{to_id}/txt"
                payload = text
            
            result = self.client.publish(topic, payload, qos=1)
            if result.rc != 0:
                logger.error(f"Failed to send direct message to {to_id}: {result.rc}")
                return False
            
            logger.info(f"Direct message sent to {to_id}: {text}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending direct message: {str(e)}")
            return False

    def send_broadcast_message(self, text: str) -> bool:
        """
        Send a broadcast message to all nodes
        
        Args:
            text: Text message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.connected:
            logger.error("Cannot send message, not connected")
            return False
        
        try:
            # Send to broadcast topic
            topic = self.tx_topic
            payload = text
            
            result = self.client.publish(topic, payload, qos=1)
            if result.rc != 0:
                logger.error(f"Failed to send broadcast message: {result.rc}")
                return False
            
            logger.info(f"Broadcast message sent: {text}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending broadcast message: {str(e)}")
            return False
