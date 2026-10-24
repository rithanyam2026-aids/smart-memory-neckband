#pragma once

#include <stdint.h>
#include <string>

struct SensorVitals {
    float pulseBpm;
    std::string motionStatus; // "normal", "sudden_fall_impact", "immobility"
    float accelG;
    bool hasGpsFix;
    double latitude;
    double longitude;
};

class SensorManager {
public:
    const float CRITICAL_HIGH_PULSE = 130.0f;
    const float CRITICAL_LOW_PULSE  = 40.0f;

    bool evaluateEmergencyCondition(const SensorVitals& vitals, std::string& outReason) {
        bool isPulseAbnormal = (vitals.pulseBpm >= CRITICAL_HIGH_PULSE || vitals.pulseBpm <= CRITICAL_LOW_PULSE);
        bool isMotionCritical = (vitals.motionStatus == "sudden_fall_impact" || vitals.motionStatus == "immobility");

        // STRICT REQUIREMENT: Emergency alert ONLY when pulse AND motion together indicate one!
        if (isPulseAbnormal && isMotionCritical) {
            outReason = "Abnormal pulse combined with critical fall impact or immobility.";
            return true;
        }

        // Pulse alone or motion alone never alerts
        return false;
    }
};
