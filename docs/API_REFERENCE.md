# API Reference

Complete API documentation for the Card Balance Checker web application.

## Base URL

```
http://127.0.0.1:5000
```

---

## Table of Contents

- [Card Checking](#card-checking)
- [Google Sheets](#google-sheets)
- [Exit Nodes](#exit-nodes)
- [Settings](#settings)
- [Gemini AI](#gemini-ai)
- [Browser Testing](#browser-testing)
- [System](#system)

---

## Card Checking

### Check Card Balance

Check balance for a single card.

```http
POST /check_balance
Content-Type: application/json
```

**Request Body:**
```json
{
  "card_number": "4111111111111111",
  "exp_month": "12",
  "exp_year": "25",
  "cvv": "123",
  "headless": false,
  "max_retries": 5,
  "browser": "stealth",
  "captcha_mode": "gemini"
}
```

**Response:**
```json
{
  "success": true,
  "balance": "$50.00",
  "message": "Balance retrieved successfully",
  "check_date": "2024-01-15T10:30:00"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Card validation failed"
}
```

---

### Cancel Current Task

Cancel the running card check.

```http
POST /cancel
```

**Response:**
```json
{
  "success": true,
  "message": "Task cancelled! Task browser closed, exit node disconnected."
}
```

---

### Force Kill Browsers

Emergency kill all browser processes.

```http
POST /force_kill_browsers
```

**Response:**
```json
{
  "success": true,
  "message": "Force killed all browsers: chromium, chrome, chromedriver",
  "killed": ["chromium", "chrome", "chromedriver"]
}
```

---

### Get Status

Get current automation status.

```http
GET /status
```

**Response:**
```json
{
  "running": true,
  "step": "Filling card information...",
  "progress": 30,
  "cancelled": false,
  "current_task": "Checking card ****1234"
}
```

---

### Get History

Get check history.

```http
GET /history
```

**Response:**
```json
[
  {
    "timestamp": "2024-01-15 10:30:00",
    "card_last4": "1234",
    "success": true,
    "balance": "$50.00",
    "message": ""
  }
]
```

---

### Clear History

Clear check history.

```http
POST /clear_history
```

---

## Google Sheets

### Get All Cards

Get all cards from the Google Sheet.

```http
GET /sheets/cards
```

**Response:**
```json
{
  "success": true,
  "total": 150,
  "cards": [
    {
      "row_index": 2,
      "id": "1",
      "card_last4": "1234",
      "exp": "12/25",
      "initial_balance": "50.00",
      "current_balance": "45.00",
      "is_checked": true,
      "is_duplicate": false,
      "last_check_date": "2024-01-15"
    }
  ]
}
```

---

### Get Unchecked Cards

Get cards that haven't been checked yet.

```http
GET /sheets/unchecked
```

**Response:**
```json
{
  "success": true,
  "total": 25,
  "cards": [
    {
      "row_index": 10,
      "id": "5",
      "card_last4": "5678",
      "exp": "06/26"
    }
  ]
}
```

---

### Check Card from Sheet

Check a specific card by row index.

```http
POST /sheets/check/{row_index}
Content-Type: application/json
```

**Request Body:**
```json
{
  "headless": false,
  "max_retries": 5,
  "skip_duplicates": true,
  "notes": "First check"
}
```

**Response:**
```json
{
  "success": true,
  "balance": "$50.00",
  "is_duplicate": false,
  "duplicate_rows": [],
  "duplicates_marked": 0
}
```

---

### Get Sheet Statistics

Get statistics about the sheet.

```http
GET /sheets/stats
```

**Response:**
```json
{
  "success": true,
  "total": 150,
  "checked": 100,
  "unchecked": 50,
  "duplicate_cards": 10,
  "duplicates_marked": 8,
  "first_row": 2,
  "last_row": 151
}
```

---

### Check Duplicate Status

Check if a card is duplicate.

```http
GET /sheets/check_duplicate/{row_index}
```

**Response:**
```json
{
  "success": true,
  "is_duplicate": true,
  "duplicate_rows": [5, 15, 25],
  "card_last4": "1234"
}
```

---

### Update Sheet Row

Manually update a row in the sheet.

```http
POST /sheets/update/{row_index}
Content-Type: application/json
```

**Request Body:**
```json
{
  "initial_balance": "50.00",
  "current_balance": "45.00"
}
```

---

## Exit Nodes

### Get Available Exit Nodes

List all Tailscale exit nodes.

```http
GET /exit_nodes
```

**Response:**
```json
{
  "success": true,
  "current_node": "us-east-1.tailscale.com",
  "total": 5,
  "nodes": [
    {
      "hostname": "us-east-1.tailscale.com",
      "ip": "100.64.0.1",
      "active": true,
      "online": true
    }
  ]
}
```

---

### Switch Exit Node

Switch to a different exit node.

```http
POST /exit_nodes/switch
Content-Type: application/json
```

**Request Body:**
```json
{
  "hostname": "us-west-2.tailscale.com"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Switched to us-west-2.tailscale.com",
  "current_node": "us-west-2.tailscale.com"
}
```

---

### Disable Exit Node

Disconnect from exit node (use direct connection).

```http
POST /exit_nodes/disable
```

**Response:**
```json
{
  "success": true,
  "message": "Exit node disabled - using direct connection"
}
```

---

### Test Exit Node

Test an exit node for CAPTCHA.

```http
POST /exit_nodes/test
Content-Type: application/json
```

**Request Body:**
```json
{
  "hostname": "us-east-1.tailscale.com",
  "headless": true
}
```

**Response:**
```json
{
  "success": true,
  "mode": "single",
  "hostname": "us-east-1.tailscale.com",
  "captcha_triggered": false,
  "status": "pass",
  "message": "No CAPTCHA detected"
}
```

---

## Settings

### Get Settings

Get current settings.

```http
GET /settings
```

**Response:**
```json
{
  "success": true,
  "settings": {
    "headless": false,
    "browser": "stealth",
    "max_retries": 5,
    "skip_duplicates": true,
    "captcha_mode": "gemini",
    "browser_profile": "mobile_iphone_chrome"
  }
}
```

---

### Update Settings

Update settings.

```http
POST /settings
Content-Type: application/json
```

**Request Body:**
```json
{
  "headless": true,
  "browser": "chromium",
  "max_retries": 3,
  "captcha_mode": "auto"
}
```

---

### Get Available Browsers

List available browser options.

```http
GET /settings/browsers
```

**Response:**
```json
{
  "success": true,
  "browsers": [
    {"id": "chromium", "name": "Chromium", "description": "Open-source Chrome engine"},
    {"id": "stealth", "name": "Stealth (UC Mode)", "description": "Anti-detection browser"}
  ],
  "current": "stealth"
}
```

---

### Get Browser Profiles

List available browser profiles for anti-detection.

```http
GET /settings/browser_profiles
```

**Response:**
```json
{
  "success": true,
  "profiles": [
    {
      "id": "desktop_windows",
      "name": "Desktop Windows",
      "viewport": {"width": 1920, "height": 1080},
      "is_mobile": false
    },
    {
      "id": "mobile_iphone_chrome",
      "name": "iPhone Chrome",
      "viewport": {"width": 390, "height": 844},
      "is_mobile": true,
      "has_touch": true
    }
  ],
  "current": "mobile_iphone_chrome"
}
```

---

## Gemini AI

### Get Prompt Presets

Get all available prompt presets with full text.

```http
GET /gemini/prompt_presets
```

**Response:**
```json
{
  "success": true,
  "presets": {
    "detailed": {
      "name": "Detailed Prompt",
      "description": "Full visual grid diagram",
      "full_prompt": "You are a CAPTCHA image analyzer...",
      "is_builtin": true
    },
    "expert": {
      "name": "Expert Prompt",
      "description": "Technical precision focus",
      "full_prompt": "...",
      "is_builtin": true
    }
  }
}
```

---

### Get Prompt Statistics

Get success rate statistics for prompts.

```http
GET /gemini/prompt_stats
```

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_attempts": 100,
    "total_successes": 85,
    "overall_success_rate": 85.0,
    "current_preset": "expert",
    "ranking": [
      {"name": "expert", "success_rate": 87.5, "attempts": 80},
      {"name": "detailed", "success_rate": 75.0, "attempts": 20}
    ]
  }
}
```

---

### Test Gemini API Key

Test if current API key is working.

```http
POST /gemini/test
```

**Response:**
```json
{
  "success": true,
  "message": "API key 1 is working!",
  "model": "gemini-2.5-flash"
}
```

---

### Rotate API Key

Switch to next API key.

```http
POST /gemini/rotate_key
```

**Response:**
```json
{
  "success": true,
  "current_key_index": 1,
  "total_keys": 9,
  "message": "Switched to key 2 of 9"
}
```

---

### Get API Keys Status

Get detailed status of all API keys.

```http
GET /gemini/keys_status
```

**Response:**
```json
{
  "success": true,
  "total_keys": 9,
  "available_keys": 7,
  "total_remaining_requests": 350,
  "keys": [
    {
      "key_number": 1,
      "key_masked": "...BIUU",
      "requests_made": 45,
      "is_rate_limited": false,
      "remaining_requests": 55
    }
  ]
}
```

---

### Create Custom Prompt

Save a new prompt file.

```http
POST /gemini/prompts/{key}
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "My Custom Prompt",
  "description": "Optimized for traffic lights",
  "prompt": "Analyze the CAPTCHA grid..."
}
```

---

## Browser Testing

### Plugin Test

Run a browser test with custom settings.

```http
POST /plugin/test
Content-Type: application/json
```

**Request Body:**
```json
{
  "url": "https://bot.sannysoft.com/",
  "browser": "stealth",
  "exit_node": "",
  "headers": {},
  "timeout": 30,
  "viewport": "1920x1080",
  "headless": false,
  "screenshot": true,
  "capture_console": false,
  "keep_open": false,
  "script": "return document.title"
}
```

**Response:**
```json
{
  "success": true,
  "url": "https://bot.sannysoft.com/",
  "final_url": "https://bot.sannysoft.com/",
  "title": "Antibot Test",
  "status_code": 200,
  "load_time": 2500,
  "screenshot": "base64...",
  "script_result": "Antibot Test",
  "detected_ip": "1.2.3.4"
}
```

---

### Stop Plugin Test

Stop running browser test.

```http
POST /plugin/stop
```

---

## System

### Stream Logs

Server-Sent Events for real-time logs.

```http
GET /logs
```

**Event Stream:**
```
data: {"log": "2024-01-15 10:30:00 - INFO - Starting check..."}

data: {"heartbeat": true}

data: {"log": "2024-01-15 10:30:05 - INFO - Form filled"}
```

---

### Clear Logs

Clear the log queue.

```http
POST /clear_logs
```

---

## Phone API (Port 5001)

### Get Phone Status

```http
GET /api/status
```

**Response:**
```json
{
  "initialized": true,
  "device": {
    "model": "Pixel 6",
    "brand": "Google",
    "android_version": "14"
  },
  "scrcpy_running": true,
  "device_serial": "ABCD1234"
}
```

---

### Take Screenshot

```http
GET /api/screenshot
```

**Response:**
```json
{
  "image": "data:image/jpeg;base64,...",
  "timestamp": "2024-01-15T10:30:00"
}
```

---

### Open URL on Phone

```http
POST /api/open_url
Content-Type: application/json
```

**Request Body:**
```json
{
  "url": "https://example.com"
}
```

---

### Tap Screen

```http
POST /api/tap
Content-Type: application/json
```

**Request Body:**
```json
{
  "x": 500,
  "y": 800,
  "duration": 0
}
```

---

### Input Text

```http
POST /api/input
Content-Type: application/json
```

**Request Body:**
```json
{
  "text": "Hello World"
}
```

---

### Check Card on Phone

```http
POST /api/card/check
Content-Type: application/json
```

**Request Body:**
```json
{
  "card_number": "4111111111111111",
  "exp_month": "12",
  "exp_year": "25",
  "cvv": "123"
}
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource doesn't exist |
| 500 | Server Error - Internal error |

---

## Rate Limiting

The API doesn't have built-in rate limiting, but Gemini AI has:
- 60 requests per minute per key
- Use `/gemini/rotate_key` when rate limited

---

## WebSocket / SSE

For real-time updates, use the `/logs` endpoint with Server-Sent Events:

```javascript
const eventSource = new EventSource('/logs');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.log) {
    console.log(data.log);
  }
};
```
