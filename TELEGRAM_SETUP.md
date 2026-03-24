# Telegram Publishing Setup

This guide explains how to configure and test Telegram publishing for Jarvis v2 Core.

## Configuration

1. **Edit `config/settings.json`** and add the `delivery` section:

```json
{
  "delivery": {
    "telegram_target": "chat"
  }
}
```

2. **Supported target formats:**
   - `@username` - Telegram username or channel handle
   - `Chat Title` - Partial or full chat title (case-insensitive)
   - `123456789` - Numeric chat ID (most reliable)

## Finding Your Target

### Method 1: Use the dialog listing utility
```bash
python list_telegram_dialogs.py
```

This will show all available chats/channels with their titles, usernames, and IDs.

### Method 2: Manual lookup
- Open Telegram
- Go to the chat/channel you want to use
- The target can be:
  - The username (e.g., `@mychannel`)
  - The chat title (e.g., `My Group Chat`)
  - The numeric ID (use the listing utility to find this)

## Testing

After configuring your target, test the publishing:

```bash
python test_telegram_publish.py
```

This will send a test digest to verify the configuration works.

## How It Works

1. **Entity Resolution**: Jarvis tries multiple methods to resolve your target:
   - Direct username/ID lookup
   - Numeric ID conversion
   - Title-based search (partial matching)

2. **Error Handling**: 
   - Clear error messages if target can't be resolved
   - No silent fallbacks to Saved Messages
   - Detailed logging for debugging

3. **Reliability**:
   - Messages are split if too long (Telegram limit: 4096 chars)
   - Local backup saved to `data/digests/`
   - Console fallback if publishing fails

## Troubleshooting

### Target not found
- Run `python list_telegram_dialogs.py` to verify the exact target
- Use numeric ID for most reliable resolution
- Ensure Jarvis account has access to the target chat

### Permission errors
- Make sure Jarvis account is a member/admin of the target
- Check that the target allows messages from bots

### Network issues
- Verify internet connection
- Check Telegram API credentials in config
- Look at logs in `data/logs/jarvis.log` for detailed errors
