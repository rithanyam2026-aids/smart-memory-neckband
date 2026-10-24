/**
 * Smart Memory Neckband - ESP32-S3 Main Firmware
 * Senses environment, manages privacy hardware gates, and streams to Python AI service.
 */

#include <Arduino.h>
#include "config.h"
#include "protocol.h"
#include "house_grid.h"
#include "privacy_machine.h"
#include "sensors.h"

HouseGridManager gridManager;
PrivacyStateMachine privacySM;
SensorManager sensorManager;

uint32_t lastHeartbeatMs = 0;
uint32_t lastOutsideSampleMs = 0;
uint32_t outsideIntervalMs = 10000;

void setup() {
    Serial.begin(115200);

    // Hardware Privacy Power Gates Configuration
    pinMode(PIN_CAM_POWER_GATE, OUTPUT);
    pinMode(PIN_MIC_POWER_GATE, OUTPUT);
    pinMode(PIN_STATUS_LED, OUTPUT);

    // Initial safe state: Cut off camera and mic
    digitalWrite(PIN_CAM_POWER_GATE, LOW);
    digitalWrite(PIN_MIC_POWER_GATE, LOW);
    digitalWrite(PIN_STATUS_LED, LOW);

    // In production, initializes LittleFS, loads house_grid.json, connects to phone hotspot Wi-Fi
    Serial.println(F("[FIRMWARE] ESP32-S3 Neckband initialized. Safe SLEEP mode active."));
}

void loop() {
    uint32_t now = millis();

    // 1. Link Liveness & Fail-safe Check
    if (now - lastHeartbeatMs > LINK_LOSS_TIMEOUT_MS) {
        if (privacySM.isLinkAlive) {
            Serial.println(F("[FIRMWARE] Link loss detected! Applying privacy fail-safe."));
            privacySM.setLinkStatus(false);
        }
    }

    // 2. Continuous Sensor Evaluation (Runs in ALL privacy states)
    SensorVitals vitals;
    vitals.pulseBpm = 72.0f; // In production: analogRead(PIN_PULSE_ANALOG)
    vitals.motionStatus = "normal"; // In production: MPU6050 I2C reading

    std::string alertReason;
    if (sensorManager.evaluateEmergencyCondition(vitals, alertReason)) {
        Serial.printf("[FIRMWARE] 🚨 EMERGENCY ALERT: %s\n", alertReason.c_str());
        // In production: packs MSG_EMERGENCY_ALERT and dispatches over link
    }

    // 3. Silence / Departure Check
    privacySM.checkSilenceTimeout(now);

    delay(20);
}
