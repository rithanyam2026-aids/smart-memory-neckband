#pragma once

/**
 * Smart Memory Neckband - ESP32-S3 Hardware Pinout & Configuration
 * Architecture: ESP32-S3 with 8MB Octal PSRAM + LittleFS Flash Storage
 */

// --- Hardware Privacy Power Gates (Physical disconnects for Camera & Mic) ---
#define PIN_CAM_POWER_GATE     21  // MOSFET Gate: HIGH = Camera powered, LOW = Physical cut-off
#define PIN_MIC_POWER_GATE     47  // MOSFET Gate: HIGH = Mic powered, LOW = Physical cut-off

// --- Status LED & Voice Cues ---
#define PIN_STATUS_LED         48  // RGB NeoPixel / Visual indicator: Green=Active, Blue=Sleep, Red=Private

// --- Pulse & Motion Sensors (Continuous in ALL privacy states) ---
#define PIN_PULSE_ANALOG       1   // ADC1_CH0: Optical PPG Pulse Sensor
#define PIN_I2C_SDA            4   // MPU6050 / LSM6DS3 Accelerometer & Gyroscope
#define PIN_I2C_SCL            5

// --- Optional GPS UART ---
#define PIN_GPS_RX             19  // NEO-6M / NEO-8M UART RX
#define PIN_GPS_TX             20  // NEO-6M / NEO-8M UART TX

// --- I2S Digital Microphone (INMP441 / ICS-43434) ---
#define PIN_I2S_MIC_WS         42  // Word Select / L-R Clock
#define PIN_I2S_MIC_SCK        41  // Bit Clock
#define PIN_I2S_MIC_SD         2   // Serial Data In

// --- I2S Class-D Speaker Amplifier (MAX98357A) ---
#define PIN_I2S_SPK_BCLK       15  // Bit Clock
#define PIN_I2S_SPK_LRC        16  // Left/Right Clock
#define PIN_I2S_SPK_DIN        7   // Data Out

// --- Local Wi-Fi Link Parameters ---
#define LINK_PORT              8765
#define LINK_PRESHARED_KEY     "smart_memory_neckband_psk_shared_key_32b_fixed"
#define HEARTBEAT_INTERVAL_MS  1000
#define LINK_LOSS_TIMEOUT_MS   2500
