# Model configuration
MODEL_ID = "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
MODEL_LOCAL_PATH = "./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"  # Set this if using a local model instead
USE_GGUF = True  # Set to True if loading a GGUF model file
MAX_NEW_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.9

# Meshtastic configuration
MESHTASTIC_IP = "10.0.0.213"
MESHTASTIC_PORT = 4403  # Default Meshtastic TCP port
MESHTASTIC_HTTP_PORT = 8080  # Default Meshtastic HTTP port
PRIVATE_MODE = False  # If True, only respond to direct messages

# MQTT configuration
MQTT_BROKER = "10.0.0.159"  # Same as Meshtastic IP by default
MQTT_PORT = 1883  # Default MQTT port
MQTT_USERNAME = "something"  # Set if your broker requires authentication
MQTT_PASSWORD = "something"  # Set if your broker requires authentication
SEND_STARTUP_MESSAGE = False  # If True, broadcast a message when the agent starts up
USE_LLM_CHANNEL = True  # If True, use a dedicated LLM channel for processing messages
# Format: msh/[region]/[channel_index]/json/[channel_name]
# For a channel named "llm" that is the secondary channel (index 1)
# The JSON format is required for proper Meshtastic channel integration
LLM_CHANNEL = "msh/US/2/json/llm/"  # Dedicated channel for LLM messages
LLM_RESPONSE_CHANNEL = "msh/US/2/json/llmres/"  # Channel for LLM responses (different from LLM_CHANNEL)

# System prompt for the conversational agent
SYSTEM_PROMPT = """You are a helpful AI assistant connected via Meshtastic mesh network.
You can communicate with users over long distances even without internet connectivity.
Keep your responses concise as they need to be transmitted over a low-bandwidth network.
"""
