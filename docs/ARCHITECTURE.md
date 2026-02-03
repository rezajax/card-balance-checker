# Project Architecture

This document explains the complete architecture of the Card Balance Checker & Browser Automation system. It's designed to help developers understand how all components work together.

## Table of Contents

- [System Overview](#system-overview)
- [High-Level Architecture](#high-level-architecture)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Module Details](#module-details)
- [Design Decisions](#design-decisions)

---

## System Overview

This project is a **multi-platform card balance checking automation system** with the following capabilities:

1. **Web-based Control Panel** - Flask application for managing card checks
2. **Browser Automation** - Playwright & SeleniumBase for bypassing anti-bot detection
3. **AI CAPTCHA Solving** - Gemini AI integration for solving reCAPTCHA challenges
4. **Google Sheets Integration** - Read cards and write results automatically
5. **VPN/Exit Node Management** - Tailscale integration for IP rotation
6. **Phone Automation** - ADB-based Android device control (alternative approach)

---

## High-Level Architecture

```mermaid
graph TB
    subgraph "User Interface"
        WEB[Web Panel<br/>Flask + HTML/JS]
        API[REST API<br/>Endpoints]
    end

    subgraph "Core Automation"
        CARD[CardChecker<br/>Playwright]
        STEALTH[StealthCardChecker<br/>SeleniumBase UC]
        BROWSER[StealthBrowser<br/>Anti-Detection]
    end

    subgraph "AI & CAPTCHA"
        GEMINI[Gemini AI<br/>CAPTCHA Solver]
        PROMPTS[Prompt Templates<br/>detailed/simple/expert]
    end

    subgraph "Data Layer"
        SHEETS[SheetsManager<br/>Google Sheets API]
        SETTINGS[Settings<br/>JSON Config]
        HISTORY[Check History<br/>In-Memory]
    end

    subgraph "Network Layer"
        TAILSCALE[TailscaleManager<br/>Exit Node Control]
    end

    subgraph "Phone Automation"
        ADB[ADBController]
        SCRCPY[ScrcpyManager]
        PHONE_WEB[Phone Web App]
    end

    WEB --> API
    API --> CARD
    API --> STEALTH
    CARD --> BROWSER
    STEALTH --> BROWSER
    CARD --> GEMINI
    STEALTH --> GEMINI
    GEMINI --> PROMPTS
    API --> SHEETS
    API --> TAILSCALE
    API --> SETTINGS
    PHONE_WEB --> ADB
    ADB --> SCRCPY
```

---

## Core Components

### 1. Web Application (`app.py`)

The central control hub - a Flask web application providing:

```mermaid
graph LR
    subgraph "Flask App (app.py)"
        ROUTES[Route Handlers]
        SSE[Server-Sent Events<br/>Real-time Logs]
        QUEUE[Log Queue<br/>Thread-Safe]
    end

    subgraph "API Groups"
        CARD_API[/check_balance<br/>/sheets/check]
        NODE_API[/exit_nodes<br/>/exit_nodes/switch]
        SETTINGS_API[/settings<br/>/gemini/*]
        PLUGIN_API[/plugin/test]
    end

    ROUTES --> CARD_API
    ROUTES --> NODE_API
    ROUTES --> SETTINGS_API
    ROUTES --> PLUGIN_API
    SSE --> QUEUE
```

**Key Features:**
- Real-time log streaming via SSE
- Task cancellation support
- Session management
- Settings persistence (JSON file)

### 2. Card Checker (`card_checker.py`)

The main automation engine using Playwright:

```mermaid
stateDiagram-v2
    [*] --> Initialize
    Initialize --> NavigateToSite
    NavigateToSite --> FillForm
    FillForm --> HandleCAPTCHA
    HandleCAPTCHA --> SolvingCAPTCHA: CAPTCHA Detected
    SolvingCAPTCHA --> GeminiAI: AI Mode
    SolvingCAPTCHA --> ManualWait: Manual Mode
    SolvingCAPTCHA --> AutoRetry: Auto Mode
    GeminiAI --> SubmitForm
    ManualWait --> SubmitForm
    AutoRetry --> SwitchExitNode: CAPTCHA Failed
    SwitchExitNode --> NavigateToSite
    HandleCAPTCHA --> SubmitForm: No CAPTCHA
    SubmitForm --> ExtractBalance
    ExtractBalance --> [*]: Success
    ExtractBalance --> [*]: Error
```

**Components:**
- `CardChecker` - Main class with Playwright
- `TailscaleManager` - Exit node management
- `CaptchaTester` - Test exit nodes for CAPTCHA
- `BROWSER_PROFILES` - Device emulation profiles
- `GeminiCaptchaSolver` - AI-based CAPTCHA solving

### 3. Stealth Browser (`stealth_browser.py`)

Anti-detection browser wrapper using SeleniumBase UC Mode:

```mermaid
graph TD
    subgraph "StealthBrowser"
        INIT[Initialize]
        START[start<br/>Launch UC Browser]
        NAV[navigate<br/>uc_open_with_reconnect]
        CAPTCHA[handle_captcha<br/>uc_gui_click_captcha]
        CLOSE[close<br/>Cleanup]
    end

    subgraph "Anti-Detection Features"
        DEVTOOLS[DevTools Rename]
        DISCONNECT[Auto Disconnect<br/>on Page Load]
        FINGERPRINT[Fingerprint<br/>Masking]
    end

    INIT --> START
    START --> DEVTOOLS
    START --> DISCONNECT
    START --> FINGERPRINT
    START --> NAV
    NAV --> CAPTCHA
    CAPTCHA --> CLOSE
```

**Why SeleniumBase UC Mode?**
- Automatically renames DevTools variables
- Disconnects during page load (avoids detection)
- Built-in CAPTCHA click methods
- Better than raw undetected-chromedriver

### 4. Sheets Manager (`sheets_manager.py`)

Google Sheets integration for batch processing:

```mermaid
graph LR
    subgraph "Google Sheets"
        SHEET[Card Sheet]
        COL_A[ID]
        COL_B[UUID]
        COL_C[Card Number]
        COL_D[Exp Month]
        COL_E[Exp Year]
        COL_F[CVV]
        COL_G[Initial Balance]
        COL_H[Current Balance]
        COL_I[Result JSON]
    end

    subgraph "SheetsManager"
        GET[get_all_cards]
        UPDATE[update_card_result]
        DUP[check_duplicate]
        STATS[get_sheet_stats]
    end

    SHEET --> GET
    UPDATE --> SHEET
    GET --> DUP
    DUP --> STATS
```

**Duplicate Detection:**
- Detects same card across multiple rows
- Copies balance from existing duplicate
- Marks duplicates as "DUPLICATE" to skip

### 5. Gemini CAPTCHA Solver

AI-powered reCAPTCHA solving:

```mermaid
sequenceDiagram
    participant C as CardChecker
    participant G as GeminiSolver
    participant A as Gemini API
    participant P as Prompts

    C->>G: solve_captcha(screenshot)
    G->>P: get_prompt(preset)
    P-->>G: prompt_text
    G->>G: Divide into grid
    G->>A: Send image + prompt
    A-->>G: "1, 4, 7, 8"
    G->>G: Parse tile numbers
    G-->>C: tiles_to_click[]
    C->>C: Click each tile
    C->>G: solve_captcha(new_screenshot)
    Note over C,G: Repeat until solved or timeout
```

**Prompt Presets:**
- `detailed` - Full grid diagram explanation
- `simple` - Minimal instructions
- `visual` - Coordinate-based approach
- `expert` - Technical precision focus
- `custom` - User-defined prompts

### 6. Phone Automation (`phone/`)

Alternative approach using Android phone via ADB:

```mermaid
graph TB
    subgraph "Phone Module"
        MAIN[PhoneAutomation]
        ADB[ADBController]
        SCRCPY[ScrcpyManager]
        BROWSER_AUTO[PhoneBrowserAutomation]
        SCREEN[ScreenReader]
        CHECKER[PhoneCardChecker]
    end

    subgraph "Android Device"
        PHONE[Phone/Tablet]
        BRAVE[Brave Browser]
    end

    MAIN --> ADB
    MAIN --> SCRCPY
    MAIN --> BROWSER_AUTO
    ADB --> PHONE
    SCRCPY --> PHONE
    BROWSER_AUTO --> ADB
    BROWSER_AUTO --> BRAVE
    SCREEN --> ADB
    CHECKER --> BROWSER_AUTO
    CHECKER --> SCREEN
```

**Why Phone Automation?**
- Real device fingerprint (not emulated)
- Mobile carrier IP
- Harder to detect as bot
- Alternative when desktop automation blocked

---

## Data Flow

### Card Check Flow (Desktop)

```mermaid
sequenceDiagram
    participant U as User
    participant W as Web Panel
    participant A as App.py
    participant C as CardChecker
    participant T as Tailscale
    participant S as Site
    participant G as Gemini
    participant SH as Sheets

    U->>W: Click "Check Card"
    W->>A: POST /sheets/check/5
    A->>SH: get_card_by_row(5)
    SH-->>A: card_data

    alt Always Use Exit Node
        A->>T: switch_exit_node()
        T-->>A: connected
    end

    A->>C: check_balance(card)
    C->>S: Navigate to rcbalance.com
    S-->>C: Page loaded
    C->>C: Fill form fields
    C->>S: Look for CAPTCHA

    alt CAPTCHA Present
        C->>G: solve_captcha(screenshot)
        G-->>C: tiles_to_click
        C->>S: Click tiles
        loop Until Solved
            C->>G: solve_captcha(new_screenshot)
            G-->>C: more_tiles
            C->>S: Click tiles
        end
    end

    C->>S: Submit form
    S-->>C: Result page
    C->>C: Extract balance
    C-->>A: {success: true, balance: "$50.00"}
    A->>SH: update_card_result(5, result)
    A-->>W: JSON response
    W-->>U: Show balance
```

---

## Module Details

### File Structure

```
cursor/
├── app.py                    # Main Flask application
├── card_checker.py           # Playwright-based card checker (large, ~135KB)
├── stealth_browser.py        # SeleniumBase UC wrapper
├── stealth_card_checker.py   # Card checker using stealth browser
├── sheets_manager.py         # Google Sheets integration
├── browser_automation.py     # Basic Playwright automation
├── advanced_automation.py    # Advanced automation examples
│
├── prompts/                  # Gemini CAPTCHA prompts
│   ├── detailed.md
│   ├── simple.md
│   ├── visual.md
│   └── expert.md
│
├── phone/                    # Phone automation module
│   ├── __init__.py
│   ├── main.py              # Phone automation entry point
│   ├── web_app.py           # Phone web interface
│   ├── adb_controller.py    # ADB commands
│   ├── scrcpy_manager.py    # scrcpy screen mirroring
│   ├── browser_automation.py # Phone browser control
│   ├── screen_reader.py     # UI hierarchy parsing
│   ├── card_checker.py      # Phone card checker
│   └── templates/phone.html
│
├── templates/index.html      # Main web UI
├── static/css/style.css      # Styles
├── settings.json             # Persistent settings
├── requirements.txt          # Dependencies
└── docs/                     # Documentation
```

### Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `CardChecker` | card_checker.py | Main Playwright-based checker |
| `StealthCardChecker` | stealth_card_checker.py | SeleniumBase UC checker |
| `StealthBrowser` | stealth_browser.py | Anti-detection browser |
| `SheetsManager` | sheets_manager.py | Google Sheets CRUD |
| `TailscaleManager` | card_checker.py | VPN exit node control |
| `GeminiCaptchaSolver` | card_checker.py | AI CAPTCHA solving |
| `ADBController` | phone/adb_controller.py | Android ADB commands |
| `PhoneCardChecker` | phone/card_checker.py | Phone-based checker |

---

## Design Decisions

### Why Two Browser Engines?

1. **Playwright** (`CardChecker`)
   - Faster and more reliable
   - Better API for automation
   - Works when site doesn't have strong anti-bot

2. **SeleniumBase UC** (`StealthCardChecker`)
   - Bypasses Cloudflare/anti-bot detection
   - Used when Playwright gets blocked
   - More resource-intensive

### Why Multiple CAPTCHA Modes?

```mermaid
graph TD
    CAPTCHA[CAPTCHA Detected]
    AUTO[Auto Mode]
    GEMINI[Gemini AI Mode]
    MANUAL[Manual Mode]

    CAPTCHA --> AUTO
    CAPTCHA --> GEMINI
    CAPTCHA --> MANUAL

    AUTO --> |Try Exit Nodes| SWITCH[Switch IP]
    SWITCH --> |Retry 5x| FAIL[Give Up]

    GEMINI --> |Screenshot| AI[AI Analysis]
    AI --> |Click Tiles| SOLVE[Solved]
    AI --> |Fail| MANUAL

    MANUAL --> |Wait 60s| USER[User Solves]
```

- **Auto**: Best for sites where IP change bypasses CAPTCHA
- **Gemini AI**: Best success rate, but uses API quota
- **Manual**: Fallback when AI fails

### Why Phone Automation?

Desktop browsers are increasingly detected. Mobile phones provide:
- Real device fingerprint
- Carrier IP addresses
- Touch-based interactions
- App-level isolation

The phone module is an **alternative approach** when desktop automation fails.

---

## Configuration

### Settings Schema

```json
{
  "headless": false,
  "browser": "stealth",
  "max_retries": 5,
  "skip_duplicates": true,
  "skip_checked": true,
  "timeout": 60000,
  "captcha_mode": "gemini",
  "always_use_exit_node": true,
  "disconnect_after_task": true,
  "browser_profile": "mobile_iphone_chrome",
  "gemini_api_keys": ["key1", "key2", "..."],
  "gemini_model": "gemini-2.5-flash",
  "gemini_prompt_preset": "expert"
}
```

### Browser Profiles

| Profile | Viewport | Mobile | Touch |
|---------|----------|--------|-------|
| desktop_windows | 1920x1080 | No | No |
| desktop_mac | 1440x900 | No | No |
| mobile_iphone | 390x844 | Yes | Yes |
| mobile_iphone_chrome | 390x844 | Yes | Yes |
| mobile_android | 412x915 | Yes | Yes |
| tablet_ipad | 1024x1366 | Yes | Yes |

---

## Next Steps

- See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for installation
- See [API_REFERENCE.md](./API_REFERENCE.md) for endpoint details
- See [DEVELOPMENT_JOURNEY.md](./DEVELOPMENT_JOURNEY.md) for lessons learned
