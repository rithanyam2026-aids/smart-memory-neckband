#pragma once

#include <stdint.h>

#define PROTOCOL_MAGIC   0x534D
#define PROTOCOL_VERSION 0x01

enum MsgType : uint8_t {
    MSG_HANDSHAKE_HELLO   = 0x01,
    MSG_HANDSHAKE_AUTH    = 0x02,
    MSG_HEARTBEAT_PING    = 0x03,
    MSG_HEARTBEAT_PONG    = 0x04,
    MSG_FRAME_STREAM      = 0x10,
    MSG_AUDIO_CHUNK       = 0x11,
    MSG_SENSOR_TELEMETRY  = 0x12,
    MSG_EMERGENCY_ALERT   = 0x13,
    MSG_OUTSIDE_SAMPLE    = 0x14,
    MSG_OUTSIDE_RESULT    = 0x15,
    MSG_STATE_CHANGE_LOG  = 0x20,
    MSG_SYNC_SETTINGS     = 0x21,
    MSG_SPEAKER_PLAYBACK  = 0x22
};

#pragma pack(push, 1)
struct LinkPacketHeader {
    uint16_t magic;
    uint8_t  version;
    uint8_t  msgType;
    uint16_t flags;
    uint16_t seqNo;
    uint32_t payloadLen;
    uint32_t checksum;
};
#pragma pack(pop)
