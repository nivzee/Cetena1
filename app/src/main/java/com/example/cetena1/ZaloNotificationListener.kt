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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Cetena Sync", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Cetena1 đang chạy")
            .setContentText("Đang giám sát tin nhắn Zalo...")
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .build()
        startForeground(1, notification)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            if (!sbn.packageName.contains("zalo")) return

            val notification = sbn.notification
            val extras = notification.extras
            
            // Lấy tiêu đề và nội dung
            val title = extras.getString(Notification.EXTRA_TITLE) ?: ""
            val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""

            // Bỏ qua các thông báo hệ thống của Zalo hoặc thông báo trống
            if (text.isBlank() || title.contains("Zalo") || text.contains("đang chạy")) return

            // Tạo chữ ký để tránh gửi trùng (trong vòng 1 giây)
            val currentSignature = "$title|$text"
            if (currentSignature == lastMessageSignature) return
            lastMessageSignature = currentSignature

            Log.e("ZaloListener", "📩 Inbound từ Notification: $title - $text")
            
            // Cập nhật người dùng hoạt động gần nhất
            getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
                .edit().putString("last_active_contact", title).apply()

            sendToMessageCenter(title, text)

        } catch (e: Exception) {
            Log.e("ZaloListener", "Lỗi: ${e.message}")
        }
    }

    private fun sendToMessageCenter(sender: String, message: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val serverUrl = sharedPref.getString("server_url", "") ?: ""
        if (serverUrl.isEmpty()) return

        val client = OkHttpClient()
        val json = """{"sender": "$sender", "message": "$message", "platform": "ZALO", "direction": "INBOUND"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
        val request = Request.Builder().url(serverUrl).post(body).build()
        
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloListener", "Gửi Inbound thất bại: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                response.close()
            }
        })
    }
}
