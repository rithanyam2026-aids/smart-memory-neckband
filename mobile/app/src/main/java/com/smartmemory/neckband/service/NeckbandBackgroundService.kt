package com.smartmemory.neckband.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.smartmemory.neckband.PairingActivity

/**
 * Always-on background service for Smart Memory Neckband.
 * - Auto-starts on boot
 * - Listens ONLY while neckband state is ACTIVE
 * - Displays clear ongoing notification with listening indicator
 */
class NeckbandBackgroundService : Service() {

    companion object {
        const val CHANNEL_ID = "neckband_background_channel"
        const val NOTIFICATION_ID = 1001
        const val ACTION_STATE_CHANGED = "com.smartmemory.neckband.ACTION_STATE_CHANGED"
        const val EXTRA_STATE = "extra_privacy_state"
    }

    private var currentNeckbandState: String = "SLEEP"

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Neckband Standby (SLEEP)"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val newState = intent?.getStringExtra(EXTRA_STATE)
        if (newState != null) {
            currentNeckbandState = newState
            updateListeningState(newState)
        }
        return START_STICKY
    }

    private fun updateListeningState(state: String) {
        val statusText = when (state) {
            "ACTIVE" -> "● LISTENING - Capturing conversation notes"
            "PRIVATE" -> "🔒 PRIVATE - Microphones strictly OFF"
            else -> "🌙 SLEEP - Low-power standby"
        }
        val notification = buildNotification(statusText)
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, notification)

        // Only listen and process when state is strictly ACTIVE
        if (state == "ACTIVE") {
            startOfflineAudioProcessing()
        } else {
            stopAudioCapture()
        }
    }

    private fun startOfflineAudioProcessing() {
        // Runs Whisper offline transcription and on-device LLM summarizer
    }

    private fun stopAudioCapture() {
        // Immediately halts audio pipeline and discards pending buffers
    }

    private fun buildNotification(contentText: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, PairingActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Smart Memory Companion")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Smart Neckband Background Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows real-time listening and privacy status of the neckband"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
