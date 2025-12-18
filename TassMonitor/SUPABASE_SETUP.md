# Supabase Setup for Dynamic Keywords

This guide explains how to set up Supabase for storing and managing alert keywords dynamically.

## Prerequisites

1. A Supabase account (sign up at https://supabase.com)
2. A Supabase project created

## Step 1: Create the Table

In your Supabase project, go to the SQL Editor and run the following SQL:

```sql
-- Create the alert_keywords table
CREATE TABLE IF NOT EXISTS alert_keywords (
    id BIGSERIAL PRIMARY KEY,
    keywords JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create an index on updated_at for faster queries
CREATE INDEX IF NOT EXISTS idx_alert_keywords_updated_at ON alert_keywords(updated_at DESC);

-- Optional: Add a comment
COMMENT ON TABLE alert_keywords IS 'Stores alert keywords for @everyone tagging in Discord';
```

## Step 2: Set Up Environment Variables

Add the following to your `.env` file (in the project root):

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# Discord Bot Token (for !poly commands)
DISCORD_BOT_TOKEN=your-discord-bot-token
```

### Getting Your Supabase Credentials

1. Go to your Supabase project dashboard
2. Click on "Settings" → "API"
3. Copy the "Project URL" → This is your `SUPABASE_URL`
4. Copy the "anon public" key → This is your `SUPABASE_KEY`

### Getting Your Discord Bot Token

1. Go to https://discord.com/developers/applications
2. Create a new application or select an existing one
3. Go to "Bot" section
4. Click "Reset Token" or copy existing token → This is your `DISCORD_BOT_TOKEN`
5. Enable "Message Content Intent" under "Privileged Gateway Intents"
6. Invite the bot to your server with the following permissions:
   - Send Messages
   - Read Message History
   - Attach Files (for reading .txt files)

## Step 3: Initial Keywords (Optional)

You can insert initial keywords using the SQL Editor:

```sql
INSERT INTO alert_keywords (keywords) VALUES (
    '["strike", "strikes", "striking", "struck", "airstrike", "airstrikes", "air strike", "air strikes", "attack", "attacks", "attacked", "attacking", "casualties", "casualty", "killed", "killing", "deaths", "dead", "wounded", "injured", "injuries", "bombing", "bombed", "bomb", "bombs", "missile", "missiles", "rocket", "rockets", "raid", "raids", "raided", "shelling", "shelled", "shell", "targeted", "targeting", "target", "explosion", "explosions", "exploded", "explode", "martyr", "martyrs", "martyred", "gaza", "lebanon", "lebanese"]'::jsonb
);
```

Or simply use the Discord bot command `!poly setkeywords` with a .txt file after setup.

## Usage

Once set up, you can manage keywords via Discord commands:

- `!poly setkeywords` - Attach a .txt file with keywords (one per line) to update the keyword list
- `!poly listkeywords` - Show the current list of keywords
- `!poly help` - Show help message

### Example .txt File Format

Create a file `keywords.txt`:

```
strike
strikes
airstrike
attack
casualties
killed
bombing
missile
# This is a comment (ignored)
gaza
lebanon
```

Then use `!poly setkeywords` and attach this file in Discord.

## Notes

- Keywords are case-insensitive when matching
- The system checks both original and translated text for keywords
- When keywords are updated, the new list is used immediately for all future messages
- If Supabase is not configured, the system falls back to default keywords

