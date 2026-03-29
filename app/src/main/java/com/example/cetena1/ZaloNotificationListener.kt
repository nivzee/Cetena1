package com.example.cetena1

import android.app.Notification
import android.content.Context
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class ZaloNotificationListener : NotificationListenerService() {

    private var lastMessageSignature: String = ""

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.e("ZaloListener", "✅ Service nghe thông báo đã SẴN SÀNG!")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            if (sbn.isOngoing) return

            val packageName = sbn.packageName
            if (packageName == "com.zing.zalo" || packageName == "com.vng.zalo") {
                val extras = sbn.notification.extras
                val title = extras.getString(Notification.EXTRA_TITLE) ?: "Không tên"
                val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""

                Log.d("ZaloListener", "Nhận thông báo từ $title: $text")

                val currentSignature = "$title|$text"
                if (title.isNotEmpty() && text.isNotEmpty() && currentSignature != lastMessageSignature) {
                    lastMessageSignature = currentSignature
                    sendToMessageCenter(title, text)
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloListener", "Lỗi xử lý thông báo: ${e.message}")
        }
    }

    private fun sendToMessageCenter(sender: String, message: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val serverUrl = sharedPref.getString("server_url", "")
        
        if (serverUrl.isNullOrEmpty()) {
            Log.e("ZaloListener", "❌ Chưa có URL server!")
            return
        }

        val client = OkHttpClient()
        val json = """{"sender": "$sender", "message": "$message", "platform": "ZALO", "direction": "INBOUND"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())

        val request = Request.Builder().url(serverUrl).post(body).build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloListener", "Gửi Inbound thất bại: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                Log.d("ZaloListener", "✅ Đã gửi thành công Inbound tới PC")
                response.close()
            }
        })
    }
}