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

    // Các đường dẫn Zalo có thể lưu file/ảnh
    private val zaloPaths = arrayOf(
        "/sdcard/Zalo/Zalo Downloads",
        "/sdcard/Zalo/ZaloReceivedFiles",
        "/sdcard/Zalo/Pictures",
        "/sdcard/Pictures/Zalo",
        "/sdcard/DCIM/Zalo"
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
            .build()
        startForeground(2, notification)
    }

    private fun setupObservers() {
        for (path in zaloPaths) {
            val directory = File(path)
            if (!directory.exists()) {
                Log.e("ZaloFile", "⚠️ Thư mục không tồn tại: $path")
                continue
            }

            val observer = object : FileObserver(directory.path, CREATE or MOVED_TO) {
                override fun onEvent(event: Int, fileName: String?) {
                    if (fileName != null && !fileName.endsWith(".tmp") && !fileName.endsWith(".pending")) {
                        val newFile = File(directory, fileName)
                        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
                        val activeContact = sharedPref.getString("last_active_contact", "Người dùng Zalo") ?: "Người dùng Zalo"
                        
                        Log.e("ZaloFile", "🚀 PHÁT HIỆN FILE: $fileName (Gán cho: $activeContact)")
                        
                        // Đợi file ghi xong hoàn toàn trước khi gửi
                        Handler(Looper.getMainLooper()).postDelayed({
                            sendFileToPC(newFile, activeContact)
                        }, 3000)
                    }
                }
            }
            observer.startWatching()
            observers.add(observer)
            Log.e("ZaloFile", "✅ Đang theo dõi: $path")
        }
    }

    private fun sendFileToPC(file: File, senderName: String) {
        if (!file.exists()) {
            Log.e("ZaloFile", "❌ File đã bị xóa hoặc không thể đọc: ${file.path}")
            return
        }

        val sharedPref = getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE)
        val serverUrl = sharedPref.getString("server_url", "") ?: ""
        if (serverUrl.isEmpty()) return

        val uploadUrl = if (serverUrl.contains("/webhook/zalo")) {
            serverUrl.replace("/webhook/zalo", "/webhook/file")
        } else serverUrl

        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("sender", senderName)
            .addFormDataPart("file", file.name, file.asRequestBody("application/octet-stream".toMediaTypeOrNull()))
            .build()

        val request = Request.Builder().url(uploadUrl).post(requestBody).build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("ZaloFile", "❌ Lỗi mạng khi gửi file: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                if (response.isSuccessful) {
                    Log.e("ZaloFile", "✅ ĐÃ GỬI THÀNH CÔNG: ${file.name}")
                } else {
                    Log.e("ZaloFile", "❌ Server báo lỗi: ${response.code}")
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