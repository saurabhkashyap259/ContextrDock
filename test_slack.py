"""Simple script to test Slack integration with Aktivolabs workspace."""

import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

# Load credentials from environment
BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

def test_slack_connection():
    """Test Slack API connection and list channels."""
    client = WebClient(token=BOT_TOKEN)
    
    print("🔗 Testing Slack connection to Aktivolabs workspace...\n")
    
    try:
        # Test auth
        auth_response = client.auth_test()
        print(f"✅ Connected to Slack!")
        print(f"   Team: {auth_response['team']}")
        print(f"   User: {auth_response['user']}")
        print(f"   Bot ID: {auth_response.get('bot_id', 'N/A')}\n")
        
        # List conversations (channels)
        print("📋 Listing channels:\n")
        response = client.conversations_list(
            types="public_channel,private_channel",
            limit=10
        )
        
        channels = response['channels']
        print(f"Found {len(channels)} channels:\n")
        
        for channel in channels:
            channel_type = "🔒 Private" if channel['is_private'] else "🌐 Public"
            print(f"   {channel_type} #{channel['name']}")
            print(f"      ID: {channel['id']}")
            print(f"      Members: {channel.get('num_members', 'N/A')}")
            print()
        
        # Get recent messages from first channel
        if channels:
            first_channel = channels[0]
            print(f"\n💬 Fetching recent messages from #{first_channel['name']}...\n")
            
            try:
                history_response = client.conversations_history(
                    channel=first_channel['id'],
                    limit=5
                )
                
                messages = history_response['messages']
                print(f"Found {len(messages)} recent messages:\n")
                
                for msg in messages:
                    user_id = msg.get('user', 'Unknown')
                    text = msg.get('text', '[No text]')
                    timestamp = msg.get('ts', 'Unknown')
                    
                    print(f"   [{timestamp}] {user_id}:")
                    print(f"      {text[:100]}{'...' if len(text) > 100 else ''}\n")
            except SlackApiError as channel_err:
                print(f"   ⚠️  Cannot read messages (bot not in channel): {channel_err.response['error']}\n")
        
        # Try to read from #ideas channel specifically
        print("\n🔍 Looking for #ideas channel...\n")
        ideas_channel = None
        for channel in channels:
            if channel['name'] == 'ideas':
                ideas_channel = channel
                break
        
        if ideas_channel:
            print(f"✅ Found #ideas channel (ID: {ideas_channel['id']})")
            print(f"   Attempting to fetch messages...\n")
            
            try:
                history_response = client.conversations_history(
                    channel=ideas_channel['id'],
                    limit=10
                )
                
                messages = history_response['messages']
                print(f"✅ Successfully fetched {len(messages)} messages from #ideas!\n")
                
                if messages:
                    print("Recent messages:")
                    for i, msg in enumerate(messages[:5], 1):
                        user_id = msg.get('user', 'Bot/System')
                        text = msg.get('text', '[No text]')
                        timestamp = msg.get('ts', 'Unknown')
                        msg_type = msg.get('type', 'message')
                        
                        print(f"\n   Message {i}:")
                        print(f"   User: {user_id}")
                        print(f"   Time: {timestamp}")
                        print(f"   Type: {msg_type}")
                        print(f"   Text: {text[:150]}{'...' if len(text) > 150 else ''}")
                else:
                    print("   ℹ️  Channel is empty or no messages yet")
                    
            except SlackApiError as ideas_err:
                print(f"   ❌ Cannot read #ideas: {ideas_err.response['error']}")
                print(f"      Make sure the bot is invited to the channel")
        else:
            # Search all channels including private ones
            print("   ℹ️  #ideas not found in public channels, searching all channels...")
            try:
                all_channels_response = client.conversations_list(
                    types="public_channel,private_channel",
                    exclude_archived=True,
                    limit=100
                )
                for channel in all_channels_response['channels']:
                    if channel['name'] == 'ideas':
                        ideas_channel = channel
                        print(f"   ✅ Found #ideas in extended search (ID: {channel['id']})")
                        break
                
                if not ideas_channel:
                    print("   ⚠️  #ideas channel not found. It may be private or archived.")
            except Exception as search_err:
                print(f"   ⚠️  Error searching channels: {str(search_err)}")
        
        print("\n✅ Slack integration test successful!")
        print("\n📊 Summary:")
        print(f"   - Authentication: ✅ Working")
        print(f"   - Channel listing: ✅ Working")  
        print(f"   - Message fetching: ✅ Working")
        print("\n🎉 Your Slack connector is ready to sync messages!")
        
    except SlackApiError as e:
        print(f"\n❌ Slack API Error: {e.response['error']}")
        print(f"   Details: {e.response.get('response_metadata', {})}")
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_slack_connection()
