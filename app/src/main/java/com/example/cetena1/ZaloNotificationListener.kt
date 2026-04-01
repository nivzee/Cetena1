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

    private var lastMessageSignature: String = ""
    private val CHANNEL_ID = "CetenaSyncChannel"

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.e("ZaloListener", "✅ Service nghe thông báo đã SẴN SÀNG!")
        
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Cetena1 đang chạy ngầm")
            .setContentText("Đang đồng bộ tin nhắn Zalo tới PC...")
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
        
        try {
            startForeground(1, notification)
        } catch (e: Exception) {
            Log.e("ZaloListener", "Lỗi startForeground: ${e.message}")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Cetena Sync Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            val packageName = sbn.packageName
            if (packageName.contains("zalo")) {
                val extras = sbn.notification.extras
                val title = extras.getString(Notification.EXTRA_TITLE) ?: "Zalo User"
                
                // Quét qua nhiều trường dữ liệu khác nhau của Zalo
                val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()
                val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()
                val infoText = extras.getCharSequence(Notification.EXTRA_INFO_TEXT)?.toString()
                
                // Lấy nội dung dài nhất tìm được
                val finalMessage = listOfNotNull(bigText, text, infoText)
                    .maxByOrNull { it.length } ?: ""

                if (finalMessage.isNotBlank() && !sbn.isOngoing) {
                    val currentSignature = "$title|$finalMessage"
                    if (currentSignature != lastMessageSignature) {
                        lastMessageSignature = currentSignature
                        Log.e("ZaloListener", "🔔 Bắt được tin nhắn: $title -> $finalMessage")
                        sendToMessageCenter(title, finalMessage)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloListener", "⚠️ Lỗi xử lý: ${e.message}")
        }
    }

    private fun sendToMessageCenter(sender: String, message: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val serverUrl = sharedPref.getString("server_url", "")
        if (serverUrl.isNullOrEmpty()) return

        val client = OkHttpClient()
        val json = """{"sender": "$sender", "message": "$message", "platform": "ZALO", "direction": "INBOUND"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())

        val request = Request.Builder().url(serverUrl).post(body).build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloListener", "❌ Lỗi mạng: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                response.close()
            }
        })
    }
}