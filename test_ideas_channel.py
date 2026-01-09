"""Test fetching messages from #ideas channel."""

import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
IDEAS_CHANNEL_ID = "CGREG0X9A"

client = WebClient(token=BOT_TOKEN)

print("📬 Fetching messages from #ideas channel...\n")

try:
    response = client.conversations_history(
        channel=IDEAS_CHANNEL_ID,
        limit=20
    )
    
    messages = response["messages"]
    print(f"✅ Successfully fetched {len(messages)} messages from #ideas!\n")
    
    if messages:
        print("=" * 80)
        for i, msg in enumerate(messages, 1):
            user = msg.get("user", "System/Bot")
            text = msg.get("text", "[No text]")
            ts = msg.get("ts", "")
            msg_type = msg.get("type", "message")
            subtype = msg.get("subtype", "normal")
            
            print(f"\nMessage {i}/{len(messages)}:")
            print(f"  User ID: {user}")
            print(f"  Timestamp: {ts}")
            print(f"  Type: {msg_type} ({subtype})")
            print(f"  Text: {text}")
            print("-" * 80)
            
        print(f"\n🎉 Successfully read {len(messages)} messages from #ideas channel!")
        print("\n✅ Your Slack connector can now:")
        print("   - Fetch message history")
        print("   - Index messages for search")
        print("   - Enable semantic search across Slack")
        
    else:
        print("ℹ️  #ideas channel exists but has no messages yet")
        print("   Try sending a message in the channel and run this again!")
        
except SlackApiError as e:
    error_code = e.response["error"]
    if error_code == "not_in_channel":
        print(f"❌ Bot is not in the #ideas channel")
        print(f"   Please invite @contextdock to #ideas:")
        print(f"   1. Open #ideas in Slack")
        print(f"   2. Type: /invite @contextdock")
        print(f"   3. Run this script again")
    else:
        print(f"❌ Slack API Error: {error_code}")
        print(f"   Response: {e.response}")
        
except Exception as e:
    print(f"❌ Unexpected error: {str(e)}")
    import traceback
    traceback.print_exc()
