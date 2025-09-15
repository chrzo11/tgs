
import json
import logging
import re
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError

# Suppress ALL logging except our messages
import sys
import os

# Redirect stderr to suppress all error messages
sys.stderr = open(os.devnull, 'w')

# Configure logging - only show our messages
logging.basicConfig(
    format='%(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress all other loggers
logging.getLogger('pyrogram').setLevel(logging.CRITICAL)
logging.getLogger('asyncio').setLevel(logging.CRITICAL)
logging.getLogger('httpx').setLevel(logging.CRITICAL)
logging.getLogger('pymongo').setLevel(logging.CRITICAL)

# Telegram API Configuration
API_ID = 22631192
API_HASH = "d63ae360ab4697a261dcb7ffa2ff3cae"
PHONE_NUMBER = "+918334041071"  # Your phone number with country code

# Target group ID (where device verification messages will be sent)
TARGET_GROUP_ID = -1002704970947

# MongoDB Configuration
MONGODB_CONNECTION_STRING = "mongodb+srv://rharishkumar9566_db_user:k2sFE1SaSZ5sujFp@cluster0.xl7biy2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DATABASE_NAME = "fix11"
COLLECTION_NAME = "device_verifications"

# MongoDB client
client = None
db = None
collection = None

def connect_to_mongodb():
    """Connect to MongoDB and initialize database and collection."""
    global client, db, collection
    try:
        client = MongoClient(MONGODB_CONNECTION_STRING)
        # Test the connection
        client.admin.command('ping')
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        
        # Create a unique index on chat_id to prevent duplicates.
        # This should align with the existing index causing the error.
        collection.create_index("chat_id", unique=True)
        collection.create_index("verified_at")
        
        logger.info("Successfully connected to MongoDB")
        return True
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return False

def extract_json_from_message(text: str) -> dict:
    """Extract JSON data from the message text."""
    try:
        # Look for JSON data between "JSON Data:" and the end of the message
        json_match = re.search(r'JSON Data:\s*\n?(\{.*\})', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            return json.loads(json_str)
        
        # Alternative: look for any JSON object in the message
        json_match = re.search(r'(\{[^{}]*"action"[^{}]*\})', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            return json.loads(json_str)
            
        return None
    except json.JSONDecodeError as e:
        return None
    except Exception as e:
        return None

# Create Pyrogram client
app = Client(
    "device_verification_monitor",
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE_NUMBER
)

@app.on_message(filters.chat(TARGET_GROUP_ID) & filters.text)
async def handle_group_message(client, message: Message):
    """Handle messages only from the target group."""
    message_text = message.text
    chat_id = message.chat.id
    from_user = message.from_user.first_name if message.from_user else "Unknown"
    
    # Check if message contains device verification data
    if "🔐 Device Verification Data" in message_text:
        print("🔐 DEVICE VERIFICATION DETECTED!")
        
        # Extract JSON data
        json_data = extract_json_from_message(message_text)
        
        if json_data:
            try:
                # Get chatid from JSON data (the original key)
                chatid_val = json_data.get("chatid")
                
                # Skip if chatid is null, empty, or None
                if not chatid_val:
                    print("⚠️ SKIPPING - No valid chatid found in JSON data")
                    print(f"   JSON data: {json_data}")
                    print("─" * 50)
                    return
                
                # Check for duplicate chat_id before saving (using the correct DB field name)
                existing_doc = collection.find_one({"chat_id": chatid_val})
                if existing_doc:
                    print("⚠️ DUPLICATE CHAT ID - Already exists in database")
                    print(f"   Chat ID: {chatid_val}")
                    print(f"   Previous save: {existing_doc.get('saved_at', 'N/A')}")
                    print("─" * 50)
                    return
                
                # Add timestamp when saved to database
                json_data["saved_at"] = datetime.now(timezone.utc).isoformat()
                json_data["group_id"] = str(chat_id)  # Add group ID to the data
                
                # IMPORTANT: Align the key with the database schema before insertion
                if 'chatid' in json_data:
                    json_data['chat_id'] = json_data.pop('chatid')
                
                # Save to MongoDB
                result = collection.insert_one(json_data)
                print(f"✅ SAVED TO MONGODB: {result.inserted_id}")
                print(f"   Chat ID: {chatid_val}")
                print(f"   IP: {json_data.get('ipaddress', 'N/A')}")
                print(f"   Time: {json_data.get('verifiedat', 'N/A')}")
                print("─" * 50)
                
            except Exception as e:
                print(f"❌ ERROR: {e}")
        else:
            print("❌ INVALID JSON DATA")

@app.on_message(filters.private & filters.text)
async def handle_private_message(client, message: Message):
    """Handle private messages."""
    message_text = message.text
    chat_id = message.chat.id
    from_user = message.from_user.first_name if message.from_user else "Unknown"
    
    logger.info(f"📨 PRIVATE MESSAGE RECEIVED:")
    logger.info(f"   Chat ID: {chat_id}")
    logger.info(f"   From: {from_user}")
    logger.info(f"   Text: {message_text}")
    
    if message_text.startswith("/start"):
        await message.reply(
            f"🤖 Device Verification Monitor is running!\n"
            f"Monitoring group: {TARGET_GROUP_ID}\n"
            f"Your Chat ID: {chat_id}"
        )
    elif message_text.startswith("/status"):
        try:
            count = collection.count_documents({})
            await message.reply(
                f"📊 Status Report:\n"
                f"✅ MongoDB Connected: Yes\n"
                f"📈 Total documents saved: {count}\n"
                f"🎯 Monitoring group: {TARGET_GROUP_ID}"
            )
        except Exception as e:
            await message.reply(f"❌ Error getting status: {str(e)}")
    else:
        await message.reply(
            f"Bot received: {message_text[:100]}...\n\n"
            f"Commands:\n"
            f"/start - Show bot info\n"
            f"/status - Show database status"
        )

def main():
    """Start the client."""
    # Connect to MongoDB
    if not connect_to_mongodb():
        print("❌ Failed to connect to MongoDB. Exiting.")
        return
    
    print("🚀 DEVICE VERIFICATION MONITOR STARTED")
    print(f"📱 Monitoring group: {TARGET_GROUP_ID}")
    print("─" * 50)
    
    try:
        # Start the client
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Client stopped by user")
    except Exception as e:
        print(f"❌ Client error: {e}")
        print("🔄 Restarting in 5 seconds...")
        import time
        time.sleep(5)
        main()

if __name__ == '__main__':
    main()




