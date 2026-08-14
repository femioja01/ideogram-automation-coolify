# Deploying Ideogram Automation on KVM 2 Server via Coolify

This guide covers deploying the upgraded **Ideogram Stealth Automation & Control Center** to a Linux KVM 2 VPS using **Coolify**.

---

## 🌟 Key Features of the Deployed App

* **Stealth Automation (DrissionPage)**: Bypasses Cloudflare anti-bot checks using Chromium DevTools Protocol (CDP) on a virtual display server (XVFB).
* **Web Control Dashboard (`http://your-server-ip:8000`)**:
  * **Real-time Terminal Logs**: WebSocket live stream of execution logs and stdout/stderr.
  * **Interactive Prompts Database**: Add, edit, filter, or delete prompts directly in `prompts.csv`.
  * **Generated Asset Gallery**: Browse output images with vision scores, prompt details, and download options.
* **Live Virtual Screen Viewer (noVNC)**:
  * Embedded live VNC browser tab streaming XVFB screen (`:99`).
  * **Interactive Login**: Log into Ideogram (Google/Email) directly through your browser inside your deployed Coolify app!

---

## 1. Coolify Deployment Steps

### Step 1: Create a New Application in Coolify
1. In your Coolify dashboard, select your **Project** and **Environment**.
2. Click **+ Add New Resource** → **Public / Private Repository** (or **Docker Compose**).
3. Connect repository `https://github.com/femioja01/ideogram-automation-coolify`.
4. Set the **Build Pack** to **Docker Compose** (or **Dockerfile**).

### Step 2: Configure Environment Variables
In Coolify, navigate to **Environment Variables** and add:

```env
REPLICATE_API_TOKEN=r8_your_replicate_token_here
OUTPUT_DIR=output_images
BASIC_AUTH_USERNAME=admin
BASIC_AUTH_PASSWORD=your_secure_dashboard_password
```

### Step 3: Configure Ports & Reverse Proxy
* **Primary Web Dashboard Port**: `8000` (Map your domain or subdomain to port 8000 in Coolify).
* **Live Screen VNC Port**: `6080` (Optional secondary port for direct noVNC streams).

### Step 4: Configure Persistent Volumes
In Coolify's **Storages / Volumes** tab, map:
1. `chrome_profile_data` ➔ `/app/chrome_profile`
2. `output_images_data` ➔ `/app/output_images`
3. `prompts_data` ➔ `/app/prompts_data`
