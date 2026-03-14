# Troubleshooting Guide

This guide covers the most common issues encountered when setting up and running PentestGPT-lite on a Raspberry Pi Zero 2 W.

---

## Table of Contents

- [Setup / Installation Issues](#setup--installation-issues)
- [OLED Display Issues](#oled-display-issues)
- [LLM / AI Issues](#llm--ai-issues)
- [WiFi / Pentest Tool Issues](#wifi--pentest-tool-issues)
- [PiSugar Battery Issues](#pisugar-battery-issues)
- [Voice Input / Output Issues](#voice-input--output-issues)
- [Systemd Service Issues](#systemd-service-issues)
- [Report Export Issues](#report-export-issues)

---

## Setup / Installation Issues

### `setup.sh` fails with "Unexpected architecture"

**Symptom:** Warning during install:
```
[WARN]  Unexpected architecture x86_64 — designed for Raspberry Pi ARMv8
```

**Cause:** You are running on a non-ARM machine (e.g., a desktop PC or CI environment).

**Fix:** The installer is designed for Raspberry Pi OS on ARMv8. Use a Raspberry Pi Zero 2 W. For development on a desktop, see [docs/development.md](development.md).

---

### `pip install` fails during `llama-cpp-python` compilation

**Symptom:**
```
error: command 'cmake' failed: No such file or directory
```

**Fix:** The `build-essential` and `cmake` system packages must be installed first. Re-run `setup.sh` as root, or install them manually:
```bash
sudo apt install build-essential cmake
```

Then reinstall:
```bash
source /home/pi/pentestgpt-venv/bin/activate
CMAKE_ARGS="-DLLAMA_NATIVE=OFF" pip install llama-cpp-python==0.2.90
```

---

### Model file not found at startup

**Symptom:**
```
FileNotFoundError: /home/pi/models/tinyllama-1.1b-q4_0.gguf not found
```

**Fix:** The model was not downloaded during setup. Download it manually:
```bash
wget -O /home/pi/models/tinyllama-1.1b-q4_0.gguf \
  https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf
```

Ensure the path in `config.ini` under `[paths] model` matches the downloaded file.

---

### Out of disk space during install

**Symptom:** `apt-get` or `wget` fails with "No space left on device".

**Fix:**
- Use a microSD card with ≥ 8 GB of space (Class 10 / A1 recommended).
- Remove unnecessary packages: `sudo apt autoremove --purge`
- The TinyLlama model alone is ~620 MB.

---

## OLED Display Issues

### OLED shows nothing after boot

**Possible causes and fixes:**

1. **I2C not enabled:**
   ```bash
   sudo raspi-config
   # Interface Options → I2C → Enable
   sudo reboot
   ```

2. **Wrong I2C address:** Check the detected address:
   ```bash
   i2cdetect -y 1
   ```
   Update `config.ini` under `[oled] i2c_address` to match (usually `0x3C` or `0x3D`).

3. **Loose cable:** Reseat the ribbon cable or header pins on the Waveshare Play Hat.

4. **Wrong I2C bus:** Some Pi models use bus 0. Try `i2cdetect -y 0` and update `config.ini` `[oled] i2c_bus = 0`.

---

### OLED flickers or shows garbled output

**Fix:** Reduce the refresh rate in `config.ini`:
```ini
[oled]
refresh_rate = 0.2
```

---

## LLM / AI Issues

### LLM inference is very slow

**Expected:** TinyLlama on Pi Zero 2 W generates ~3–5 tokens/second. A 200-token response takes ~60 seconds. This is normal.

**Tips to speed up:**
- Reduce `max_tokens` in `config.ini` (e.g., `max_tokens = 100`).
- Increase `n_threads` to 4 (uses all cores, may reduce UI responsiveness).
- Reduce context: `n_ctx = 256`.

---

### LLM produces repetitive or nonsensical output

**Fix:** Increase the `repeat_penalty` in `config.ini`:
```ini
repeat_penalty = 1.2
```

If the problem persists, try a lower `temperature`:
```ini
temperature = 0.2
```

---

### `RuntimeError: Failed to load model`

**Possible causes:**
- Not enough RAM. Check: `free -m`. If available < 250 MB, close other processes.
- Swap not configured. `setup.sh` sets up 64 MB of swap. Verify:
  ```bash
  swapon --show
  ```
  If no swap is shown, create it manually:
  ```bash
  sudo dd if=/dev/zero of=/swapfile bs=1M count=64
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  ```

---

## WiFi / Pentest Tool Issues

### `aircrack-ng` / `aireplay-ng` not found

**Fix:** Install aircrack-ng:
```bash
sudo apt install aircrack-ng
```

---

### Monitor mode fails: "Device or resource busy"

**Symptom:**
```
ioctl(SIOCSIWMODE) failed: Device or resource busy
```

**Fix:** Kill processes that hold the wireless interface:
```bash
sudo airmon-ng check kill
sudo ip link set wlan0 down
sudo iw dev wlan0 set type monitor
sudo ip link set wlan0 up
```

After finishing, restore managed mode:
```bash
sudo ip link set wlan0 down
sudo iw dev wlan0 set type managed
sudo ip link set wlan0 up
sudo systemctl restart NetworkManager  # if installed
```

---

### `nmap` scan returns no results

**Possible causes:**
- Target host is down or unreachable.
- Firewall is blocking ICMP pings. Try a port scan instead:
  ```bash
  nmap -Pn -p 22,80,443 <target>
  ```
- Scan is too slow — Pi Zero 2 W's single-core throughput for nmap is limited. Use `-T3` or lower timing.

---

### `sqlmap` reports "no parameter(s) found"

**Fix:** Ensure you are targeting a URL with parameters, e.g.:
```
http://target/page.php?id=1
```
Adjust the target URL passed to the Web Pentest mode.

---

## PiSugar Battery Issues

### Battery percentage shows 0% or fails to read

**Possible causes:**

1. **PiSugar not detected on I2C:** Verify:
   ```bash
   i2cdetect -y 1
   ```
   You should see `57` in the grid. If not, reseat the PiSugar HAT.

2. **Wrong I2C address:** Update `config.ini`:
   ```ini
   [power]
   pisugar_address = 0x57
   ```

3. **PiSugar firmware not initialised:** Connect a USB-C charger for 10 seconds to wake the PiSugar, then disconnect.

---

### Device shuts down immediately even with full battery

**Fix:** The shutdown threshold may be misconfigured. In `config.ini`:
```ini
[power]
threshold_sleep = 10   # Shutdown below 10%
threshold_warn  = 20   # Warn below 20%
```
Ensure `threshold_sleep` is less than `threshold_warn`.

---

## Voice Input / Output Issues

### No voice output (espeak-ng)

**Check espeak-ng works independently:**
```bash
espeak-ng -v en-gb "hello"
```

If you hear nothing:
- Check audio output: `aplay -l` to list devices.
- The Waveshare Play Hat has a built-in speaker — ensure the volume is not muted.
- If using headphones/speaker: `amixer set PCM 90%`

---

### Voice input not recognised (Vosk)

**Symptom:** Button C hold produces no recognised text.

**Fixes:**
1. Verify the Vosk model is downloaded:
   ```bash
   ls /home/pi/models/vosk-model-small-en-us/
   ```
   If the directory is empty or missing, re-run `setup.sh` or download manually:
   ```bash
   wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
   unzip vosk-model-small-en-us-0.15.zip -d /home/pi/models/
   mv /home/pi/models/vosk-model-small-en-us-0.15 /home/pi/models/vosk-model-small-en-us
   ```
2. Check the microphone input: `arecord -l` — ensure a capture device is listed.
3. Speak closer to the microphone and in a quiet environment.

---

## Systemd Service Issues

### Service fails to start (`systemctl status pentestgpt`)

**View logs:**
```bash
journalctl -u pentestgpt -n 50 --no-pager
```

**Common causes:**
- Python import error — run the script manually to see the full traceback:
  ```bash
  /home/pi/pentestgpt-venv/bin/python /home/pi/NxtGenAI/main.py
  ```
- Missing model file — see [Model file not found](#model-file-not-found-at-startup).
- I2C not enabled — see [OLED shows nothing](#oled-shows-nothing-after-boot).

---

### Service starts but exits immediately

**Fix:** Check the `WorkingDirectory` and `ExecStart` paths in the service file:
```bash
cat /etc/systemd/system/pentestgpt.service
```
Ensure all paths exist. Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart pentestgpt
```

---

## Report Export Issues

### USB export fails ("No USB drive found")

**Possible causes:**
- USB drive is not mounted. Check `lsblk` and `ls /media/pi/`.
- USB drive is formatted as NTFS without the `ntfs-3g` driver:
  ```bash
  sudo apt install ntfs-3g
  ```
- The `usb_mount` path in `config.ini` does not match where the OS mounts the drive.
  Update `[paths] usb_mount` to the correct mount point.
