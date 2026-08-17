# garmin-mcp

A local MCP server that exposes your Garmin Connect activity, health, and
training data (activities, HRV, sleep, heart rate, stress, body battery,
training readiness, HR/power zones, lactate threshold, FTP, VO2max,
personal records, workouts, scheduled workouts, and training plans) as
tools inside Claude Desktop.

It talks directly to the live Garmin Connect API via the
[`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
library. Data is read-only — nothing is ever written back to Garmin.

## How auth works

Garmin login happens in two separate places on purpose:

- **`scripts/setup_auth.py`** — an interactive script you run yourself in a
  terminal. It logs in with your email/password, prompts you for an MFA
  code if Garmin asks for one, and saves the resulting session token to
  `~/.garmin_mcp/tokens`.
- **The MCP server** (`src/garmin_mcp/server.py`), launched headlessly by
  Claude Desktop, only ever loads and silently refreshes that cached token.
  It never prompts for MFA — Claude Desktop gives it no terminal to prompt
  on, and blocking on stdin there would hang tool calls. If the cached
  session is missing or has expired, tool calls fail with an error telling
  you to re-run `setup_auth.py`.

Your Garmin password is stored in the macOS keychain (item/service
`garmin-mcp`, viewable in Keychain Access), never written to a file. Only
your Garmin login email (not secret) is saved, in `~/.garmin_mcp/config.json`.

## Setup

1. Install dependencies:

   ```bash
   cd garmin_mcp
   uv sync
   ```

2. Run the one-time interactive login:

   ```bash
   uv run python scripts/setup_auth.py
   ```

   Enter your Garmin Connect email and password (the password is then
   stored in the keychain for next time). Enter the MFA code when prompted.
   On success you'll see a confirmation and the token cache path.

3. Register the server with Claude Desktop by editing
   `~/Library/Application Support/Claude/claude_desktop_config.json` and
   adding (alongside any other `mcpServers` entries):

   ```json
   {
     "mcpServers": {
       "garmin": {
         "command": "uv",
         "args": ["run", "--project", "/absolute/path/to/garmin_mcp", "garmin-mcp"]
       }
     }
   }
   ```

4. Fully quit Claude Desktop (Cmd+Q, not just close the window) and reopen
   it. The tools/hammer icon should list the `garmin` tools.

## Tools

| Tool | Description |
| --- | --- |
| `list_activities` | Recent activities, most recent first (paginated, optional type filter) |
| `get_activity` | Full detail for one activity: summary + per-metric time series |
| `get_activity_splits` | Lap/split data for one activity |
| `get_heart_rate` | Daily resting HR + intraday HR timeline |
| `get_daily_stats` | Steps, calories, resting HR, distance, floors, intensity minutes |
| `get_sleep` | Sleep stages, duration, sleep score |
| `get_hrv` | Heart rate variability |
| `get_body_battery` | Body Battery energy reserve over a date range |
| `get_stress` | All-day stress level |
| `get_training_readiness` | Training Readiness score and contributing factors |
| `get_training_status` | Fitness trend, acute/chronic training load & ACWR, VO2max, and 4-week Load Focus breakdown |
| `get_profile` | Identity, unit prefs, personal settings (max HR, resting HR, weight, height, VO2max), HR zones and power zones per sport |
| `get_lactate_threshold` | Running lactate threshold: heart rate, power, and speed |
| `get_cycling_ftp` | Latest cycling Functional Threshold Power |
| `get_ftp_history` | Historic FTP for a sport over a date range |
| `get_max_metrics` | Max-metric data (e.g. VO2max) over a date range |
| `get_resting_heart_rate` | Daily resting heart rate trend over a date range |
| `get_fitness_age` | Garmin Fitness Age for a given date |
| `get_personal_records` | Personal records |
| `list_workouts` | Saved workout templates, most recent first (paginated) |
| `get_workout` | Full structure of one workout: segments, targets, intervals |
| `get_scheduled_workouts` | Calendar of workouts scheduled for a given month |
| `get_scheduled_workout` | Detail for one scheduled workout instance |
| `list_training_plans` | Training plans |
| `get_training_plan` | Details for a specific training plan |
| `get_adaptive_training_plan` | Details for a specific adaptive training plan |

All date parameters take `YYYY-MM-DD` and default to today.

## Troubleshooting

**A tool call returns a "Garmin session error" / "run setup_auth.py"
message.** Your cached refresh token expired or was revoked (this happens
occasionally, e.g. after a password change or long period of inactivity).
Re-run:

```bash
uv run python scripts/setup_auth.py
```

**Rate limited.** Garmin Connect will occasionally rate-limit rapid
requests; the underlying library retries transient failures automatically,
but if you see a rate-limit error, wait a bit and try again.

**Verifying the server directly, outside Claude Desktop:**

```bash
uv run mcp dev src/garmin_mcp/server.py
```

opens the MCP Inspector so you can call each tool by hand and check its
output/schema.

## Project layout

```
garmin_mcp/
  pyproject.toml
  src/garmin_mcp/
    auth.py      # keychain + token-cache helpers
    server.py    # FastMCP server and tool definitions
  scripts/
    setup_auth.py  # interactive one-time/occasional login
```
