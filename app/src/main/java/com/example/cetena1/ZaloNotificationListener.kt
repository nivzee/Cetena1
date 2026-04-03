package com.example.cetena1

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class ZaloNotificationListener : NotificationListenerService() {

    private val CHANNEL_ID = "CetenaSyncChannel"
    private var lastSentMessage: String = ""

    override fun onCreate() {
        super.onCreate()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Cetena Sync", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.e("ZaloListener", "✅ Service Inbound đã sẵn sàng")
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Cetena1")
            .setContentText("Đang theo dõi tin nhắn đến...")
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .build()
        startForeground(1, notification)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            if (!sbn.packageName.contains("zalo")) return

            val extras = sbn.notification.extras
            val title = extras.getString(Notification.EXTRA_TITLE) ?: ""
            
            // QUÉT SÂU: Thử lấy tin nhắn từ nhiều nguồn khác nhau trong thông báo
            val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
            val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString() ?: ""
            val titleBig = extras.getCharSequence(Notification.EXTRA_TITLE_BIG)?.toString() ?: ""
            val lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)

            Log.e("ZaloListener", "🔍 Scan: title=$title, text=$text, bigText=$bigText")

            if (!lines.isNullOrEmpty()) {
                for (line in lines) {
                    processAndSend(title, line.toString())
                }
            } else if (bigText.isNotBlank()) {
                processAndSend(title, bigText)
            } else if (text.isNotBlank()) {
                processAndSend(title, text)
            }

        } catch (e: Exception) {
            Log.e("ZaloListener", "Lỗi: ${e.message}")
        }
    }

    private fun processAndSend(sender: String, message: String) {
        // Lọc các thông báo không phải tin nhắn
        if (message.isBlank() || sender.contains("Zalo") || message.contains("đang chạy") || message == "Tin nhắn") return
        
        // Chống trùng lặp nhanh
        if (message == lastSentMessage) return
        lastSentMessage = message

        Log.e("ZaloListener", "📩 PHÁT HIỆN INBOUND: $sender -> $message")
        
        // Cập nhật SharedPreferences
        getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
            .edit().putString("last_active_contact", sender).apply()

        sendToMessageCenter(sender, message)
    }

    private fun sendToMessageCenter(sender: String, message: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val serverUrl = sharedPref.getString("server_url", "") ?: return

        val json = """{"sender": "$sender", "message": "$message", "platform": "ZALO", "direction": "INBOUND"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
        val request = Request.Builder()
            .url(serverUrl)
            .post(body)
            .addHeader("ngrok-skip-browser-warning", "true")
            .build()
        
        NetworkClient.instance.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) { response.close() }
        })
    }
}
