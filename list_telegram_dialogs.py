#!/usr/bin/env python3
"""
Utility to list available Telegram dialogs for Jarvis configuration.

Run this script to see all available chats/channels and their IDs,
then update config/settings.json -> delivery.telegram_target with your desired target.
"""

import asyncio
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.digest.publisher import list_available_dialogs


async def main():
    """List available Telegram dialogs."""
    print("Fetching your Telegram dialogs...")
    print("This will help you choose the right target for delivery.telegram_target")
    print()
    
    try:
        await list_available_dialogs()
        print("\nUsage:")
        print("1. Choose a target from the list above")
        print("2. Update config/settings.json:")
        print('   "delivery": {')
        print('     "telegram_target": "@username"  # or "Chat Title" or "123456789"')
        print("   }")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure your Telegram API credentials are configured correctly in config/settings.json")


if __name__ == "__main__":
    asyncio.run(main())
