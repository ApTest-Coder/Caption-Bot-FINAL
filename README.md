# Caption Bot

Advanced Telegram Auto Caption Bot with a clean button-based UI.

## Features

- Multi-channel support; each channel has independent settings
- Add channel by ID or by forwarding a channel message in bot DM
- Caption templates with dynamic variables
- Episode/season/quality/audio fallback rules
- HTML formatting including `<blockquote expandable>`
- Colored buttons: blue, green, red
- Text replacement, filters, forwarding, prefix, suffix, stickers, media details
- Public/private mode
- Public-link-only force subscribe; no generated invite links
- Broadcast, user tracking and statistics
- Lightweight MongoDB primary backend with optional SQLite backend
- Docker support
- Owner/admin-only management commands
- Unexpected errors are sent to the owner/admin DM; missing metadata does not stop processing

## Public mode

`PUBLIC_MODE=true` lets normal users use the bot. Admin-only commands remain protected.

`PUBLIC_MODE=false` shows exactly:

```text
🔒 This Bot Is Private

Please contact the administrator. @ApxCoder
```

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in `BOT_TOKEN`, `OWNER_ID` and your database values. Every other setting
   has a working default.
3. Install dependencies: `pip install -r requirements.txt`.
4. Run: `python main.py`.

`main.py` validates the configuration before it connects to anything and exits
with a list of exactly what is missing, so a typo fails immediately and loudly
instead of surfacing as a confusing Telegram error later.

`DATABASE_TYPE` defaults to `sqlite`, which needs no external service. Set it to
`mongodb` and provide `MONGO_URI` to use MongoDB instead.

### Migrating from an older release

Earlier releases were configured by editing credentials straight into
`config.py`. **That no longer works, on purpose.** `config.py` is a tracked
source file, so editing secrets into it puts your bot token one `git commit -a`
away from being published. Configuration now comes from the environment (or a
local `.env`, which is git-ignored).

To migrate, copy each value from your old `config.py` into `.env` using the same
names, then restore the tracked `config.py` from this repository.

## Images

Put your own `start.jpg` and `fsub.jpg` inside `assets/`. The bot safely falls back to a text message if an image is not present.

## Commands

Public: `/start`, `/help`, `/channels`, `/stats`, `/settings`

Admin: `/addadmin`, `/deladmin`, `/broadcast`, `/set_public`

`/addadmin` and `/deladmin` are restricted to `OWNER_ID`; the owner account
cannot be demoted.

Channel configuration is intentionally handled through the inline UI rather than a long list of commands.

## Security

Do not commit real credentials. Secrets belong in `.env`, which `.gitignore`
excludes; `.env.example` holds placeholders only. CI fails the build if a value
shaped like a Telegram bot token, or a tracked `.env`, appears in the repository.

Adding a channel requires that **you** are an administrator of that channel, not
merely that the bot is. Without that check, anyone who knew a channel ID could
claim a channel the bot administered and rewrite its captions and buttons.

