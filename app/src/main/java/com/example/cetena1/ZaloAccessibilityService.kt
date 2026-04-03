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

    private var tempMessage: String = ""
    private var lastInboundMessage: String = ""
    private var lastKnownContact: String = "Người dùng Zalo"

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: ""
        if (!pkg.contains("zalo")) return

        try {
            val rootNode = rootInActiveWindow ?: return
            
            // Cập nhật tên người đang chat liên tục
            val currentContact = findContactName(rootNode)
            if (currentContact != "Người dùng Zalo") {
                lastKnownContact = currentContact
                getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
                    .edit().putString("last_active_contact", currentContact).apply()
            }

            when (event.eventType) {
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                    val text = event.text.joinToString("")
                    if (text.isNotBlank() && text != "[]") tempMessage = text
                }

                AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                    if (tempMessage.isNotBlank()) {
                        // Nếu vẫn là mặc định, lấy từ bộ nhớ đệm SharedPreferences
                        val finalSender = if (lastKnownContact != "Người dùng Zalo") {
                            lastKnownContact
                        } else {
                            getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
                                .getString("last_active_contact", "Người dùng Zalo") ?: "Người dùng Zalo"
                        }
                        
                        Log.e("ZaloTracker", "🚀 GỬI OUTBOUND: $tempMessage TỚI $finalSender")
                        sendToMessageCenter(finalSender, tempMessage, "OUTBOUND")
                        tempMessage = "" 
                    }
                }

                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED, AccessibilityEvent.TYPE_VIEW_SCROLLED -> {
                    val screenMsg = findLatestInboundOnScreen(rootNode)
                    if (screenMsg.isNotBlank() && screenMsg != lastInboundMessage && screenMsg != tempMessage) {
                        lastInboundMessage = screenMsg
                        val finalSender = if (lastKnownContact != "Người dùng Zalo") lastKnownContact else "Người dùng Zalo"
                        sendToMessageCenter(finalSender, screenMsg, "INBOUND")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloTracker", "Lỗi: ${e.message}")
        }
    }

    private fun findContactName(rootNode: AccessibilityNodeInfo): String {
        // Danh sách ID tiêu đề Zalo (Cập nhật mới nhất)
        val ids = arrayOf(
            "com.zing.zalo:id/chat_title_name", 
            "com.vng.zalo:id/chat_title_name", 
            "com.zing.zalo:id/tv_header_title",
            "com.vng.zalo:id/tv_header_title"
        )
        for (id in ids) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (!nodes.isNullOrEmpty()) {
                val name = nodes[0].text?.toString() ?: ""
                if (name.isNotBlank()) return name
            }
        }
        
        // Nếu không thấy ID, tìm kiếm Node có khả năng là tiêu đề (thường nằm ở top)
        return scanTopForName(rootNode)
    }

    private fun scanTopForName(node: AccessibilityNodeInfo?): String {
        if (node == null) return "Người dùng Zalo"
        // Tiêu đề Zalo thường là TextView ở phía trên màn hình
        if (node.className == "android.widget.TextView" && node.isClickable == false) {
            val text = node.text?.toString() ?: ""
            // Thường tên người chat sẽ không quá dài và không chứa các ký tự lạ
            if (text.length in 2..30 && !text.contains(":") && !text.contains("/") && text != "Zalo") {
                return text
            }
        }
        for (i in 0 until node.childCount) {
            val result = scanTopForName(node.getChild(i))
            if (result != "Người dùng Zalo") return result
        }
        return "Người dùng Zalo"
    }

    private fun findLatestInboundOnScreen(rootNode: AccessibilityNodeInfo): String {
        val messageIds = arrayOf("com.zing.zalo:id/msg_text", "com.vng.zalo:id/msg_text")
        for (id in messageIds) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            if (!nodes.isNullOrEmpty()) return nodes.last().text?.toString() ?: ""
        }
        return ""
    }

    private fun sendToMessageCenter(name: String, message: String, direction: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val url = sharedPref.getString("server_url", "") ?: return
        
        val json = """{"sender": "$name", "message": "$message", "platform": "ZALO", "direction": "$direction"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
        val request = Request.Builder()
            .url(url)
            .post(body)
            .addHeader("ngrok-skip-browser-warning", "true")
            .build()
        
        NetworkClient.instance.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) { response.close() }
        })
    }

    override fun onInterrupt() {}
}
