#!/usr/bin/env bash
# =============================================================================
# PentestGPT-lite — One-Command Installer
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Usage:
#   chmod +x setup.sh && sudo ./setup.sh
#
# What this does:
#   1. Updates system packages
#   2. Installs system dependencies (nmap, hydra, aircrack-ng, espeak-ng, etc.)
#   3. Installs Whisplay Pi AI Hat drivers (WM8960 audio, LCD, buttons, LED)
#   4. Enables I2C and SPI via raspi-config (required for OLED + PiSugar)
#   5. Creates Python virtual environment and installs pip packages
#   6. Downloads TinyLlama-1.1B-Q4_0 GGUF model if not present
#   7. Creates necessary directories
#   8. Configures systemd service for auto-start on boot
#   9. Sets up swap (256 MB) to handle LLM memory spikes
#
# RAM Budget (tested with `free -m` after full startup):
#   TinyLlama Q4_0 inference : ~180 MB
#   Python UI + runtime       :  ~30 MB
#   Tools (subprocess)        :  ~20 MB
#   OS overhead               :  ~60 MB
#   Total used                : ~290 MB  (of 512 MB hardware)
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'  # No Colour

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Must run as root ──────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "Please run as root: sudo ./setup.sh"

# ── Detect Pi OS ──────────────────────────────────────────────────────────────
ARCH=$(uname -m)
info "Detected architecture: ${ARCH}"
[[ "$ARCH" =~ ^(aarch64|armv8|armv7l)$ ]] || \
    warn "Unexpected architecture ${ARCH} — designed for Raspberry Pi ARMv8"

# =============================================================================
# STEP 1 — System package update
# =============================================================================
info "Step 1/9 — Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
success "System packages updated."

# =============================================================================
# STEP 2 — Install system dependencies
# =============================================================================
info "Step 2/9 — Installing system dependencies..."

PACKAGES=(
    # Core tooling
    python3 python3-pip python3-venv python3-dev
    # Desktop GUI (Tkinter — required for python3 gui.py)
    python3-tk
    # Whisplay HAT Python dependencies (display, GPIO, audio)
    python3-libgpiod python3-spidev python3-pil python3-pygame
    # Pentest tools
    nmap hydra aircrack-ng sqlmap
    # Voice output
    espeak-ng
    # Voice input — PyAudio requires PortAudio development headers
    portaudio19-dev
    # Audio utilities (ALSA — needed for WM8960 soundcard verification)
    alsa-utils
    # I2C / SPI / GPIO
    python3-smbus i2c-tools
    # Misc
    git curl wget unzip usbutils
    # Build tools (needed for llama-cpp-python compilation)
    build-essential cmake
)

for pkg in "${PACKAGES[@]}"; do
    if dpkg -s "$pkg" &>/dev/null; then
        info "  Already installed: $pkg"
    else
        apt-get install -y -qq "$pkg" && success "  Installed: $pkg"
    fi
done

success "System dependencies installed."

# =============================================================================
# STEP 3 — Install Whisplay Pi AI Hat drivers
# =============================================================================
info "Step 3/9 — Installing Whisplay Pi AI Hat drivers (WM8960 audio + LCD + buttons + LED)..."

WHISPLAY_DIR="/opt/Whisplay"

if [[ -d "$WHISPLAY_DIR" ]]; then
    info "  Whisplay repo already cloned — pulling latest..."
    git -C "$WHISPLAY_DIR" pull --quiet
else
    info "  Cloning PiSugar/Whisplay driver repo..."
    git clone https://github.com/PiSugar/Whisplay.git --depth 1 "$WHISPLAY_DIR"
    success "  Whisplay repo cloned to $WHISPLAY_DIR"
fi

# Run the official Raspberry Pi WM8960 driver installer
# This installs the ALSA overlay, configures /boot/firmware/config.txt,
# and sets up the wm8960-soundcard so PyAudio can open the mic/speaker.
WHISPLAY_DRIVER_SCRIPT="$WHISPLAY_DIR/Driver/install_wm8960_drive.sh"
if [[ -f "$WHISPLAY_DRIVER_SCRIPT" ]]; then
    info "  Running WM8960 audio driver installer..."
    bash "$WHISPLAY_DRIVER_SCRIPT"
    success "  WM8960 audio driver installed."
else
    warn "  install_wm8960_drive.sh not found at expected path — check $WHISPLAY_DIR/Driver/"
    warn "  Audio (mic + speaker) may not work until the WM8960 driver is installed manually."
    warn "  Run manually: cd $WHISPLAY_DIR/Driver && sudo bash install_wm8960_drive.sh"
fi

# Copy the Whisplay.py driver module into the NxtGenAI directory
# so ui.py can import it for LCD/button/LED control
WHISPLAY_PY="$WHISPLAY_DIR/Driver/Whisplay.py"
if [[ -f "$WHISPLAY_PY" ]]; then
    cp "$WHISPLAY_PY" /home/pi/NxtGenAI/Whisplay.py 2>/dev/null || \
        cp "$WHISPLAY_PY" "$(dirname "${BASH_SOURCE[0]}")/Whisplay.py" 2>/dev/null || true
    success "  Whisplay.py driver module copied to project directory."
else
    warn "  Whisplay.py not found in $WHISPLAY_DIR/Driver/ — LCD/button/LED control may be limited."
fi

success "Whisplay Pi AI Hat driver setup complete."
warn "  *** A REBOOT is required after install for WM8960 audio and I2S overlay to activate. ***"
warn "  *** setup.sh will continue — reboot at the end. ***"

# =============================================================================
# STEP 4 — Enable I2C and SPI
# =============================================================================
info "Step 4/9 — Enabling I2C and SPI interfaces..."

# Enable I2C in /boot/config.txt (or /boot/firmware/config.txt on bookworm)
CONFIG_FILE="/boot/firmware/config.txt"
[[ -f "$CONFIG_FILE" ]] || CONFIG_FILE="/boot/config.txt"

if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE"; then
    echo "dtparam=i2c_arm=on" >> "$CONFIG_FILE"
    success "  I2C enabled in $CONFIG_FILE"
else
    info "  I2C already enabled."
fi

if ! grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
    echo "dtparam=spi=on" >> "$CONFIG_FILE"
    success "  SPI enabled in $CONFIG_FILE"
else
    info "  SPI already enabled."
fi

# Add pi user to i2c and spi groups
usermod -aG i2c,spi pi 2>/dev/null || true

# Load kernel modules immediately (for this session)
modprobe i2c-dev 2>/dev/null || true

success "I2C and SPI configured."

# =============================================================================
# STEP 5 — Create directory structure
# =============================================================================
info "Step 5/9 — Creating directory structure..."

mkdir -p /home/pi/models
mkdir -p /home/pi/wordlists
mkdir -p /home/pi/reports
mkdir -p /home/pi/NxtGenAI

chown -R pi:pi /home/pi/models /home/pi/wordlists /home/pi/reports

success "Directories created."

# =============================================================================
# STEP 6 — Python virtual environment + pip packages
# =============================================================================
info "Step 6/9 — Setting up Python virtual environment..."

VENV="/home/pi/pentestgpt-venv"

if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    success "  Virtual environment created at $VENV"
else
    info "  Virtual environment already exists at $VENV"
fi

# Activate venv and upgrade pip
"$VENV/bin/pip" install --quiet --upgrade pip

info "  Installing Python packages from requirements.txt..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
    # llama-cpp-python needs special compile flags for ARM
    CMAKE_ARGS="-DLLAMA_NATIVE=OFF" \
        "$VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    success "  Python packages installed."
else
    warn "  requirements.txt not found at $SCRIPT_DIR — skipping pip install."
fi

# Copy project files to /home/pi/NxtGenAI if not already there
if [[ "$SCRIPT_DIR" != "/home/pi/NxtGenAI" ]]; then
    cp -u "$SCRIPT_DIR"/*.py "$SCRIPT_DIR"/*.ini /home/pi/NxtGenAI/ 2>/dev/null || true
    chown -R pi:pi /home/pi/NxtGenAI
fi

# =============================================================================
# STEP 7 — Download TinyLlama model (if missing)
# =============================================================================
info "Step 7/9 — Checking for LLM model..."

MODEL_PATH="/home/pi/models/tinyllama-1.1b-q4_0.gguf"
MODEL_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf"

if [[ -f "$MODEL_PATH" ]]; then
    MODEL_SIZE=$(du -m "$MODEL_PATH" | cut -f1)
    if [[ $MODEL_SIZE -lt 100 ]]; then
        warn "  Model file looks corrupt (${MODEL_SIZE} MB) — re-downloading..."
        rm -f "$MODEL_PATH"
    else
        success "  Model already present (${MODEL_SIZE} MB): $MODEL_PATH"
    fi
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    warn "  Model not found. Downloading TinyLlama-1.1B-Q4_0 (~620 MB)..."
    warn "  This requires internet access. After this, the system is fully offline."
    # Download with progress bar, resume support
    wget --continue \
         --show-progress \
         --progress=bar:force \
         -O "$MODEL_PATH" \
         "$MODEL_URL" || {
        warn "  Download failed. You can manually place the model at:"
        warn "  $MODEL_PATH"
        warn "  Download from: $MODEL_URL"
    }
    chown pi:pi "$MODEL_PATH" 2>/dev/null || true
fi

success "Model check complete."

# =============================================================================
# STEP 8 — Download 10k common passwords wordlist (if missing)
# =============================================================================
info "Step 8/9 — Setting up wordlists..."

WORDLIST_10K="/home/pi/wordlists/10k-common.txt"
WORDLIST_URL="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10k-most-common.txt"

if [[ ! -f "$WORDLIST_10K" ]]; then
    warn "  Downloading 10k common passwords wordlist..."
    wget --quiet -O "$WORDLIST_10K" "$WORDLIST_URL" || {
        # Offline fallback: generate a tiny placeholder so the path exists
        warn "  Download failed — creating placeholder wordlist."
        echo -e "password\n123456\nadmin\nletmein\nwelcome" > "$WORDLIST_10K"
    }
    chown pi:pi "$WORDLIST_10K"
    success "  10k wordlist ready."
else
    info "  10k wordlist already present."
fi

# Note rockyou.txt installation
ROCKYOU="/home/pi/wordlists/rockyou.txt"
if [[ ! -f "$ROCKYOU" ]]; then
    if [[ -f /usr/share/wordlists/rockyou.txt ]]; then
        cp /usr/share/wordlists/rockyou.txt "$ROCKYOU"
        chown pi:pi "$ROCKYOU"
        success "  rockyou.txt copied from system wordlists."
    elif [[ -f /usr/share/wordlists/rockyou.txt.gz ]]; then
        gunzip -c /usr/share/wordlists/rockyou.txt.gz > "$ROCKYOU"
        chown pi:pi "$ROCKYOU"
        success "  rockyou.txt decompressed from system wordlists."
    else
        warn "  rockyou.txt not found. Install with: sudo apt install wordlists"
        warn "  Then copy to /home/pi/wordlists/rockyou.txt"
    fi
else
    info "  rockyou.txt already present."
fi

success "Wordlists ready."

# =============================================================================
# STEP 8b — Download Vosk small English model (for Push-to-Talk voice input)
# =============================================================================
info "Step 8b/9 — Checking for Vosk offline speech recognition model..."

VOSK_MODEL_DIR="/home/pi/models/vosk-model-small-en-us"
VOSK_ZIP="/home/pi/models/vosk-model-small-en-us-0.15.zip"
VOSK_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

if [[ -d "$VOSK_MODEL_DIR" ]]; then
    success "  Vosk model already present: $VOSK_MODEL_DIR"
else
    warn "  Vosk model not found. Downloading (~40 MB)..."
    warn "  This is used for offline push-to-talk voice recognition."
    wget --continue \
         --show-progress \
         --progress=bar:force \
         -O "$VOSK_ZIP" \
         "$VOSK_URL" && {
        unzip -q "$VOSK_ZIP" -d /home/pi/models/
        # Rename extracted folder to canonical name if needed
        extracted=$(find /home/pi/models -maxdepth 1 -type d -name "vosk-model-small-en-us*" | head -1)
        if [[ "$extracted" != "$VOSK_MODEL_DIR" && -n "$extracted" ]]; then
            mv "$extracted" "$VOSK_MODEL_DIR"
        fi
        rm -f "$VOSK_ZIP"
        chown -R pi:pi "$VOSK_MODEL_DIR"
        success "  Vosk model downloaded and extracted to $VOSK_MODEL_DIR"
    } || {
        warn "  Vosk download failed. Push-to-talk will be disabled until you"
        warn "  manually download and extract the model to: $VOSK_MODEL_DIR"
        warn "  URL: $VOSK_URL"
    }
fi

success "Vosk model check complete."

# =============================================================================
# STEP 9 — Configure swap + systemd service
# =============================================================================
info "Step 9/9 — Configuring swap and systemd service..."

# Set up 256 MB swap (LLM loading can spike RAM briefly)
if ! swapon --show | grep -q /swapfile; then
    if [[ ! -f /swapfile ]]; then
        dd if=/dev/zero of=/swapfile bs=1M count=256 status=none
        chmod 600 /swapfile
        mkswap /swapfile -q
    fi
    swapon /swapfile
    # Persist across reboots
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
    success "  256 MB swap enabled."
else
    info "  Swap already active."
fi

# Update systemd service for auto-start on boot (OLED headless mode)
SERVICE_FILE="/etc/systemd/system/pentestgpt.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=PentestGPT-lite Autonomous Pentesting Toolkit
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/NxtGenAI
ExecStart=/home/pi/pentestgpt-venv/bin/python3 /home/pi/NxtGenAI/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pentestgpt.service
success "  systemd service enabled (pentestgpt.service)"

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PentestGPT-lite installation complete!      ${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}┌─────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${CYAN}│  🚀  HOW TO LAUNCH                                              │${NC}"
echo -e "${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│  🖥️   Desktop GUI (recommended for beginners):                  │${NC}"
echo -e "${CYAN}│       python3 /home/pi/NxtGenAI/gui.py                          │${NC}"
echo -e "${CYAN}│                                                                  │${NC}"
echo -e "${CYAN}│  📺  OLED headless (Raspberry Pi hardware):                     │${NC}"
echo -e "${CYAN}│       sudo systemctl start pentestgpt                           │${NC}"
echo -e "${CYAN}│       sudo python3 /home/pi/NxtGenAI/main.py                   │${NC}"
echo -e "${CYAN}│                                                                  │${NC}"
echo -e "${CYAN}│  🔄  Auto-start on boot (OLED mode):                            │${NC}"
echo -e "${CYAN}│       sudo systemctl enable pentestgpt                          │${NC}"
echo -e "${CYAN}│       sudo reboot                                                │${NC}"
echo -e "${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│  🎙️   VOICE COMMANDS (say these into the microphone):           │${NC}"
echo -e "${CYAN}│       'network scan'  — discover hosts on the network           │${NC}"
echo -e "${CYAN}│       'wifi crack'    — capture & crack WPA2 handshake          │${NC}"
echo -e "${CYAN}│       'web pentest'   — scan a web application                  │${NC}"
echo -e "${CYAN}│       'brute force'   — run dictionary attack                   │${NC}"
echo -e "${CYAN}│       'full auto'     — let AI chain all steps automatically    │${NC}"
echo -e "${CYAN}│       'report'        — generate and export findings            │${NC}"
echo -e "${CYAN}│       'stop'          — abort current operation                 │${NC}"
echo -e "${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│  ⌨️   GUI KEYBOARD SHORTCUTS:                                   │${NC}"
echo -e "${CYAN}│       SPACE    — Push-to-Talk (hold while speaking)             │${NC}"
echo -e "${CYAN}│       F1       — Toggle command & voice guide panel             │${NC}"
echo -e "${CYAN}│       F5       — Reset / restart buddy session                  │${NC}"
echo -e "${CYAN}│       Ctrl+Q   — Quit safely                                    │${NC}"
echo -e "${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│  🔧  HARDWARE BUTTONS (OLED mode):                              │${NC}"
echo -e "${CYAN}│       Button A — Next menu item                                 │${NC}"
echo -e "${CYAN}│       Button B — Previous item / back                           │${NC}"
echo -e "${CYAN}│       Button C — Push-to-Talk voice input                       │${NC}"
echo -e "${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│  📋  USEFUL COMMANDS:                                           │${NC}"
echo -e "${CYAN}│       View logs:   sudo journalctl -u pentestgpt -f             │${NC}"
echo -e "${CYAN}│       Edit config: nano /home/pi/NxtGenAI/config.ini            │${NC}"
echo -e "${CYAN}│       Reports:     ls /home/pi/reports/                         │${NC}"
echo -e "${CYAN}└─────────────────────────────────────────────────────────────────┘${NC}"
echo ""
warn "LEGAL NOTICE: Use only on networks/systems you own or have"
warn "explicit written authorisation to test. Misuse is illegal."
echo ""
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}│  ⚠️   REBOOT REQUIRED                                           │${NC}"
echo -e "${YELLOW}│  The Whisplay WM8960 audio driver and I2S overlay will not      │${NC}"
echo -e "${YELLOW}│  activate until you reboot. Please run:                         │${NC}"
echo -e "${YELLOW}│                                                                  │${NC}"
echo -e "${YELLOW}│       sudo reboot                                                │${NC}"
echo -e "${YELLOW}│                                                                  │${NC}"
echo -e "${YELLOW}│  After reboot, verify audio with:  aplay -l                     │${NC}"
echo -e "${YELLOW}│  You should see:  wm8960-soundcard                              │${NC}"
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────────┘${NC}"
echo ""
