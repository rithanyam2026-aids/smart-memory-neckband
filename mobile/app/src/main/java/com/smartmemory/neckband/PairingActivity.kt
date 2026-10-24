package com.smartmemory.neckband

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.smartmemory.neckband.service.NeckbandBackgroundService

/**
 * Minimal Setup and Listening Indicator Activity.
 * The only user-facing screen in the mobile app.
 */
class PairingActivity : AppCompatActivity() {

    private lateinit var tvStatusIndicator: TextView
    private lateinit var tvPrivacyNotice: TextView
    private lateinit var etDeviceId: EditText
    private lateinit var etAccountPin: EditText
    private lateinit var btnPair: Button
    private lateinit var btnBatteryOptimization: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_pairing)

        tvStatusIndicator = findViewById(R.id.tvStatusIndicator)
        tvPrivacyNotice = findViewById(R.id.tvPrivacyNotice)
        etDeviceId = findViewById(R.id.etDeviceId)
        etAccountPin = findViewById(R.id.etAccountPin)
        btnPair = findViewById(R.id.btnPair)
        btnBatteryOptimization = findViewById(R.id.btnBatteryOptimization)

        btnPair.setOnClickListener {
            val deviceId = etDeviceId.text.toString().trim()
            val pin = etAccountPin.text.toString().trim()
            if (deviceId.isNotEmpty() && pin.isNotEmpty()) {
                val prefs = getSharedPreferences("smart_neckband_prefs", Context.MODE_PRIVATE)
                prefs.edit().putString("device_id", deviceId).putString("pin", pin).apply()
                Toast.makeText(this, "Neckband and account paired successfully!", Toast.LENGTH_SHORT).show()

                // Start always-on background service
                val serviceIntent = Intent(this, NeckbandBackgroundService::class.java)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent)
                } else {
                    startService(serviceIntent)
                }
                updateIndicator(isListening = false, state = "SLEEP")
            }
        }

        btnBatteryOptimization.setOnClickListener {
            requestIgnoreBatteryOptimization()
        }
    }

    private fun updateIndicator(isListening: Boolean, state: String) {
        if (isListening && state == "ACTIVE") {
            tvStatusIndicator.text = "● LISTENING TO CONVERSATION"
            tvStatusIndicator.setBackgroundColor(0xFF10B981.toInt()) // Green
            tvPrivacyNotice.text = "Microphone active. Whisper transcribing offline on phone. Raw audio is purged immediately."
        } else if (state == "PRIVATE") {
            tvStatusIndicator.text = "🔒 PRIVATE MODE (OFF)"
            tvStatusIndicator.setBackgroundColor(0xFFEF4444.toInt()) // Red
            tvPrivacyNotice.text = "Inside private room or personal facility. Microphones and camera are completely shut down."
        } else {
            tvStatusIndicator.text = "🌙 SLEEP MODE (STANDBY)"
            tvStatusIndicator.setBackgroundColor(0xFF6B7280.toInt()) // Gray
            tvPrivacyNotice.text = "Neckband is sleeping. Waiting for someone to talk or approach."
        }
    }

    private fun requestIgnoreBatteryOptimization() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                }
                startActivity(intent)
            } else {
                Toast.makeText(this, "Battery optimization is already disabled for continuous protection.", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
