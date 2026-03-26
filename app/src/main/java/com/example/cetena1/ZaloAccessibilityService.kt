package com.example.cetena1

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class ZaloAccessibilityService : AccessibilityService() {

    private var lastCapturedText: String = ""
    private val client = OkHttpClient()

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.e("ZaloTracker", "==========================================")
        Log.e("ZaloTracker", "✅ SERVICE ĐÃ CHẠY - ĐANG ĐỢI TIN ZALO...")
        Log.e("ZaloTracker", "==========================================")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        try {
            val pkg = event.packageName?.toString() ?: ""
            if (!pkg.contains("zalo")) return

            when (event.eventType) {
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                    val text = event.text.joinToString("")
                    if (text.isNotBlank()) {
                        lastCapturedText = text
                        Log.d("ZaloTracker", "✍️ Đang gõ: $lastCapturedText")
                    }
                }
                AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                    if (lastCapturedText.isNotBlank()) {
                        Log.e("ZaloTracker", "🚀 Phát hiện bấm GỬI! Nội dung: $lastCapturedText")
                        val rootNode = rootInActiveWindow
                        val name = if (rootNode != null) findContactName(rootNode) else "Người dùng Zalo"
                        sendToMessageCenter(name, lastCapturedText)
                        lastCapturedText = "" 
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloTracker", "⚠️ Lỗi xử lý event: ${e.message}")
        }
    }

    private fun findContactName(rootNode: AccessibilityNodeInfo): String {
        val ids = arrayOf(
            "com.zing.zalo:id/chat_title_name", 
            "com.vng.zalo:id/chat_title_name", 
            "com.zing.zalo:id/tv_title",
            "com.zing.zalo:id/name"
        )
        for (id in ids) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (nodes != null && nodes.isNotEmpty()) {
                val name = nodes[0].text?.toString() ?: ""
                if (name.isNotBlank()) return name
            }
        }
        return "Người dùng Zalo"
    }

    private fun sendToMessageCenter(name: String, message: String) {
        try {
            val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
            val url = sharedPref.getString("server_url", "") ?: ""

            if (url.isBlank()) {
                Log.e("ZaloTracker", "❌ CHƯA CÓ URL! Hãy mở App Cetena1 và nhấn LƯU.")
                return
            }

            val json = """{"sender": "$name", "message": "$message", "platform": "ZALO", "direction": "OUTBOUND"}"""
            val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
            val request = Request.Builder().url(url).post(body).build()

            client.newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    Log.e("ZaloTracker", "❌ LỖI MẠNG: ${e.message} - URL: $url")
                }
                override fun onResponse(call: Call, response: Response) {
                    Log.e("ZaloTracker", "✅ ĐÃ GỬI THÀNH CÔNG OUTBOUND TỚI PC!")
                    response.close()
                }
            })
        } catch (e: Exception) {
            Log.e("ZaloTracker", "⚠️ Lỗi gửi tin: ${e.message}")
        }
    }

    override fun onInterrupt() {}
}