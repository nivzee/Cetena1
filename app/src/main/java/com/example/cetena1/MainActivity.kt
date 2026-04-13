package com.example.cetena1

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.os.PowerManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.cetena1.ui.theme.Cetena1Theme
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

object NetworkClient {
    val instance = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startFileService()
        setContent {
            Cetena1Theme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    SettingsScreen(onSave = { startFileService() })
                }
            }
        }
    }

    private fun startFileService() {
        val intent = Intent(this, ZaloFileObserverService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}

@Composable
fun SettingsScreen(onSave: () -> Unit) {
    val context = LocalContext.current
    val sharedPref = remember { context.getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE) }
    val scrollState = rememberScrollState()
    
    var serverUrl by remember { 
        mutableStateOf(sharedPref.getString("server_url", "https://subalated-invincibly-sudie.ngrok-free.dev/webhook/zalo") ?: "") 
    }
    var statusText by remember { mutableStateOf("Sẵn sàng") }

    // Kiểm tra trạng thái quyền liên tục
    val isStorageGranted = remember { mutableStateOf(checkStoragePermission(context)) }

    Column(modifier = Modifier.padding(20.dp).fillMaxWidth().verticalScroll(scrollState)) {
        Text(text = "Cấu hình Cetena1", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(20.dp))
        
        OutlinedTextField(
            value = serverUrl,
            onValueChange = { serverUrl = it },
            label = { Text("Địa chỉ Webhook (URL)") },
            modifier = Modifier.fillMaxWidth()
        )
        
        Spacer(modifier = Modifier.height(10.dp))
        
        Button(
            onClick = {
                sharedPref.edit().putString("server_url", serverUrl).apply()
                Toast.makeText(context, "Đã lưu!", Toast.LENGTH_SHORT).show()
                onSave()
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("1. LƯU CẤU HÌNH")
        }
        
        Spacer(modifier = Modifier.height(10.dp))

        Button(
            onClick = { context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("2. MỞ HỖ TRỢ TIẾP CẬN")
        }

        Spacer(modifier = Modifier.height(10.dp))

        Button(
            onClick = { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("3. MỞ TRUY CẬP THÔNG BÁO")
        }

        Spacer(modifier = Modifier.height(10.dp))

        Button(
            onClick = {
                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:${context.packageName}")
                }
                context.startActivity(intent)
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("3.5. TẮT TỐI ƯU PIN (QUAN TRỌNG)")
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Nút Truy cập file đổi màu nếu đã cấp quyền
        Button(
            onClick = { 
                if (!isStorageGranted.value) {
                    requestStoragePermission(context)
                } else {
                    Toast.makeText(context, "Quyền đã được cấp!", Toast.LENGTH_SHORT).show()
                }
            },
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isStorageGranted.value) Color(0xFF4CAF50) else MaterialTheme.colorScheme.primary
            ),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (isStorageGranted.value) "4. ĐÃ CẤP QUYỀN FILE" else "4. MỞ TRUY CẬP FILE")
        }

        Spacer(modifier = Modifier.height(20.dp))

        Button(
            onClick = {
                statusText = "Đang kiểm tra..."
                testConnection(serverUrl) { success, message ->
                    statusText = if (success) "✅ Kết nối OK!" else "❌ Lỗi: $message"
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("5. KIỂM TRA KẾT NỐI (TEST)")
        }

        Spacer(modifier = Modifier.height(20.dp))
        Text(text = "Trạng thái: $statusText", style = MaterialTheme.typography.bodyLarge)
        
        // Cập nhật lại trạng thái khi quay lại app
        LaunchedEffect(Unit) {
            while(true) {
                isStorageGranted.value = checkStoragePermission(context)
                kotlinx.coroutines.delay(2000)
            }
        }
    }
}

fun checkStoragePermission(context: Context): Boolean {
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        Environment.isExternalStorageManager()
    } else {
        true // Các bản Android cũ hơn mặc định dùng quyền Manifest
    }
}

fun requestStoragePermission(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        intent.data = Uri.parse("package:${context.packageName}")
        context.startActivity(intent)
    }
}

fun testConnection(url: String, onResult: (Boolean, String) -> Unit) {
    if (url.isBlank()) { onResult(false, "URL trống"); return }
    
    val json = """{"sender": "Test", "message": "PING", "direction": "PING"}"""
    val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
    
    val request = Request.Builder()
        .url(url)
        .post(body)
        .addHeader("ngrok-skip-browser-warning", "true")
        .build()

    NetworkClient.instance.newCall(request).enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) {
            onResult(false, e.message ?: "Lỗi")
        }
        override fun onResponse(call: Call, response: Response) {
            onResult(response.isSuccessful, if(response.isSuccessful) "OK" else "Lỗi ${response.code}")
            response.close()
        }
    })
}
