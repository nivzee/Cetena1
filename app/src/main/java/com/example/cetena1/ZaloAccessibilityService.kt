package com.example.cetena1

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class ZaloAccessibilityService : AccessibilityService() {

    private var tempMessage: String = ""
    private var lastKnownContact: String = "Người dùng Zalo"
    private val handler = Handler(Looper.getMainLooper())

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.e("ZaloTracker", "✅ DỊCH VỤ TRUY CẬP ĐÃ SẴN SÀNG")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: ""
        if (!pkg.contains("zalo")) return

        try {
            val rootNode = rootInActiveWindow ?: return
            
            // Tìm tên người đang chat (ưu tiên quét liên tục)
            val currentContact = findContactName(rootNode)
            if (currentContact != "Người dùng Zalo") {
                lastKnownContact = currentContact
            }

            when (event.eventType) {
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                    val source = event.source
                    if (source?.isEditable == true) {
                        val text = event.text.joinToString("")
                        val beforeText = event.beforeText?.toString() ?: ""
                        Log.e("ZaloTracker", "⌨️ TEXT_CHANGED: '$beforeText' -> '$text'")

                        if (text.isBlank() && tempMessage.isNotBlank()) {
                            // Ô nhập liệu bị xóa sạch -> Thường là do nhấn Gửi hoặc Xóa hết
                            val messageToProcess = tempMessage
                            Log.e("ZaloTracker", "⌨️ Ô nhập liệu trống, kích hoạt quét Outbound dự phòng cho: $messageToProcess")
                            
                            handler.postDelayed({ 
                                // Reset tempMessage ngay lập tức để tránh double trigger
                                tempMessage = ""
                                
                                val currentRoot = rootInActiveWindow
                                if (currentRoot != null) scanScreen(currentRoot) 
                                
                                // Nếu scanScreen không tìm thấy (do lag), ta vẫn CHỐT dựa trên nội dung đã gõ
                                Log.e("ZaloTracker", "🎯 CHỐT OUTBOUND (DỰ PHÒNG TEXT_EMPTY): $messageToProcess")
                                processAndSend(lastKnownContact, messageToProcess, "OUTBOUND")
                            }, 500) 
                        } else if (text != "Tin nhắn" && text.isNotBlank()) {
                            tempMessage = text
                        }
                    }
                }

                AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                    val source = event.source
                    if (source != null) {
                        val viewId = source.viewIdResourceName ?: ""
                        val desc = source.contentDescription?.toString() ?: ""
                        val rect = Rect()
                        source.getBoundsInScreen(rect)
                        Log.e("ZaloTracker", "🖱 Click: ID=$viewId, Desc=$desc, Rect=$rect, Class=${source.className}")

                        if (isSendButton(source) || isSendButton(source.parent)) {
                            if (tempMessage.isNotBlank()) {
                                Log.e("ZaloTracker", "🎯 PHÁT HIỆN CLICK GỬI: $tempMessage")
                                processAndSend(lastKnownContact, tempMessage, "OUTBOUND")
                                tempMessage = "" 
                            }
                        }
                    } else {
                        // Trường hợp Source null, quét nhanh root để tìm nút gửi hoặc kiểm tra trạng thái ô nhập liệu
                        Log.e("ZaloTracker", "🖱 Click (Source null), đang kiểm tra UI...")
                        handler.postDelayed({ 
                            val root = rootInActiveWindow ?: return@postDelayed
                            val inputNodes = root.findAccessibilityNodeInfosByViewId("com.zing.zalo:id/chat_input_field")
                            val currentText = inputNodes?.firstOrNull()?.text?.toString() ?: ""
                            
                            // Nếu sau khi click mà ô nhập liệu trống hoặc về mặc định, chứng tỏ đã gửi
                            if ((currentText.isBlank() || currentText == "Tin nhắn") && tempMessage.isNotBlank()) {
                                Log.e("ZaloTracker", "🎯 XÁC NHẬN GỬI (Dựa trên UI thay đổi): $tempMessage")
                                processAndSend(lastKnownContact, tempMessage, "OUTBOUND")
                                tempMessage = ""
                            }
                        }, 200)
                    }
                }

                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED, 
                AccessibilityEvent.TYPE_VIEW_SCROLLED,
                AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                    scanScreen(rootNode)
                }
            }
        } catch (e: Exception) {
            Log.e("ZaloTracker", "❌ Error Event: ${e.message}")
        }
    }

    private fun isSendButton(node: AccessibilityNodeInfo?): Boolean {
        if (node == null) return false
        val id = node.viewIdResourceName ?: ""
        val desc = node.contentDescription?.toString()?.lowercase() ?: ""
        val rect = Rect()
        node.getBoundsInScreen(rect)
        
        // Nới lỏng điều kiện cho S21
        val isRightSide = rect.left > 800
        val isBottomArea = rect.top > 2000
        
        return id.contains("send") || id.contains("btn_send") || 
               desc.contains("gửi") || desc.contains("send") ||
               (node.isClickable && isRightSide && isBottomArea)
    }

    private fun scanScreen(rootNode: AccessibilityNodeInfo) {
        val allNodes = mutableListOf<AccessibilityNodeInfo>()
        findAllTextNodes(rootNode, allNodes)

        val candidates = mutableListOf<Triple<String, Int, String>>()

        for (node in allNodes) {
            val content = node.text?.toString() ?: continue
            val rect = Rect()
            node.getBoundsInScreen(rect)

            // Điều chỉnh tọa độ S21: Mở rộng vùng quét (150 < top < 2350)
            if (node.isEditable || rect.top < 150 || rect.top > 2350) continue
            if (rect.left == 0 && rect.width() >= 1080) continue

            val cleanContent = cleanMessage(content)
            if (cleanContent.isBlank() || cleanContent == "Tin nhắn" || cleanContent == lastKnownContact) continue
            
            // Inbound: lệch trái (< 500), Outbound: lệch phải (> 500)
            val direction = if (rect.left < 500) "INBOUND" else "OUTBOUND"
            candidates.add(Triple(cleanContent, rect.top, direction))
        }

        if (candidates.isEmpty()) return

        // Lấy tin nhắn mới nhất ở đáy màn hình (tọa độ top lớn nhất)
        val latest = candidates.maxByOrNull { it.second } ?: return
        val (msgContent, _, msgDir) = latest

        val sharedPrefs = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val lastSent = sharedPrefs.getString("last_sent_msg", "")
        val lastTime = sharedPrefs.getLong("last_sent_time", 0)

        // Chặn trùng lặp trong 2 giây
        if (msgContent == lastSent && (System.currentTimeMillis() - lastTime) < 2000) return

        // Outbound: Chỉ chốt khi khớp chính xác với tempMessage (đang gõ) 
        // hoặc khi click nút gửi đã xóa tempMessage
        if (msgDir == "OUTBOUND") {
            if (tempMessage.isNotBlank() && msgContent != tempMessage) return
        }

        Log.e("ZaloTracker", "🚀 CHỐT TIN (${msgDir} SCAN): $lastKnownContact -> $msgContent")
        processAndSend(lastKnownContact, msgContent, msgDir)
    }

    private fun processAndSend(sender: String, message: String, direction: String) {
        val sharedPrefs = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        sharedPrefs.edit()
            .putString("last_sent_msg", message)
            .putLong("last_sent_time", System.currentTimeMillis())
            .putString("last_active_contact", sender)
            .apply()

        sendToMessageCenter(sender, message, direction)
    }

    private fun findContactName(rootNode: AccessibilityNodeInfo): String {
        // Thử tìm theo ID chuẩn của Zalo
        val idList = arrayOf(
            "com.zing.zalo:id/chat_title_name", 
            "com.vng.zalo:id/chat_title_name", 
            "com.zing.zalo:id/tv_header_title"
        )
        for (id in idList) {
            val nodes = rootNode.findAccessibilityNodeInfosByViewId(id)
            for (node in nodes ?: emptyList()) {
                val name = node.text?.toString() ?: ""
                val cleanName = cleanMessage(name)
                if (cleanName.length >= 2 && cleanName != "Tin nhắn" && !cleanName.contains("truy cập", true)) {
                    return cleanName
                }
            }
        }
        return lastKnownContact
    }

    private fun cleanMessage(raw: String): String {
        var t = raw.replace(Regex("[\\u00A0\\u2007\\u202F]"), " ")
        t = t.replace("\n", " ").trim()
        
        val tLower = t.lowercase()
        
        // Chỉ chặn nếu là NHÃN TRẠNG THÁI (độ dài ngắn và khớp hoàn toàn/bắt đầu bằng)
        val statusLabels = arrayOf(
            "vừa xong", "hôm qua", "hôm nay", "đang gõ", "đã xem", 
            "đã nhận", "đã gửi", "đã chuyển", "trả lời", "vừa mới truy cập"
        )
        
        for (label in statusLabels) {
            if (tLower == label || (tLower.startsWith(label) && t.length < label.length + 5)) {
                return ""
            }
        }

        if (t.length < 2 || t == "Tin nhắn" || t.matches(Regex("^\\d{1,2}:\\d{2}$"))) return ""

        return t
    }

    private fun findAllTextNodes(root: AccessibilityNodeInfo?, list: MutableList<AccessibilityNodeInfo>) {
        if (root == null) return
        try {
            if (root.text != null && root.text.isNotBlank()) list.add(root)
            for (i in 0 until root.childCount) {
                val child = root.getChild(i)
                if (child != null) findAllTextNodes(child, list)
            }
        } catch (e: Exception) {}
    }

    private fun sendToMessageCenter(name: String, message: String, direction: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        // Cung cấp URL mặc định nếu người dùng chưa bấm Lưu
        val defaultUrl = "https://subalated-invincibly-sudie.ngrok-free.dev/webhook/zalo"
        val url = sharedPref.getString("server_url", "") ?: ""
        val finalUrl = if (url.isBlank()) defaultUrl else url
        
        val json = """{"sender": "$name", "message": "$message", "platform": "ZALO", "direction": "$direction"}"""
        val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
        val request = Request.Builder()
            .url(finalUrl)
            .post(body)
            .addHeader("ngrok-skip-browser-warning", "true")
            .build()

        Log.e("ZaloTracker", "📡 Đang gửi tới $finalUrl: $json")

        NetworkClient.instance.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloTracker", "❌ GỬI THẤT BẠI tới $finalUrl: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                val code = response.code
                val bodyStr = response.body?.string() ?: ""
                if (response.isSuccessful) {
                    Log.e("ZaloTracker", "✅ GỬI THÀNH CÔNG (HTTP $code)")
                } else {
                    Log.e("ZaloTracker", "⚠️ SERVER TRẢ LỖI (HTTP $code): $bodyStr")
                }
                response.close()
            }
        })
    }

    override fun onInterrupt() {}
}
