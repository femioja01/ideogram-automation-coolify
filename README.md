# Ideogram Image Automation Control Center (macOS Local Version)

A high-performance local web application and automation engine for batch generating images on **Ideogram.ai** with automated Vision Quality Scoring (**CLIProxy / Gemini 3.5 Flash Low / OpenAI / Replicate**).

---

## ⚡ Quick Start on macOS

### 1. Launch the Application
In your Mac terminal, navigate to this directory and run:
```bash
bash run_local.sh
```

*(Or double-click `start_mac.command` in Finder)*

### 2. Open the Web Dashboard
Open your browser to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## ✨ Features

- **Visual Dashboard**: Real-time stats (Total Prompts, Completed, Pending, Failed, Generated Images) & live WebSocket terminal log streaming.
- **Native Chrome Automation**: DrissionPage CDP stealth engine running natively on your Mac GPU with zero lag.
- **5-Minute Unconditional Login Window**: Easy manual login or Google Sign-In with automatic session persistence (`chrome_profile/`).
- **Prompts Database Manager**: Add, edit, filter, reset failed prompts, or trigger single prompt runs.
- **Image Gallery**: View and download high-scoring generated images with metadata and vision quality scores.
- **App Settings**: Configure your `CLIPROXY_API_KEY`, `OPENAI_API_KEY`, or `REPLICATE_API_TOKEN`, score threshold, and retries directly from the UI.
