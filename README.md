# ESP32 Desktop Monitor

Stream your computer screen to an ESP32 display over WiFi. This project enables you to mirror your monitor to small LCD displays connected to ESP32 boards.

## Hardware Requirements

### Supported ESP32 Development Boards

#### Original (TFT_eSPI):
- **Board**: TENSTAR T-Display ESP32-D0WD (or compatible ESP32 with integrated display)
- **Chip**: ESP32-D0WD with CH9102 USB-to-Serial chip
- **Memory**: 16MB Flash
- **Display**: 1.14" ST7789 LCD (135×240 pixels)
- **Connectivity**: WiFi and Bluetooth compatible

#### ESP32-C6 Waveshare (Arduino_GFX):
- **Board**: Waveshare ESP32-C6-LCD-1.47 (or similar)
- **Chip**: ESP32-C6FH8 RISC-V processor
- **Memory**: 8MB Flash
- **Display**: 1.47" ST7789 LCD (172×320 pixels)
- **Connectivity**: WiFi 6 and Bluetooth 5

### Computer
- Any computer running Python 3.7+
- macOS, Linux, or Windows (with appropriate screen capture libraries)

---

## Software Requirements

### ESP32 Side (Arduino IDE)

1. **Arduino IDE** (1.8.x or 2.x) or **PlatformIO**

2. **ESP32 Board Support Package**
   - Add this URL to Arduino IDE Preferences → Additional Board Manager URLs:
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Install "esp32" by Espressif Systems from Board Manager (v2.0.11 or later)

3. **Display Library** (Choose based on your board):

   **Option A: TFT_eSPI** (Original ESP32 boards)
   - Install via Arduino Library Manager
   - Or download from: https://github.com/Bodmer/TFT_eSPI
   - **Important**: Configure `User_Setup.h` for your display
   - **Note**: Not compatible with ESP32-C6

   **Option B: Arduino_GFX** (ESP32-C6 and newer boards)
   - Install via Arduino Library Manager: Search "GFX Library for Arduino" by moononournation
   - Compatible with ESP32-C6, ESP32-S3, and other newer boards
   - No configuration file needed - settings are in your sketch

### Computer Side (Python)

- Python 3.7 or higher
- Required packages (install via `pip install -r requirements.txt`):
  - `opencv-python` - Image processing and scaling
  - `mss` - Cross-platform screen capture
  - `numpy` - Array operations

---

## Setup Instructions

### For ESP32-C6 Waveshare Boards (Arduino_GFX)

#### 1. Configure ESP32-C6 Receiver

1. Open `receiver_esp32c6.ino` in Arduino IDE
2. Update WiFi credentials:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
3. Verify display configuration matches your board:
   ```cpp
   // Pin definitions for Waveshare ESP32-C6-LCD-1.47
   #define TFT_SCK   7
   #define TFT_MOSI  6
   #define TFT_CS    14
   #define TFT_DC    15
   #define TFT_RST   21
   #define TFT_BL    22
   
   // Display dimensions
   const uint16_t SCREEN_WIDTH = 179;   // Adjust for your display
   const uint16_t SCREEN_HEIGHT = 320;
   ```
4. Select board: **Tools → Board → ESP32 Arduino → ESP32C6 Dev Module**
5. Configure board settings:
   - **USB CDC On Boot**: Enabled
   - **Flash Size**: 8MB (or check your board specs)
   - **PSRAM**: Disabled (or OPI PSRAM if your board has it)
6. Select port: **Tools → Port → [Your ESP32-C6 port]**
7. Upload the sketch

#### 2. Find ESP32 IP Address

After uploading, open the Serial Monitor (115200 baud). The ESP32 will:
- Connect to WiFi
- Display its IP address on the screen
- Print the IP address to Serial Monitor

Note the IP address (e.g., `192.168.1.149`).

#### 3. Update Transmitter Resolution

Edit `transmitter.py` (lines 33-34):
```python
DISPLAY_WIDTH = 179   # Match your ESP32 display width
DISPLAY_HEIGHT = 320  # Match your ESP32 display height
```

For displays larger than 255×255, see [PROTOCOL_UPDATE.md](PROTOCOL_UPDATE.md) for 16-bit coordinate upgrade instructions.

---

### For Original ESP32 Boards (TFT_eSPI)

#### 1. Configure ESP32 Receiver

1. Open `receiver.ino` in Arduino IDE
2. Update WiFi credentials:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
3. Configure TFT_eSPI library:
   - Open `User_Setup.h` in the TFT_eSPI library folder (usually `Documents/Arduino/libraries/TFT_eSPI/`)
   - Ensure your display driver (ST7789) is selected
   - Verify pin definitions match your board
   - For T-Display boards, typically:
     ```cpp
     #define ST7789_DRIVER
     #define TFT_WIDTH  135
     #define TFT_HEIGHT 240
     #define TFT_MOSI 19
     #define TFT_SCLK 18
     #define TFT_CS   5
     #define TFT_DC   16
     #define TFT_RST  23
     #define TFT_BL   4
     ```
4. Select board: **Tools → Board → ESP32 Dev Module**
5. Select port: **Tools → Port → [Your ESP32 port]**
6. Upload the sketch

---

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

**macOS users**: Grant "Screen Recording" permission to Terminal (or your Python environment) when prompted.

---

### Run the Transmitter

```bash
python transmitter.py --ip <ESP32_IP_ADDRESS>
```

Replace `<ESP32_IP_ADDRESS>` with the IP address from the Serial Monitor.

---

## Usage

### Basic Usage

```bash
# Stream leftmost monitor to ESP32
python transmitter.py --ip 192.168.1.149

# Stream specific monitor (1-based index)
python transmitter.py --ip 192.168.1.149 --monitor-index 2

# Adjust frame rate (default: 15 FPS)
python transmitter.py --ip 192.168.1.149 --target-fps 20

# Adjust change detection sensitivity (default: 5)
python transmitter.py --ip 192.168.1.149 --threshold 8

# Force full frame updates (no delta encoding)
python transmitter.py --ip 192.168.1.149 --full-frame
```

### Command Line Options

- `--ip <IP>` - ESP32 IP address (required)
- `--port <PORT>` - TCP port (default: 8090)
- `--monitor-index <N>` - Select monitor by index (1-based, default: leftmost)
- `--prefer-largest` - Use largest monitor instead of leftmost
- `--target-fps <FPS>` - Target frame rate (default: 15.0)
- `--threshold <N>` - Pixel change threshold 0-255 (default: 5, higher = less sensitive)
- `--full-frame` - Send all pixels every frame (no diffing, slower)
- `--max-updates-per-frame <N>` - Max pixels per packet (default: 3000)
- `--rotate <0|90|180|270>` - Rotate capture before scaling
- `--show-cursor` - Draw cursor on captured frame (macOS only)

### Performance Tuning

For better frame rates:

1. **Increase threshold** (reduces bandwidth):
   ```bash
   python transmitter.py --ip 192.168.1.149 --threshold 8
   ```

2. **Adjust frame rate**:
   ```bash
   python transmitter.py --ip 192.168.1.149 --target-fps 20
   ```

3. **Increase packet size** (for high-motion content):
   ```bash
   python transmitter.py --ip 192.168.1.149 --max-updates-per-frame 8000
   ```

4. **Reduce WiFi power** (ESP32-C6 - reduces heat):
   ```cpp
   WiFi.setTxPower(WIFI_POWER_11dBm);  // Lower power = less heat
   ```

5. **Lower backlight brightness** (reduces heat):
   ```cpp
   analogWrite(TFT_BL, 80);  // 30% brightness instead of 100%
   ```

---

## How It Works

### Protocol

The system uses a custom TCP-based protocol optimized for small displays:

1. **Frame Diffing**: Only pixels that changed are sent (configurable threshold)
2. **Run-Length Encoding**: Consecutive pixels of the same color are encoded as runs
3. **Automatic Selection**: The sender chooses the most efficient encoding (pixel-by-pixel vs. run-length)
4. **Batched Updates**: All updates for a frame are received before applying to display

### Packet Format

**Pixel Packets** (`PXUP`):
- Header: `'PXUP'` (4 bytes) + version (1 byte) + frame_id (4 bytes) + count (2 bytes)
- Body: `count` entries of `x`, `y`, `color` (RGB565)

**Run Packets** (`PXUR`):
- Header: `'PXUR'` (4 bytes) + version (1 byte) + frame_id (4 bytes) + count (2 bytes)
- Body: `count` entries of `y`, `x0`, `length`, `color` (RGB565)

**Note**: The original protocol uses 8-bit coordinates (max 255×255). For larger displays, see [PROTOCOL_UPDATE.md](PROTOCOL_UPDATE.md) to upgrade to 16-bit coordinates.

### Optimizations

- **High-Speed SPI**: Up to 80MHz SPI clock (configurable)
- **Delta Encoding**: Only transmits changed pixels
- **Run-Length Encoding**: Compresses consecutive same-color pixels
- **TCP_NODELAY**: Disables Nagle's algorithm for lower latency
- **Smart Packet Selection**: Automatically chooses most efficient encoding

---

## Troubleshooting

### ESP32-C6 Specific Issues

#### Display shows nothing or random pixels
- **Cause**: Wrong display library or incorrect pin configuration
- **Fix**: Verify you're using Arduino_GFX (not TFT_eSPI) and pins match your board

#### "writePixel doesn't work" 
- **Cause**: Some Arduino_GFX configurations require `drawPixel()` instead
- **Fix**: The receiver code uses `drawPixel()` which works on all boards

#### ESP32 heating up
- **Causes**: Full brightness backlight, high WiFi power, continuous display updates
- **Fixes**:
  ```cpp
  analogWrite(TFT_BL, 80);              // Lower backlight
  WiFi.setTxPower(WIFI_POWER_11dBm);    // Reduce WiFi power
  ```

#### "struct.error: ubyte format requires 0 <= number <= 255"
- **Cause**: Display resolution exceeds 255 pixels (Y > 255)
- **Fix**: Follow [PROTOCOL_UPDATE.md](PROTOCOL_UPDATE.md) to upgrade to 16-bit coordinates

### General Issues

#### Colors Appear Swapped
```cpp
// Arduino_GFX: Try different color order in display initialization
Arduino_GFX *gfx = new Arduino_ST7789(bus, TFT_RST, 0, true, ...);
//                                                      ^^^^ try false

// TFT_eSPI: Adjust in User_Setup.h
#define TFT_RGB_ORDER TFT_BGR  // or TFT_RGB
```

#### Low Frame Rate
1. Check WiFi signal strength (ESP32 should be close to router)
2. Increase `--threshold` to reduce bandwidth
3. Lower `--target-fps` if network can't keep up
4. Ensure both devices are on same WiFi network (not guest network)
5. Try `--monitor-index` to use correct monitor (3-monitor setups can confuse auto-detection)

#### Display shows blank screen but receives data
- **Serial shows**: "Processing X pixel updates" but screen is blank
- **Cause**: Display offset incorrect or pixels drawn off-screen
- **Fix**: Adjust display offset in receiver code:
  ```cpp
  // Try different offset values
  Arduino_GFX *gfx = new Arduino_ST7789(
    bus, TFT_RST, 0, true, 
    SCREEN_WIDTH, SCREEN_HEIGHT,
    34,  // col_offset - try: 0, 19, 34, 52
    40   // row_offset - try: 0, 40
  );
  ```

#### Connection Issues
1. Verify ESP32 IP address in Serial Monitor
2. Check firewall settings (port 8090 must be open)
3. Ensure both devices are on same network
4. Try restarting the ESP32
5. Ping the ESP32: `ping <ESP32_IP>`

---

## Board Comparison

| Feature | ESP32-D0WD (TFT_eSPI) | ESP32-C6 (Arduino_GFX) |
|---------|----------------------|------------------------|
| **Display Library** | TFT_eSPI | Arduino_GFX |
| **Max Resolution (8-bit)** | 255×255 | 255×255 |
| **Max Resolution (16-bit)** | 65,535×65,535 | 65,535×65,535 |
| **WiFi** | WiFi 4 (802.11n) | WiFi 6 (802.11ax) |
| **Architecture** | Xtensa | RISC-V |
| **Configuration** | User_Setup.h file | In sketch code |
| **Heat Management** | Moderate | Can run hot, needs tuning |

---

## Advanced Configuration

### Display Rotation

Rotate the display to match your preferred orientation:

```cpp
// Arduino_GFX
Arduino_GFX *gfx = new Arduino_ST7789(
  bus, TFT_RST, 
  1,    // rotation: 0=0°, 1=90°, 2=180°, 3=270°
  true, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0
);
```

Don't forget to update transmitter.py dimensions and use `--rotate` flag:
```bash
python transmitter.py --ip <IP> --rotate 90
```

### Multiple Monitors

List available monitors:
```bash
python -c "import mss; sct = mss.mss(); [print(f'Monitor {i}: {m}') for i, m in enumerate(sct.monitors)]"
```

Select specific monitor:
```bash
python transmitter.py --ip <IP> --monitor-index 2
```

---

## Project Files

- `receiver.ino` - ESP32 receiver for TFT_eSPI (original boards)
- `receiver_esp32c6.ino` - ESP32-C6 receiver for Arduino_GFX
- `transmitter.py` - Computer-side screen capture and streaming
- `requirements.txt` - Python dependencies
- `PROTOCOL_UPDATE.md` - Guide for 16-bit coordinate upgrade

---

## Contributing

Contributions welcome! Areas for improvement:
- Support for additional display drivers
- Optimized drawing functions for Arduino_GFX
- Dynamic protocol version negotiation
- Better color space handling
- Performance profiling tools

Please submit issues or pull requests on GitHub.

---

## License

This project is provided as-is for educational and personal use.

---

## Acknowledgments

- Original TFT_eSPI version: [tuckershannon/ESP32-Desktop-Monitor](https://github.com/tuckershannon/ESP32-Desktop-Monitor)
- TFT_eSPI library by Bodmer
- Arduino_GFX library by moononournation
- ESP32 Arduino core by Espressif
- mss library for cross-platform screen capture

---

## Support

For issues:
1. Check Serial Monitor output for error messages
2. Verify WiFi connection and IP address
3. Test with `--full-frame` to isolate delta encoding issues
4. For ESP32-C6: Ensure using Arduino_GFX, not TFT_eSPI
5. For large displays (>255 pixels): See [PROTOCOL_UPDATE.md](PROTOCOL_UPDATE.md)
