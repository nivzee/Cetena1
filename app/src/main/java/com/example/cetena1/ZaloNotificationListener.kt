package com.example.cetena1

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.os.Bundle
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1, notification)
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            val pkg = sbn.packageName ?: ""
            if (!pkg.contains("zalo")) return

            val notification = sbn.notification
            val extras = notification.extras
            val title = extras.getString(Notification.EXTRA_TITLE) ?: ""
            
            Log.e("ZaloListener", "🔔 Nhận thông báo từ: $pkg | Tiêu đề: $title")

            // 1. Thử lấy từ MessagingStyle (Dành cho Android 13/14)
            val messages = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
            if (messages != null && messages.isNotEmpty()) {
                for (msg in messages) {
                    if (msg is Bundle) {
                        val text = msg.getCharSequence("text")?.toString() ?: ""
                        val senderNode = msg.getCharSequence("sender")?.toString() ?: title
                        Log.e("ZaloListener", "📩 MessagingStyle: $senderNode -> $text")
                        processAndSend(senderNode, text)
                    }
                }
                return // Đã xử lý xong bằng MessagingStyle
            }

            // 2. Thử lấy từ các nguồn text thông thường
            val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
            val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString() ?: ""
            val lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)

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
            Log.e("ZaloListener", "❌ Lỗi khi quét thông báo: ${e.message}")
        }
    }

    private fun processAndSend(sender: String, message: String) {
        if (message.isBlank() || message == "Tin nhắn" || message.contains("đang chạy")) return
        
        // CHẶN TRÙNG TOÀN HỆ THỐNG
        val sharedPrefs = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val lastMsg = sharedPrefs.getString("last_sent_msg", "")
        val lastTime = sharedPrefs.getLong("last_sent_time", 0)
        val currentTime = System.currentTimeMillis()

        if (message == lastMsg && (currentTime - lastTime) < 3000) {
            return // Đã gửi tin này trong 3 giây qua, bỏ qua
        }

        Log.e("ZaloListener", "🚀 GỬI INBOUND (NOTIF): $sender -> $message")
        
        sharedPrefs.edit()
            .putString("last_active_contact", sender)
            .putString("last_sent_msg", message)
            .putLong("last_sent_time", currentTime)
            .apply()

        sendToMessageCenter(sender, message)
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        Log.e("ZaloListener", "❌ Service Inbound bị ngắt kết nối! Đang thử yêu cầu re-bind...")
        // Yêu cầu re-bind nếu Android 7.0+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            requestRebind(android.content.ComponentName(this, ZaloNotificationListener::class.java))
        }
    }

    private fun sendToMessageCenter(sender: String, message: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val defaultUrl = "https://subalated-invincibly-sudie.ngrok-free.dev/webhook/zalo"
        val url = sharedPref.getString("server_url", "") ?: ""
        val finalUrl = if (url.isBlank()) defaultUrl else url

        val json = """{"sender": "$sender", "message": "$message", "platform": "ZALO", "direction": "INBOUND"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
        val request = Request.Builder()
            .url(finalUrl)
            .post(body)
            .addHeader("ngrok-skip-browser-warning", "true")
            .build()
        
        Log.e("ZaloListener", "📡 Đang gửi tới $finalUrl: $json")

        NetworkClient.instance.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloListener", "❌ GỬI THẤT BẠI tới $finalUrl: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                val code = response.code
                if (response.isSuccessful) {
                    Log.e("ZaloListener", "✅ GỬI THÀNH CÔNG (HTTP $code)")
                } else {
                    val bodyStr = response.body?.string() ?: ""
                    Log.e("ZaloListener", "⚠️ SERVER TRẢ LỖI (HTTP $code): $bodyStr")
                }
                response.close()
            }
        })
    }
}
