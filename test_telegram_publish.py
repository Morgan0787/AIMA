#!/usr/bin/env python3
"""
Test script for Telegram publishing functionality.

Run this script to test if Jarvis can send messages to your configured Telegram target.
"""

import asyncio
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.core.config import get_config
from app.digest.publisher import publish_digest


def main():
    """Test Telegram publishing with a sample digest."""
    print("Testing Telegram publishing...")
    
    config = get_config()
    target = config.delivery.telegram_target.strip()
    
    if not target:
        print("❌ No telegram_target configured in config/settings.json")
        print("Please set delivery.telegram_target to test publishing")
        return
    
    print(f"📤 Target: {target}")
    
    # Create a test digest
    test_digest = """🤖 Jarvis Test Digest

This is a test message from Jarvis v2 Core to verify Telegram publishing is working correctly.

If you receive this message, the configuration is correct and Jarvis can send digests to this chat.

Test items:
• Message collection: ✅
• AI analysis: ✅  
• Digest building: ✅
• Telegram publishing: 🔄

Sent at: {timestamp}
""".format(timestamp="2026-03-24 12:53:00 UTC")
    
    print("📝 Sending test digest...")
    
    try:
        published, published_to = publish_digest(test_digest, title="Jarvis Test Digest")
        
        if published:
            print(f"✅ Successfully sent test digest to: {published_to}")
        else:
            print("❌ Failed to send test digest")
            if published_to:
                print(f"   Attempted target: {published_to}")
            else:
                print("   No valid target configured")
                
    except Exception as e:
        print(f"❌ Error during test: {e}")


if __name__ == "__main__":
    main()
