/*
 * ESP32 Desktop Monitor - Receiver for ESP32-C6-LCD-1.47
 * This receives pixel updates over WiFi and displays them on the LCD
 */

#include <WiFi.h>
#include <Arduino_GFX_Library.h>

// ==================== CONFIGURATION ====================


// WiFi Credentials 
const char* ssid = "Your SSID";
const char* password = "Password";
// TCP server port
const uint16_t SERVER_PORT = 8090;

// Display pins for ESP32-C6-LCD-1.47
#define TFT_SCK   7
#define TFT_MOSI  6
#define TFT_CS    14
#define TFT_DC    15
#define TFT_RST   21
#define TFT_BL    22

// Screen dimensions - using your working configuration, mine are set to the waveshare LCD 1.47" display with esp32 c6 board on board
const uint16_t SCREEN_WIDTH = 179;   // Your working width
const uint16_t SCREEN_HEIGHT = 320;  // Your working height

// Protocol constants
const uint8_t PIXEL_PROTOCOL_VERSION = 2;  // PXUP uses version 2
const uint8_t RUN_PROTOCOL_VERSION = 1;    // PXUR uses version 1
const char PIXEL_UPDATE_MAGIC[] = "PXUP";  // Individual pixel updates
const char RUN_UPDATE_MAGIC[] = "PXUR";     // Run-length encoded updates

// ==================== GLOBALS ====================

WiFiServer server(SERVER_PORT);
WiFiClient client;

// Display setup - using your working configuration
Arduino_DataBus *bus = new Arduino_ESP32SPI(TFT_DC, TFT_CS, TFT_SCK, TFT_MOSI, -1);
Arduino_GFX *gfx = new Arduino_ST7789(
  bus, 
  TFT_RST, 
  0,              // rotation = 0 (portrait)
  true,           // IPS display
  179,            // width (your working value)
  320,            // height (your working value)
  30,             // col_offset (your working value), this is what worked for me
  0               // row_offset
);

// Frame buffer for batch updates
uint16_t* frameBuffer = nullptr;
bool useFrameBuffer = false;

// Statistics
unsigned long lastFrameTime = 0;
unsigned long frameCount = 0;
float fps = 0.0;

// ==================== PACKET STRUCTURES ====================

struct PixelPacketHeader {
  char magic[4];        // "PXUP"
  uint8_t version;      // Protocol version
  uint32_t frameId;     // Frame identifier
  uint16_t count;       // Number of pixel updates
} __attribute__((packed));

struct PixelUpdate {
  uint8_t x;
  uint8_t y;
  uint16_t color;  // RGB565
} __attribute__((packed));

struct RunPacketHeader {
  char magic[4];        // "PXUR"
  uint8_t version;      // Protocol version
  uint32_t frameId;     // Frame identifier
  uint16_t count;       // Number of run updates
} __attribute__((packed));

struct RunUpdate {
  uint16_t y;
  uint16_t x0;
  uint16_t length;
  uint16_t color;  // RGB565
} __attribute__((packed));

// ==================== HELPER FUNCTIONS ====================

void displayIPAddress() {
  gfx->fillScreen(0x0000);  // Black
  gfx->setTextColor(0xFFFF); // White
  gfx->setTextSize(2);
  
  gfx->setCursor(10, 10);
  gfx->println("ESP32-C6");
  gfx->setCursor(10, 35);
  gfx->println("Desktop Monitor");
  
  gfx->setTextSize(1);
  gfx->setCursor(10, 70);
  gfx->println("Waiting for connection");
  gfx->setCursor(10, 85);
  gfx->print("IP: ");
  gfx->println(WiFi.localIP());
  gfx->setCursor(10, 100);
  gfx->print("Port: ");
  gfx->println(SERVER_PORT);
  
  Serial.println("\n=================================");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
  Serial.print("Port: ");
  Serial.println(SERVER_PORT);
  Serial.println("=================================\n");
}

void displayConnectionStatus(bool connected) {
  if (connected) {
    gfx->fillScreen(0x07E0);  // Green
    gfx->setTextColor(0x0000); // Black
    gfx->setTextSize(2);
    gfx->setCursor(20, SCREEN_HEIGHT/2 - 10);
    gfx->println("Connected!");
    delay(1000);
    gfx->fillScreen(0x0000);  // Clear to black
  } else {
    displayIPAddress();
  }
}

// Read exact number of bytes from client
bool readExact(uint8_t* buffer, size_t length) {
  size_t totalRead = 0;
  unsigned long timeout = millis() + 5000;  // 5 second timeout
  
  while (totalRead < length && millis() < timeout) {
    if (!client.connected()) {
      return false;
    }
    
    size_t available = client.available();
    if (available > 0) {
      size_t toRead = min(available, length - totalRead);
      size_t read = client.read(buffer + totalRead, toRead);
      totalRead += read;
    } else {
      delay(1);  // Small delay to prevent tight loop
    }
  }
  
  return totalRead == length;
}

// These functions are no longer needed - packet processing is inline in loop()

// ==================== SETUP ====================

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=================================");
  Serial.println("ESP32-C6 Desktop Monitor Receiver");
  Serial.println("=================================");
  
  // Initialize backlight at LOW brightness to reduce heat
  pinMode(TFT_BL, OUTPUT);
  analogWrite(TFT_BL, 50);  // Only 20% brightness instead of 100%
  
  // Initialize display
  Serial.println("Initializing display...");
  gfx->begin();
  gfx->fillScreen(0x0000);  // Black
  
  // Display startup message
  gfx->setTextColor(0xFFFF); // White
  gfx->setTextSize(2);
  gfx->setCursor(10, 10);
  gfx->println("Starting...");
  
  // Connect to WiFi with power saving
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  
  gfx->setTextSize(1);
  gfx->setCursor(10, 50);
  gfx->print("WiFi: ");
  gfx->println(ssid);
  
  WiFi.mode(WIFI_STA);
  
  // Reduce WiFi power to save energy and reduce heat
  // Options: WIFI_POWER_19_5dBm, WIFI_POWER_19dBm, WIFI_POWER_18_5dBm, 
  //          WIFI_POWER_17dBm, WIFI_POWER_15dBm, WIFI_POWER_13dBm, 
  //          WIFI_POWER_11dBm, WIFI_POWER_8_5dBm, WIFI_POWER_7dBm, 
  //          WIFI_POWER_5dBm, WIFI_POWER_2dBm, WIFI_POWER_MINUS_1dBm
  WiFi.setTxPower(WIFI_POWER_15dBm);  // Reduce from max (19.5dBm), 15dBm was the sweet spot for me
  
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    gfx->print(".");
    attempts++;
  }
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nFailed to connect to WiFi!");
    gfx->setTextColor(0xF800); // Red
    gfx->setCursor(10, 100);
    gfx->println("WiFi Failed!");
    while(1) { delay(1000); }
  }
  
  Serial.println("\nWiFi connected!");
  
  // Start TCP server
  server.begin();
  Serial.println("TCP server started");
  
  // Display IP address
  displayIPAddress();
  
  // gfx->flush() does not work daaaaam
  Serial.println("Ready to receive screen data");
}

// ==================== MAIN LOOP ====================

void loop() {
  // Check for new client connection
  if (!client || !client.connected()) {
    if (client) {
      Serial.println("Client disconnected");
      client.stop();
      displayConnectionStatus(false);
    }
    
    // Wait for new connection
    client = server.available();
    if (client) {
      Serial.println("New client connected!");
      Serial.print("Client IP: ");
      Serial.println(client.remoteIP());
      displayConnectionStatus(true);
      lastFrameTime = millis();
      frameCount = 0;
    }
    return;
  }
  
  // Check for incoming data
  if (client.available() >= 11) {  // Need at least header size (4 + 1 + 4 + 2 = 11 bytes)
    // Read magic bytes to determine packet type
    char magic[4];
    for (int i = 0; i < 4; i++) {
      magic[i] = client.read();
    }
    
    // Debug: print what we received
    Serial.print("Magic bytes: ");
    for (int i = 0; i < 4; i++) {
      Serial.print((int)(uint8_t)magic[i], HEX);
      Serial.print(" ");
    }
    Serial.println();
    
    bool success = false;
    if (memcmp(magic, PIXEL_UPDATE_MAGIC, 4) == 0) {
      // Already read magic, so adjust processPixelPacket to skip it
      PixelPacketHeader header;
      memcpy(header.magic, magic, 4);
      
      // Read rest of header
      if (!readExact(((uint8_t*)&header) + 4, sizeof(header) - 4)) {
        Serial.println("Failed to read pixel packet header");
        return;
      }
      
      // Verify version
      if (header.version != PIXEL_PROTOCOL_VERSION) {
        Serial.print("Unsupported pixel protocol version: ");
        Serial.print(header.version);
        Serial.print(" (expected ");
        Serial.print(PIXEL_PROTOCOL_VERSION);
        Serial.println(")");
        return;
      }
      
      // Read and apply pixel updates
      Serial.print("Processing ");
      Serial.print(header.count);
      Serial.println(" pixel updates");
      
      for (uint16_t i = 0; i < header.count; i++) {
        PixelUpdate update;
        if (!readExact((uint8_t*)&update, sizeof(update))) {
          Serial.println("Failed to read pixel update");
          return;
        }
        
        if (update.x < SCREEN_WIDTH && update.y < SCREEN_HEIGHT) {
          gfx->drawPixel(update.x, update.y, update.color);  // Changed from writePixel
          
          // Debug first few pixels
          if (i < 3) {
            Serial.print("  Pixel: (");
            Serial.print(update.x);
            Serial.print(",");
            Serial.print(update.y);
            Serial.print(") color=0x");
            Serial.println(update.color, HEX);
          }
        }
      }
      
      // Force display update
      gfx->flush();
      
      success = true;
      
    } else if (memcmp(magic, RUN_UPDATE_MAGIC, 4) == 0) {
      // Already read magic, so adjust processRunPacket to skip it
      RunPacketHeader header;
      memcpy(header.magic, magic, 4);
      
      // Read rest of header
      if (!readExact(((uint8_t*)&header) + 4, sizeof(header) - 4)) {
        Serial.println("Failed to read run packet header");
        return;
      }
      
      // Verify version
      if (header.version != RUN_PROTOCOL_VERSION) {
        Serial.print("Unsupported run protocol version: ");
        Serial.print(header.version);
        Serial.print(" (expected ");
        Serial.print(RUN_PROTOCOL_VERSION);
        Serial.println(")");
        return;
      }
      
      // Read and apply run updates
      Serial.print("Processing ");
      Serial.print(header.count);
      Serial.println(" run updates");
      
      for (uint16_t i = 0; i < header.count; i++) {
        RunUpdate update;
        if (!readExact((uint8_t*)&update, sizeof(update))) {
          Serial.println("Failed to read run update");
          return;
        }
        
        // Draw horizontal line
        if (update.y < SCREEN_HEIGHT && update.x0 < SCREEN_WIDTH) {
          uint8_t endX = min((int)(update.x0 + update.length), (int)SCREEN_WIDTH);
          
          // Debug first run
          if (i < 3) {
            Serial.print("  Run: y=");
            Serial.print(update.y);
            Serial.print(" x0=");
            Serial.print(update.x0);
            Serial.print(" len=");
            Serial.print(update.length);
            Serial.print(" color=0x");
            Serial.println(update.color, HEX);
          }
          
          // Use drawPixel for runs
          for (uint8_t x = update.x0; x < endX; x++) {
            gfx->drawPixel(x, update.y, update.color);  // Changed from writePixel
          }
        }
      }
      
      // Force display update
      gfx->flush();
      
      success = true;
      
    } else {
      Serial.println("Unknown packet type, discarding...");
      return;
    }
    
    if (success) {
      frameCount++;
      
      // Calculate FPS every second
      unsigned long currentTime = millis();
      if (currentTime - lastFrameTime >= 1000) {
        fps = (float)frameCount * 1000.0 / (float)(currentTime - lastFrameTime);
        Serial.print("FPS: ");
        Serial.println(fps, 1);
        frameCount = 0;
        lastFrameTime = currentTime;
      }
    } else {
      Serial.println("Packet processing failed");
      // Don't disconnect on single packet failure, just try to recover
    }
  }
  
  // Longer delay to reduce CPU usage and heat
  delay(10);  // Increased from 1ms to 10ms
}