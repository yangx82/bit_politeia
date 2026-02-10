# Multi-Channel Configuration Guide

## 1. Telegram Integration

### Prerequisites
- A Telegram account.
- Basic knowledge of environment variables.

### Setup Steps
1.  **Create a Bot**:
    - Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
    - Send `/newbot` and follow the prompts to name your bot.
    - Copy the **HTTP API Token** provided (e.g., `123456:ABC-DEF...`).

2.  **Configure Environment**:
    - Open `D:\git\bit_politeia\.env` (or create it).
    - Add the following line:
        ```bash
        TELEGRAM_TOKEN=your_copied_token
        ```

3.  **Start the Agent**:
    - Restart the backend service.
    - Verify logs show: `Initializing Telegram Channel...`.

---

## 2. Feishu (Lark) Integration

### Prerequisites
- A Feishu (Lark) tenant/organization account.
- Permission to create Custom Apps on [Feishu Open Platform](https://open.feishu.cn/).

### Setup Steps
1.  **Create Custom App**:
    - Log in to the [Feishu Developer Console](https://open.feishu.cn/app).
    - Click **"Create Custom App"**.
    - Fill in name (e.g., "Resident Agent") and description.

2.  **Get Credentials**:
    - In **"Credentials & Basic Info"**, copy the **App ID** and **App Secret**.

3.  **Enable Features**:
    - Go to **"Add Features"** -> **"Bot"** -> Click **"Add"**.

4.  **Configure Permissions**:
    - Go to **"Permissions & Scopes"**.
    - Search for and add the following permissions:
        - `im:message` (Access private messages)
        - `im:message.group_at_msg` (Access group messages)
        - `im:message:send_as_bot` (Send messages as bot)
    - Click **"Create Version"** and publish the app (must be approved by admin if needed).

5.  **Configure Environment**:
    - Add to `.env`:
        ```bash
        FEISHU_APP_ID=cli_a1b2c3d4e5
        FEISHU_APP_SECRET=your_app_secret_here
        ```

6.  **Run**:
    - Restart the backend.
    - The Agent uses WebSocket mode, so **no** Public IP/Callback URL configuration is needed on the Feishu console!
