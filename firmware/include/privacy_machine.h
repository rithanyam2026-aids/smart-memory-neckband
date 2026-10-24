#pragma once

#include <stdint.h>
#include <string>
#include "house_grid.h"
#include "config.h"

enum PrivacyState {
    PRIVACY_STATE_PRIVATE = 0,
    PRIVACY_STATE_SLEEP   = 1,
    PRIVACY_STATE_ACTIVE  = 2
};

enum LocationStatus {
    LOCATION_INSIDE  = 0,
    LOCATION_OUTSIDE = 1
};

class PrivacyStateMachine {
public:
    PrivacyState currentState = PRIVACY_STATE_SLEEP;
    LocationStatus currentLocation = LOCATION_INSIDE;
    int currentCellRow = 7;
    int currentCellCol = 4;
    std::string currentZone = "Front Entrance Door";

    bool isLinkAlive = true;
    uint32_t lastPersonTimeMs = 0;
    uint32_t activeTimeoutMs = 15000;

    void updateHardwarePowerGates() {
        // Physical GPIO power gating
        #ifdef ARDUINO
        if (currentState == PRIVACY_STATE_ACTIVE) {
            digitalWrite(PIN_CAM_POWER_GATE, HIGH);
            digitalWrite(PIN_MIC_POWER_GATE, HIGH);
            digitalWrite(PIN_STATUS_LED, HIGH); // Green
        } else {
            // Cut power to camera and mic
            digitalWrite(PIN_CAM_POWER_GATE, LOW);
            digitalWrite(PIN_MIC_POWER_GATE, LOW);
            digitalWrite(PIN_STATUS_LED, LOW);
        }
        #endif
    }

    void setLinkStatus(bool alive) {
        isLinkAlive = alive;
        if (!isLinkAlive) {
            // FAILSAFE: If link to AI service is down, never remain in ACTIVE!
            if (currentState == PRIVACY_STATE_ACTIVE) {
                transitionTo(PRIVACY_STATE_SLEEP, "Link to phone AI service dropped. Failsafe to SLEEP.");
            }
        }
    }

    void updatePosition(int r, int c, const HouseGridManager& grid) {
        int prevRow = currentCellRow;
        int prevCol = currentCellCol;
        LocationStatus prevLoc = currentLocation;

        if (grid.isInsideBounds(r, c)) {
            currentLocation = LOCATION_INSIDE;
            currentCellRow = r;
            currentCellCol = c;
            currentZone = grid.getZoneName(r, c);
        } else {
            // Outside grid bounds
            currentLocation = LOCATION_OUTSIDE;
            currentCellRow = -1;
            currentCellCol = -1;
            currentZone = "Outside";
        }

        // Inside House logic
        if (currentLocation == LOCATION_INSIDE) {
            bool isPrivate = grid.isAreaPrivate(currentCellRow, currentCellCol);
            if (isPrivate) {
                if (currentState != PRIVACY_STATE_PRIVATE) {
                    transitionTo(PRIVACY_STATE_PRIVATE, "Entered private room/cell.");
                }
            } else {
                if (currentState == PRIVACY_STATE_PRIVATE) {
                    // Leaving private area -> return to SLEEP (never straight to ACTIVE)
                    transitionTo(PRIVACY_STATE_SLEEP, "Exited private area into normal room. Set to SLEEP.");
                }
            }
        } else {
            // Outside House logic
            if (prevLoc == LOCATION_INSIDE) {
                transitionTo(PRIVACY_STATE_SLEEP, "Exited house through exit. Default state SLEEP.");
            }
        }
    }

    void onOutsideSceneResult(const std::string& classification) {
        if (!isLinkAlive || classification == "UNDECIDED" || classification == "PRIVATE") {
            // Treat as private if toilet detected, link down, or undecided
            if (currentState != PRIVACY_STATE_PRIVATE) {
                transitionTo(PRIVACY_STATE_PRIVATE, "Outside check confirmed private venue or undecided.");
            }
        } else if (classification == "NOT_PRIVATE") {
            if (currentState == PRIVACY_STATE_PRIVATE) {
                transitionTo(PRIVACY_STATE_SLEEP, "Outside check confirmed non-private venue. Return to SLEEP.");
            }
        }
    }

    void onPersonDetected(uint32_t nowMs) {
        // Can only wake to ACTIVE if in SLEEP and link is alive
        if (currentState == PRIVACY_STATE_SLEEP && isLinkAlive) {
            lastPersonTimeMs = nowMs;
            transitionTo(PRIVACY_STATE_ACTIVE, "Person face or voice detected.");
        } else if (currentState == PRIVACY_STATE_ACTIVE) {
            lastPersonTimeMs = nowMs;
        }
    }

    void onPersonDepartedOrSilence() {
        if (currentState == PRIVACY_STATE_ACTIVE) {
            transitionTo(PRIVACY_STATE_SLEEP, "Person departed or silence timeout.");
        }
    }

    void checkSilenceTimeout(uint32_t nowMs) {
        if (currentState == PRIVACY_STATE_ACTIVE) {
            if ((nowMs - lastPersonTimeMs) > activeTimeoutMs) {
                onPersonDepartedOrSilence();
            }
        }
    }

    void transitionTo(PrivacyState newState, const std::string& reason) {
        currentState = newState;
        updateHardwarePowerGates();
    }
};
