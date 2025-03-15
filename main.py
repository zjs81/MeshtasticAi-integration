import time
import meshtastic
import meshtastic.tcp_interface
from pubsub import pub
import requests

# Maximum allowed payload size in bytes (conservative value)
MAX_PAYLOAD_BYTES = 200
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Global dictionary to store conversation history per user (keyed by sender id)
conversation_histories = {}

# Instructions message to be sent as a welcome/help message
INSTRUCTIONS = (
    "Welcome to the AI Chat!\n"
    "Available commands:\n"
    " - /ai [your question] : ask a question\n"
    " - /ai /clear         : clear your conversation history"
)

def get_ai_response(prompt):
    """
    Call the Ollama API with the provided prompt.
    If the response (UTF-8 encoded) exceeds MAX_PAYLOAD_BYTES, reprompt for a shorter answer.
    """
    payload = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "stream": False
    }
    response = requests.post(OLLAMA_API_URL, json=payload)
    if response.status_code == 200:
        data = response.json().get("response", "").strip()
        if len(data.encode('utf-8')) > MAX_PAYLOAD_BYTES:
            new_prompt = prompt + "\n(Please provide a shorter response within 200 characters.)"
            retry_payload = {**payload, "prompt": new_prompt}
            retry_response = requests.post(OLLAMA_API_URL, json=retry_payload)
            if retry_response.status_code == 200:
                return retry_response.json().get("response", "").strip()
            else:
                return "Error: AI response failed."
        return data
    else:
        return f"Error: AI request failed with {response.status_code}"

def split_message(text, max_bytes=MAX_PAYLOAD_BYTES):
    """
    Splits text into chunks where each chunk's UTF-8 byte length does not exceed max_bytes.
    Splits on word boundaries when possible.
    """
    words = text.split()
    parts = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate.encode('utf-8')) > max_bytes:
            if current:
                parts.append(current)
                current = word
            else:
                for i in range(0, len(word), max_bytes):
                    parts.append(word[i:i+max_bytes])
                current = ""
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts

def on_receive(packet, interface):
    """
    Callback invoked when a packet is received.
    Processes messages starting with "/ai":
      - "/ai /clear" clears the user's context and sends instructions.
      - Otherwise, builds a context-aware prompt from the user's conversation history.
    """
    print("Received packet:", packet)  
    try:
        text = packet.get('decoded', {}).get('text', "")
        sender_id = packet.get('fromId', '')
        
        if not text.startswith("/ai"):
            return
        #!55c64ce8 my node
        if (sender_id != "!55c64ce8"): # CHANGE THIS TO YOUR NODE!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            print("id is " + sender_id)
            return

        # Remove the command /ai and trim whitespace
        query = text[3:].strip()

        # Chec for the clear command
        if query.lower() == "/clear":
            conversation_histories[sender_id] = []
            interface.sendText("Conversation context cleared.\n" + INSTRUCTIONS, destinationId=sender_id)
            return

        # retrieve or create conversation history for this sender
        history = conversation_histories.get(sender_id, [])
        # if history is empty, send the instructions as a welcome message
        if not history:
            interface.sendText(INSTRUCTIONS, destinationId=sender_id)
            history = []
        

        # Limit history length to last 20 entries to prevent context overflow
        if len(history) > 20:
            history = history[-20:]
        
        # Build the full prompt with history and new query
        context_str = "\n".join(history)
        full_prompt = f"{context_str}\nUser: {query}\nAssistant:"
        
        # Get the AI response
        ai_response = get_ai_response(full_prompt)
        print("AI response:", ai_response, "Bytes:", len(ai_response.encode('utf-8')))
        
        # Split the response if it's too long
        if len(ai_response.encode('utf-8')) > MAX_PAYLOAD_BYTES:
            parts = split_message(ai_response, MAX_PAYLOAD_BYTES)
        else:
            parts = [ai_response]

        # Update conversation history with the new query and response
        history.append(f"User: {query}")
        combined_response = " ".join(parts)
        history.append(f"Assistant: {combined_response}")
        conversation_histories[sender_id] = history

        # Send each part back to the sender
        for part in parts:
            print("Sending part:", part, "Bytes:", len(part.encode('utf-8')))
            interface.sendText(part, destinationId=sender_id)
            time.sleep(1)
    except Exception as e:
        print(f"Error processing message: {e}")

# Subscribe to all received messages from the mesh network
pub.subscribe(on_receive, "meshtastic.receive")

# Connect to the Meshtastic device over TCP (WiFi) using TCPInterface.
# Adjust the host and port as needed.
interface = meshtastic.tcp_interface.TCPInterface("192.168.0.6", 50080)

print("Connected to Meshtastic device over TCP/WiFi. Listening for messages...")
while True:
    time.sleep(1)
