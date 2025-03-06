#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import signal
import time
import torch

from model_loader import ModelLoader
from meshtastic_hybrid_client import MeshtasticHybridClient
from agent import Agent
import config

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("lora_llm.log")
    ]
)
logger = logging.getLogger(__name__)

# Global agent for signal handling
agent = None

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info("Shutdown signal received")
    if agent:
        logger.info("Shutting down agent")
        agent.shutdown()
    sys.exit(0)

def parse_args():
    parser = argparse.ArgumentParser(description="LLM Meshtastic Agent")
    parser.add_argument("--model", type=str, help="Model ID or path")
    parser.add_argument("--mqtt-host", type=str, help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, help="MQTT broker port (default: 1883)")
    parser.add_argument("--mqtt-username", type=str, help="MQTT username for authentication")
    parser.add_argument("--mqtt-password", type=str, help="MQTT password for authentication")
    parser.add_argument("--tcp-host", type=str, help="Meshtastic TCP interface host")
    parser.add_argument("--tcp-port", type=int, help="Meshtastic TCP interface port (default: 4403)")
    parser.add_argument("--private", action="store_true", help="Only respond to direct messages")
    parser.add_argument("--broadcast", action="store_true", help="Respond to all messages (overrides private)")
    parser.add_argument("--startup-message", action="store_true", help="Send a startup message when the agent starts")
    parser.add_argument("--no-startup-message", action="store_true", help="Don't send a startup message when the agent starts")
    parser.add_argument("--gguf", action="store_true", help="Use GGUF model format (requires local model path)")
    parser.add_argument("--cpu-only", action="store_true", help="Use CPU for inference only")
    parser.add_argument("--use-llm-channel", action="store_true", help="Use a dedicated LLM channel")
    parser.add_argument("--no-llm-channel", action="store_true", help="Don't use a dedicated LLM channel")
    parser.add_argument("--llm-channel", type=str, help="Dedicated channel for LLM messages")
    parser.add_argument("--llm-response-channel", type=str, help="Channel for LLM responses")
    return parser.parse_args()

def main():
    """
    Main function
    """
    # Parse command line arguments
    args = parse_args()
    
    # Update configuration from command line arguments
    if args.model:
        config.MODEL_ID = args.model
    if args.mqtt_host:
        config.MQTT_BROKER = args.mqtt_host
    if args.mqtt_port:
        config.MQTT_PORT = args.mqtt_port
    if args.mqtt_username:
        config.MQTT_USERNAME = args.mqtt_username
    if args.mqtt_password:
        config.MQTT_PASSWORD = args.mqtt_password
    if args.tcp_host:
        config.MESHTASTIC_IP = args.tcp_host
    if args.tcp_port:
        config.MESHTASTIC_PORT = args.tcp_port
    
    # Set private mode
    if args.private:
        config.PRIVATE_MODE = True
    elif args.broadcast:
        config.PRIVATE_MODE = False
    
    # Set startup message
    if args.startup_message:
        config.SEND_STARTUP_MESSAGE = True
    elif args.no_startup_message:
        config.SEND_STARTUP_MESSAGE = False
    
    # Set GGUF mode
    if args.gguf:
        config.USE_GGUF = True
    
    # Set LLM channel options
    if args.use_llm_channel:
        config.USE_LLM_CHANNEL = True
    elif args.no_llm_channel:
        config.USE_LLM_CHANNEL = False
    
    if args.llm_channel:
        config.LLM_CHANNEL = args.llm_channel
    
    if args.llm_response_channel:
        config.LLM_RESPONSE_CHANNEL = args.llm_response_channel
    
    # Set device
    device = "cpu" if args.cpu_only else "cuda" if torch.cuda.is_available() else "cpu"
    
    # Print configuration
    logger.info("Starting LLM Meshtastic Agent with Hybrid Messaging")
    logger.info(f"Model: {config.MODEL_ID}")
    logger.info(f"MQTT Broker (for receiving): {config.MQTT_BROKER}")
    logger.info(f"MQTT Port: {config.MQTT_PORT}")
    logger.info(f"TCP Host (for sending): {config.MESHTASTIC_IP}")
    logger.info(f"TCP Port: {config.MESHTASTIC_PORT}")
    logger.info(f"Private Mode: {config.PRIVATE_MODE}")
    logger.info(f"Device: {device}")
    logger.info(f"Using GGUF: {config.USE_GGUF}")
    logger.info(f"Send Startup Message: {config.SEND_STARTUP_MESSAGE}")
    logger.info(f"Use LLM Channel: {config.USE_LLM_CHANNEL}")
    logger.info(f"LLM Channel: {config.LLM_CHANNEL}")
    logger.info(f"LLM Response Channel: {config.LLM_RESPONSE_CHANNEL}")
    
    # Initialize model loader
    logger.info("Initializing model loader")
    model_loader = ModelLoader(
        model_id=config.MODEL_ID,
        local_path=config.MODEL_LOCAL_PATH,
        use_gguf=config.USE_GGUF,
        device=device
    )
    
    # Load model
    if not model_loader.load_model():
        logger.error("Failed to load model")
        return 1
    
    # Initialize Meshtastic Hybrid client
    logger.info("Initializing Meshtastic Hybrid client")
    meshtastic_client = MeshtasticHybridClient(
        # MQTT params (for receiving)
        mqtt_broker=config.MQTT_BROKER,
        mqtt_port=config.MQTT_PORT,
        mqtt_username=config.MQTT_USERNAME,
        mqtt_password=config.MQTT_PASSWORD,
        use_llm_channel=config.USE_LLM_CHANNEL,
        llm_channel=config.LLM_CHANNEL,
        llm_response_channel=config.LLM_RESPONSE_CHANNEL,
        # TCP params (for sending)
        tcp_host=config.MESHTASTIC_IP,
        tcp_port=config.MESHTASTIC_PORT,
        # Common params
        private_mode=config.PRIVATE_MODE,
        send_startup_message=config.SEND_STARTUP_MESSAGE
    )
    
    # Initialize agent
    logger.info("Initializing agent")
    global agent
    agent = Agent(
        model_loader=model_loader,
        meshtastic_client=meshtastic_client,
        system_prompt=config.SYSTEM_PROMPT,
        max_conversation_length=10
    )
    
    # Set message callback
    meshtastic_client.set_message_callback(agent.process_message)
    
    # Connect to both interfaces
    if not meshtastic_client.connect():
        logger.error("Failed to connect to Meshtastic interfaces")
        return 1
    
    # Request node information
    logger.info("Requesting node information")
    meshtastic_client.request_node_info()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run until interrupted
    try:
        logger.info("Agent is running. Press Ctrl+C to exit.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
        if agent:
            agent.shutdown()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
