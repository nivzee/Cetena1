package com.example.cetena1

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.graphics.Rect
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
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                    val text = event.text.joinToString("")
                    if (text.isNotBlank() && text != "[]") {
                        lastCapturedText = text
                        Log.e("ZaloTracker", "✍️ Đang gõ: $lastCapturedText")
                    }
                }

                AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                    if (lastCapturedText.isNotBlank()) {
                        val rootNode = rootInActiveWindow
                        val name = if (rootNode != null) findContactName(rootNode) else "Người dùng Zalo"
                        
                        Log.e("ZaloTracker", "🚀 GỬI TỚI $name: $lastCapturedText")
                        sendToMessageCenter(name, lastCapturedText)
                        
                        val sentText = lastCapturedText
                        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                            if (lastCapturedText == sentText) lastCapturedText = ""
                        }, 500)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloTracker", "⚠️ Lỗi: ${e.message}")
        }
    }

    private fun findContactName(rootNode: AccessibilityNodeInfo): String {
        // Danh sách ID ưu tiên
        val ids = arrayOf(
            "com.zing.zalo:id/chat_title_name", 
            "com.vng.zalo:id/chat_title_name", 
            "com.zing.zalo:id/tv_header_title",
            "com.zing.zalo:id/tv_title",
            "com.zing.zalo:id/name"
        )
        
        for (id in ids) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (nodes != null && nodes.isNotEmpty()) {
                val name = nodes[0].text?.toString() ?: ""
                nodes.forEach { it.recycle() }
                if (name.isNotBlank()) return name
            }
        }

        // CÁCH DỰ PHÒNG: Tìm mọi TextView nằm ở phần trên cùng màn hình (Header)
        return scanForHeaderTitle(rootNode) ?: "Người dùng Zalo"
    }

    private fun scanForHeaderTitle(node: AccessibilityNodeInfo?): String? {
        if (node == null) return null
        
        // Nếu là TextView và nằm ở vùng Y từ 50 đến 200 (thường là Header)
        if (node.className == "android.widget.TextView") {
            val rect = Rect()
            node.getBoundsInScreen(rect)
            if (rect.top > 50 && rect.top < 200 && rect.height() > 30) {
                val text = node.text?.toString()
                if (!text.isNullOrBlank() && text.length < 50) return text
            }
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i)
            val result = scanForHeaderTitle(child)
            if (result != null) return result
        }
        return null
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
                Log.e("ZaloTracker", "❌ LỖI GỬI: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                Log.e("ZaloTracker", "✅ ĐÃ GỬI THÀNH CÔNG!")
                response.close()
            }
        })
    }

    override fun onInterrupt() {}
}