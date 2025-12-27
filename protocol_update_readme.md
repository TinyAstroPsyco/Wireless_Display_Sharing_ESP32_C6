# ESP32 Desktop Monitor - 16-bit Coordinate Protocol Update

## Overview

This document explains how to modify the ESP32-Desktop-Monitor protocol to support displays larger than 255×255 pixels by upgrading from 8-bit to 16-bit coordinates.

## Problem Statement

The original protocol uses **8-bit (1 byte)** coordinates, limiting displays to **255×255 pixels maximum**.

```
Original limits:
- X coordinate: 0-255 (uint8_t)
- Y coordinate: 0-255 (uint8_t)
- Maximum resolution: 255×255
```

For displays like the **ESP32-C6-LCD-1.47 (172×320)**, the Y coordinate (320) exceeds 255, causing:
```
struct.error: ubyte format requires 0 <= number <= 255
```

## Solution: 16-bit Coordinates

Upgrade to **16-bit (2 bytes)** coordinates, supporting displays up to **65,535×65,535 pixels**.

```
New limits:
- X coordinate: 0-65,535 (uint16_t)
- Y coordinate: 0-65,535 (uint16_t)
- Maximum resolution: 65,535×65,535
```

---

## Protocol Specification

### Original Protocol (8-bit)

#### PXUP - Pixel Update Packets
```
Header (11 bytes):
┌─────────┬─────────┬──────────┬───────┐
│ Magic   │ Version │ Frame ID │ Count │
│ 4 bytes │ 1 byte  │ 4 bytes  │ 2 bytes│
└─────────┴─────────┴──────────┴───────┘
  "PXUP"     0x02      uint32    uint16

Body (4 bytes per pixel):
┌───┬───┬───────┐
│ X │ Y │ Color │
│ 1 │ 1 │ 2     │
└───┴───┴───────┘
```

#### PXUR - Run Update Packets
```
Header (11 bytes):
┌─────────┬─────────┬──────────┬───────┐
│ Magic   │ Version │ Frame ID │ Count │
│ 4 bytes │ 1 byte  │ 4 bytes  │ 2 bytes│
└─────────┴─────────┴──────────┴───────┘
  "PXUR"     0x01      uint32    uint16

Body (5 bytes per run):
┌───┬────┬────────┬───────┐
│ Y │ X0 │ Length │ Color │
│ 1 │ 1  │ 1      │ 2     │
└───┴────┴────────┴───────┘
```

### New Protocol (16-bit)

#### PXUP - Pixel Update Packets (v3)
```
Header (11 bytes): UNCHANGED
┌─────────┬─────────┬──────────┬───────┐
│ Magic   │ Version │ Frame ID │ Count │
│ 4 bytes │ 1 byte  │ 4 bytes  │ 2 bytes│
└─────────┴─────────┴──────────┴───────┘
  "PXUP"     0x03      uint32    uint16
             ^^^^
             NEW VERSION

Body (6 bytes per pixel):  ← +2 bytes
┌─────┬─────┬───────┐
│ X   │ Y   │ Color │
│ 2   │ 2   │ 2     │
└─────┴─────┴───────┘
uint16 uint16 uint16
```

#### PXUR - Run Update Packets (v2)
```
Header (11 bytes): UNCHANGED
┌─────────┬─────────┬──────────┬───────┐
│ Magic   │ Version │ Frame ID │ Count │
│ 4 bytes │ 1 byte  │ 4 bytes  │ 2 bytes│
└─────────┴─────────┴──────────┴───────┘
  "PXUR"     0x02      uint32    uint16
             ^^^^
             NEW VERSION

Body (8 bytes per run):  ← +3 bytes
┌─────┬─────┬────────┬───────┐
│ Y   │ X0  │ Length │ Color │
│ 2   │ 2   │ 2      │ 2     │
└─────┴─────┴────────┴───────┘
uint16 uint16 uint16  uint16
```

---

## Implementation Guide

### Step 1: Update Transmitter (Python)

**File:** `transmitter.py`

#### Change 1: Display Dimensions (lines 33-34)
```python
# OLD:
DISPLAY_WIDTH = 135
DISPLAY_HEIGHT = 240

# NEW:
DISPLAY_WIDTH = 179   # Your display width
DISPLAY_HEIGHT = 320  # Your display height
```

#### Change 2: Protocol Versions (lines 35-36)
```python
# OLD:
HEADER_VERSION = 0x02      # PXUP version
RUN_HEADER_VERSION = 0x01  # PXUR version

# NEW:
HEADER_VERSION = 0x03      # PXUP v3 (16-bit coords)
RUN_HEADER_VERSION = 0x02  # PXUR v2 (16-bit coords)
```

#### Change 3: Pixel Packet Format (line 343)
```python
# OLD:
append(struct.pack("<BBH", int(x), int(y), int(color)))
#                   ^ ^ ^
#                   1 1 2 bytes = 4 bytes total

# NEW:
append(struct.pack("<HHH", int(x), int(y), int(color)))
#                   ^ ^ ^
#                   2 2 2 bytes = 6 bytes total
```

#### Change 4: Run Packet Format (line 393)
```python
# OLD:
append(struct.pack("<BBBH", y, x0, length, color))
#                   ^ ^ ^ ^
#                   1 1 1 2 bytes = 5 bytes total

# NEW:
append(struct.pack("<HHHH", y, x0, length, color))
#                   ^ ^ ^ ^
#                   2 2 2 2 bytes = 8 bytes total
```

---

### Step 2: Update Receiver (Arduino)

**File:** `receiver.ino` (or your modified version)

#### Change 1: Protocol Versions
```cpp
// OLD:
const uint8_t PIXEL_PROTOCOL_VERSION = 2;
const uint8_t RUN_PROTOCOL_VERSION = 1;

// NEW:
const uint8_t PIXEL_PROTOCOL_VERSION = 3;  // PXUP v3
const uint8_t RUN_PROTOCOL_VERSION = 2;    // PXUR v2
```

#### Change 2: Display Dimensions
```cpp
// OLD:
const uint16_t SCREEN_WIDTH = 135;
const uint16_t SCREEN_HEIGHT = 240;

// NEW:
const uint16_t SCREEN_WIDTH = 179;   // Your display width
const uint16_t SCREEN_HEIGHT = 320;  // Your display height
```

#### Change 3: Pixel Update Struct
```cpp
// OLD:
struct PixelUpdate {
  uint8_t x;      // 1 byte (0-255)
  uint8_t y;      // 1 byte (0-255)
  uint16_t color; // 2 bytes (RGB565)
} __attribute__((packed));  // Total: 4 bytes

// NEW:
struct PixelUpdate {
  uint16_t x;     // 2 bytes (0-65535) ✅
  uint16_t y;     // 2 bytes (0-65535) ✅
  uint16_t color; // 2 bytes (RGB565)
} __attribute__((packed));  // Total: 6 bytes
```

#### Change 4: Run Update Struct
```cpp
// OLD:
struct RunUpdate {
  uint8_t y;       // 1 byte (0-255)
  uint8_t x0;      // 1 byte (0-255)
  uint8_t length;  // 1 byte (0-255)
  uint16_t color;  // 2 bytes (RGB565)
} __attribute__((packed));  // Total: 5 bytes

// NEW:
struct RunUpdate {
  uint16_t y;      // 2 bytes (0-65535) ✅
  uint16_t x0;     // 2 bytes (0-65535) ✅
  uint16_t length; // 2 bytes (0-65535) ✅
  uint16_t color;  // 2 bytes (RGB565)
} __attribute__((packed));  // Total: 8 bytes
```

---

## struct.pack Format Codes Reference

| Code | Type | Size | Range |
|------|------|------|-------|
| `B` | unsigned byte | 1 byte | 0 to 255 |
| `H` | unsigned short | 2 bytes | 0 to 65,535 |
| `I` | unsigned int | 4 bytes | 0 to 4,294,967,295 |

**Little-endian (`<`)**: Least significant byte first (ESP32 byte order)

**Examples:**
```python
struct.pack("<BBH", 50, 100, 0xF800)
#            ^ ^ ^
#            | | +-- 2 bytes for color
#            | +---- 1 byte for Y (max 255)
#            +------ 1 byte for X (max 255)

struct.pack("<HHH", 300, 100, 0xF800)
#            ^ ^ ^
#            | | +-- 2 bytes for color
#            | +---- 2 bytes for Y (max 65535) ✅
#            +------ 2 bytes for X (max 65535) ✅
```

---

## Testing Procedure

### 1. Test Compilation

**Python:**
```bash
python -c "import transmitter; print('OK')"
```

**Arduino:**
- Compile and check for errors
- Look for "Sketch uses X bytes" message

### 2. Test Basic Connection

```bash
python transmitter.py --ip <ESP32_IP>
```

**Expected Serial Monitor output:**
```
New client connected!
Magic bytes: 50 58 55 50
Processing X pixel updates
  Pixel: (123,200) color=0xF800
```

### 3. Test with Full Frame

```bash
python transmitter.py --ip <ESP32_IP> --full-frame
```

Should see display update with your screen content.

### 4. Test with Delta Mode

```bash
python transmitter.py --ip <ESP32_IP>
```

Move windows around, verify only changed pixels update.

### 5. Verify Large Coordinates

Add debug output in Arduino:
```cpp
Serial.print("X=");
Serial.print(update.x);
Serial.print(" Y=");
Serial.println(update.y);
```

Look for Y values > 255 to confirm 16-bit coordinates work.

---

## Bandwidth Comparison

### Old Protocol (8-bit):
- Pixel packet: 4 bytes per pixel
- Run packet: 5 bytes per run

### New Protocol (16-bit):
- Pixel packet: 6 bytes per pixel (+50%)
- Run packet: 8 bytes per run (+60%)

**Impact:** ~50-60% more bandwidth, but negligible for WiFi (typically <1 MB/s)

**Example:**
- 1000 pixels/frame × 6 bytes = 6 KB/frame
- At 15 FPS = 90 KB/second (well within WiFi capacity)

---

## Troubleshooting

### "struct.error: ubyte format requires 0 <= number <= 255"
- **Cause:** Still using old 8-bit format in transmitter
- **Fix:** Verify you changed `"<BBH"` to `"<HHH"` and `"<BBBH"` to `"<HHHH"`

### "Unsupported protocol version"
- **Cause:** Transmitter and receiver have mismatched versions
- **Fix:** Verify both use v3 for PXUP and v2 for PXUR

### Display shows garbage
- **Cause:** Struct packing mismatch
- **Fix:** Ensure `__attribute__((packed))` is present on structs

### No display updates
- **Cause:** Coordinates out of bounds
- **Fix:** Verify `SCREEN_WIDTH` and `SCREEN_HEIGHT` match your display

### Connection drops frequently
- **Cause:** Packets too large for buffer
- **Fix:** Reduce `--max-updates-per-frame` to 1500

---

## Summary of Changes

| Component | Lines Changed | Summary |
|-----------|---------------|---------|
| **transmitter.py** | 33-34 | Update `DISPLAY_WIDTH` and `DISPLAY_HEIGHT` |
| **transmitter.py** | 35-36 | Bump protocol versions to v3/v2 |
| **transmitter.py** | 343 | Change `"<BBH"` → `"<HHH"` |
| **transmitter.py** | 393 | Change `"<BBBH"` → `"<HHHH"` |
| **receiver.ino** | Protocol versions | Update to v3/v2 |
| **receiver.ino** | `PixelUpdate` struct | `uint8_t` → `uint16_t` for x,y |
| **receiver.ino** | `RunUpdate` struct | `uint8_t` → `uint16_t` for y,x0,length |

**Total changes:** ~10 lines of code across 2 files

---

## Backward Compatibility

**The new protocol is NOT backward compatible.** Mixing old and new versions will result in:
- "Unsupported protocol version" errors
- Corrupt display output
- Connection failures

**Solution:** Always update BOTH transmitter and receiver together.

---

## Future Enhancements

1. **Dynamic protocol negotiation**: Auto-detect 8-bit vs 16-bit capability
2. **Compression**: Add zlib compression for large updates
3. **Multi-display**: Support multiple ESP32 receivers
4. **UDP option**: Reduce latency with UDP instead of TCP

---

## License

This modification maintains compatibility with the original ESP32-Desktop-Monitor license.

## Credits

- Original project: [tuckershannon/ESP32-Desktop-Monitor](https://github.com/tuckershannon/ESP32-Desktop-Monitor)
- Protocol modification: Community contribution for larger display support

---

## Support

For issues specific to this protocol modification:
1. Verify both transmitter and receiver are updated
2. Check Serial Monitor for error messages
3. Test with `--full-frame` first
4. Ensure display dimensions match in both files

For original project issues, refer to the [original repository](https://github.com/tuckershannon/ESP32-Desktop-Monitor).
