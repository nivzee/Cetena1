package com.example.cetena1

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.*
import android.util.Log
import androidx.core.app.NotificationCompat
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.io.IOException

class ZaloFileObserverService : Service() {

    private val CHANNEL_ID = "ZaloFileChannel"
    private var observers = mutableListOf<FileObserver>()
    private val client = OkHttpClient()

    // Các đường dẫn Zalo có thể lưu file/ảnh trên Samsung S21 Android 14
    private val zaloPaths = arrayOf(
        "/storage/emulated/0/Zalo/Zalo Downloads",
        "/storage/emulated/0/Zalo/ZaloReceivedFiles",
        "/storage/emulated/0/Zalo/Pictures",
        "/storage/emulated/0/Pictures/Zalo",
        "/storage/emulated/0/DCIM/Zalo",
        "/storage/emulated/0/Download/Zalo"
    )

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startInForeground()
        setupObservers()
    }

    private fun startInForeground() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Zalo File Monitor", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Cetena1 đang giám sát file")
            .setContentText("Đang đợi file mới từ Zalo...")
            .setSmallIcon(android.R.drawable.ic_menu_save)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(2, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(2, notification)
        }
    }

    private fun setupObservers() {
        for (path in zaloPaths) {
            val directory = File(path)
            if (!directory.exists()) {
                // Thử tạo thư mục nếu chưa có (một số máy Samsung tự tạo khi cần)
                try { directory.mkdirs() } catch (e: Exception) {}
            }

            if (directory.exists() && directory.isDirectory) {
                val observer = object : FileObserver(directory.path, CREATE or MOVED_TO) {
                    override fun onEvent(event: Int, fileName: String?) {
                        if (fileName != null && !fileName.endsWith(".tmp") && !fileName.endsWith(".pending")) {
                            Log.e("ZaloFile", "📂 Sự kiện $event trên file: $fileName trong $path")
                            val newFile = File(directory, fileName)
                            
                            // Lấy contact mới nhất từ SharedPreferences ngay tại thời điểm file xuất hiện
                            val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
                            val activeContact = sharedPref.getString("last_active_contact", "Người dùng Zalo") ?: "Người dùng Zalo"
                            
                            // Đợi file ghi xong (đặc biệt quan trọng với ảnh/video dung lượng lớn)
                            Handler(Looper.getMainLooper()).postDelayed({
                                if (newFile.exists() && newFile.length() > 0) {
                                    sendFileToPC(newFile, activeContact)
                                } else {
                                    Log.e("ZaloFile", "⚠️ File chưa sẵn sàng hoặc rỗng: ${newFile.name}")
                                }
                            }, 4000) // Tăng lên 4s cho chắc chắn trên S21
                        }
                    }
                }
                observer.startWatching()
                observers.add(observer)
                Log.e("ZaloFile", "✅ Đang theo dõi: $path")
            }
        }
    }

    private fun sendFileToPC(file: File, senderName: String) {
        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val serverUrl = sharedPref.getString("server_url", "") ?: ""
        if (serverUrl.isEmpty()) return

        // Tự động chuyển đổi endpoint cho file nếu cần
        val uploadUrl = if (serverUrl.contains("/webhook/zalo")) {
            serverUrl.replace("/webhook/zalo", "/webhook/file")
        } else if (!serverUrl.contains("/file")) {
            // Nếu không có định dạng chuẩn, thử thêm /file vào cuối hoặc giữ nguyên
            serverUrl
        } else serverUrl

        Log.e("ZaloFile", "🚀 ĐANG UPLOAD: ${file.name} (Sender: $senderName) -> $uploadUrl")

        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("sender", senderName)
            .addFormDataPart("filename", file.name)
            .addFormDataPart("file", file.name, file.asRequestBody("application/octet-stream".toMediaTypeOrNull()))
            .build()

        val request = Request.Builder()
            .url(uploadUrl)
            .post(requestBody)
            .addHeader("ngrok-skip-browser-warning", "true")
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloFile", "❌ Lỗi mạng: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                if (response.isSuccessful) {
                    Log.e("ZaloFile", "✅ THÀNH CÔNG: ${file.name}")
                } else {
                    Log.e("ZaloFile", "❌ Lỗi server ${response.code}: ${response.message}")
                }
                response.close()
            }
        })
    }

    override fun onDestroy() {
        super.onDestroy()
        observers.forEach { it.stopWatching() }
    }
}
