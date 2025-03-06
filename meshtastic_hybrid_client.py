#!/usr/bin/env python3
import logging
import time
import json
import threading
from typing import Dict, Any, Optional, Callable

from meshtastic_mqtt_client import MeshtasticMqttClient
from meshtastic_tcp_client import MeshtasticTcpClient

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeshtasticHybridClient:
    """
    Hybrid client that receives messages via MQTT and sends responses via TCP
    This addresses issues with sending messages through MQTT while still using
    MQTT for receiving messages.
    """
    
    def __init__(
        self,
        # MQTT parameters
        mqtt_broker: str,
        mqtt_port: int = 1883,
        mqtt_username: str = None,
        mqtt_password: str = None,
        use_llm_channel: bool = False,
        llm_channel: str = None,
        llm_response_channel: str = None,
        # TCP parameters
        tcp_host: str = None,
        tcp_port: int = 4403,
        # Common parameters
        private_mode: bool = False,
        send_startup_message: bool = False
    ):
        """
        Initialize the hybrid Meshtastic client
        
        Args:
            mqtt_broker: MQTT broker host
            mqtt_port: MQTT broker port
            mqtt_username: MQTT username
            mqtt_password: MQTT password
            use_llm_channel: If True, use a dedicated LLM channel
            llm_channel: MQTT topic for LLM channel
            llm_response_channel: MQTT topic for LLM response channel
            tcp_host: IP address or hostname of the Meshtastic device for TCP
            tcp_port: TCP port for Meshtastic device
            private_mode: If True, only respond to direct messages
            send_startup_message: If True, send a startup message when connected
        """
        self.private_mode = private_mode
        self.send_startup_message = send_startup_message
        self.use_llm_channel = use_llm_channel
        self.llm_channel = llm_channel
        self.llm_response_channel = llm_response_channel
        
        # Initialize MQTT client for receiving messages
        self.mqtt_client = MeshtasticMqttClient(
            broker=mqtt_broker,
            port=mqtt_port,
            username=mqtt_username,
            password=mqtt_password,
            private_mode=private_mode,
            send_startup_message=False,  # We'll handle startup message ourselves
            use_llm_channel=use_llm_channel,
            llm_channel=llm_channel,
            llm_response_channel=llm_response_channel
        )
        
        # Initialize TCP client for sending messages
        self.tcp_client = MeshtasticTcpClient(
            host=tcp_host if tcp_host else mqtt_broker,  # Default to MQTT broker if not specified
            port=tcp_port,
            private_mode=private_mode
        )
        
        # Message handling
        self.message_callback = None
        self.connected = False
    
    def connect(self) -> bool:
        """
        Connect to both MQTT broker and Meshtastic TCP interface
        
        Returns:
            bool: True if both connections are successful, False otherwise
        """
        logger.info("Connecting to MQTT and TCP interfaces...")
        
        # Connect to MQTT broker first (for receiving)
        mqtt_connected = self.mqtt_client.connect()
        if not mqtt_connected:
            logger.error("Failed to connect to MQTT broker")
            return False
        
        # Connect to TCP interface (for sending) with retries
        max_retries = 4  # Try up to 4 times to connect to TCP
        tcp_connected = self.tcp_client.connect(max_retries=max_retries)
        
        if mqtt_connected and tcp_connected:
            logger.info("Successfully connected to both MQTT and TCP interfaces")
        elif mqtt_connected:
            logger.warning("Connected to MQTT but failed to connect to TCP interface")
        elif tcp_connected:
            logger.warning("Connected to TCP but failed to connect to MQTT broker")
        else:
            logger.error("Failed to connect to both MQTT and TCP interfaces")
        
        # Both connections successful
        self.connected = mqtt_connected and tcp_connected
        
        # Allow operation even if only MQTT is connected, with warnings
        if mqtt_connected and not tcp_connected:
            logger.warning("Operating in MQTT-only mode (can receive messages but may not be able to send responses)")
            self.connected = True  # Allow operation with just MQTT
        
        logger.info("Successfully connected to both MQTT and TCP interfaces")
        
        # Override MQTT message callback with our own handler
        self.mqtt_client.set_message_callback(self._handle_mqtt_message)
        
        # Send startup message if enabled
        if self.send_startup_message:
            self.send_startup_messages()
        
        return self.connected
    
    def disconnect(self):
        """
        Disconnect from both MQTT broker and Meshtastic TCP interface
        """
        logger.info("Disconnecting from MQTT and TCP interfaces...")
        
        # Disconnect from MQTT
        self.mqtt_client.disconnect()
        
        # Disconnect from TCP
        self.tcp_client.disconnect()
        
        self.connected = False
        logger.info("Disconnected from both interfaces")
    
    def _handle_mqtt_message(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Handle messages from MQTT client
        This method intercepts messages from the MQTT client, processes them with
        the callback, and then instead of letting the MQTT client send the response,
        it uses the TCP client to send the response.
        
        Args:
            message: Message dict from MQTT client
            
        Returns:
            None: We handle sending the response ourselves
        """
        # Skip if no callback is set
        if not self.message_callback:
            logger.warning("No message callback set, ignoring message")
            return None
        
        try:
            # Extract message info
            text = message.get('text', '')
            from_id = message.get('from_id', 'unknown')
            to_id = message.get('to_id', 'broadcast')
            is_direct = message.get('is_direct', False)
            is_llm_channel = message.get('is_llm_channel', False)
            
            logger.info(f"Processing message from {from_id}: {text[:50]}...")
            
            # Generate response using callback
            response = self.message_callback(message)
            
            # Skip empty responses
            if not response:
                logger.warning("Empty response from callback")
                return None
            
            logger.info(f"Generated response: {response[:50]}...")
            
            # Send response through TCP client instead of MQTT
            self._send_response_via_tcp(response, from_id, to_id, is_direct, is_llm_channel)
            
            # Return None to prevent MQTT client from sending a response
            return None
            
        except Exception as e:
            logger.error(f"Error handling MQTT message: {str(e)}")
            return None
    
    def _send_response_via_tcp(
        self, 
        response: str, 
        from_id: str, 
        to_id: str,
        is_direct: bool,
        is_llm_channel: bool
    ):
        """
        Send response via TCP client
        
        Args:
            response: Response text
            from_id: Original sender ID
            to_id: Original recipient ID
            is_direct: Whether the original message was direct
            is_llm_channel: Whether the original message was from LLM channel
        """
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                # Determine if this should be a direct message
                # In private mode or if original message was direct, respond directly
                if self.private_mode or is_direct:
                    logger.info(f"Sending direct TCP response to {from_id}")
                    success = self.tcp_client.send_message(response, from_id)
                else:
                    logger.info("Sending broadcast TCP response")
                    success = self.tcp_client.send_message(response)
                    
                if success:
                    logger.info(f"TCP response sent successfully: {response[:50]}...")
                elif attempt < max_retries:
                    logger.warning(f"Failed to send TCP response, retrying (attempt {attempt+1}/{max_retries})...")
                    continue
                else:
                    logger.error("Failed to send TCP response after all retries")
                
                # Also send to LLM response channel if this was an LLM channel message
                if is_llm_channel and self.use_llm_channel:
                    # Extract channel name from the full path
                    if self.llm_response_channel:
                        # Get the actual channel name (usually the last non-empty part)
                        llm_channel_parts = self.llm_response_channel.split('/')
                        # Filter out empty parts and get the last meaningful part (usually the channel name)
                        non_empty_parts = [part for part in llm_channel_parts if part]
                        if non_empty_parts:
                            channel_name = non_empty_parts[-1]  # Take the last non-empty part
                        else:
                            channel_name = "llmres"  # Default fallback
                        
                        logger.info(f"Sending response to LLM response channel via TCP: {channel_name}")
                        
                        # Use the TCP client to send to the specific channel
                        channel_success = self.tcp_client.send_to_channel(response, channel_name)
                        
                        if channel_success:
                            logger.info(f"Successfully sent response to LLM channel: {response[:50]}...")
                            # We're done if both sends succeeded
                            return
                        else:
                            logger.error(f"Failed to send response to LLM channel, falling back to MQTT")
                            
                            # Fallback to MQTT if TCP channel send failed
                            self._send_response_via_mqtt_llm_channel(response, from_id)
                    else:
                        logger.warning("LLM response channel not configured")
                
                # If we got here, we either succeeded or exhausted all retries
                return
                
            except Exception as e:
                logger.error(f"Error sending response (attempt {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries:
                    logger.info(f"Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    # Try MQTT as last resort
                    logger.error("Exhausted all TCP retries, falling back to MQTT")
                    if is_llm_channel and self.use_llm_channel:
                        self._send_response_via_mqtt_llm_channel(response, from_id)
    
    def _send_response_via_mqtt_llm_channel(self, response, from_id):
        """
        Send response via MQTT to the LLM response channel
        
        Args:
            response: Response text
            from_id: Original sender ID
        """
        try:
            # Format as JSON for LLM channel
            response_data = {
                "from": self.tcp_client.my_node_id_num if hasattr(self.tcp_client, 'my_node_id_num') else 1234567890,
                "type": "sendtext",
                "payload": {
                    "text": response,
                    "from_id": self.tcp_client.my_node_id if hasattr(self.tcp_client, 'my_node_id') else "llm_agent",
                    "to_id": from_id if self.private_mode else "broadcast",
                    "is_response": True
                }
            }
            
            # Use MQTT client as fallback
            success = self.mqtt_client.publish_to_llm_response_channel(response_data)
            if success:
                logger.info(f"Successfully published response to LLM response channel via MQTT")
            else:
                logger.error(f"Failed to publish response to LLM response channel via MQTT")
        except Exception as e:
            logger.error(f"Error publishing to LLM response channel: {str(e)}")
    
    def set_message_callback(self, callback: Callable[[Dict[str, Any]], Optional[str]]):
        """
        Set callback for processing messages
        
        Args:
            callback: Function that takes a message dict and returns a response string or None
        """
        self.message_callback = callback
    
    def request_node_info(self):
        """
        Request node information from both clients
        """
        self.mqtt_client.request_node_info()
        # TCP client automatically gets node info on connect
    
    def send_startup_messages(self):
        """
        Send startup messages on both interfaces
        """
        startup_message = "📢 LLM Agent is now online and ready for conversations!"
        if self.private_mode:
            startup_message += " (Private mode: only responding to direct messages)"
        if self.use_llm_channel:
            startup_message += f" (Listening on channel: {self.llm_channel})"
        
        # Send via TCP
        self.tcp_client.send_message(startup_message)
        logger.info(f"Sent startup message via TCP: {startup_message}")
        
        # Also send to LLM channel if enabled
        if self.use_llm_channel:
            # Format as JSON for LLM channel
            startup_data = {
                "from": 1234567890,  # Placeholder ID for LLM agent
                "type": "sendtext",
                "payload": {
                    "text": startup_message,
                    "from_id": "llm_agent",
                    "to_id": "broadcast"
                }
            }
            # Still use MQTT to publish to the LLM channel, as TCP can't publish there
            self.mqtt_client.send_to_llm_channel(startup_data)
            logger.info(f"Sent startup message to LLM channel: {startup_message}")
    
    def send_message(self, text: str, to_id: str = None) -> bool:
        """
        Send a message using the TCP client
        
        Args:
            text: Text message to send
            to_id: Node ID to send to, or None for broadcast
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        return self.tcp_client.send_message(text, to_id)
