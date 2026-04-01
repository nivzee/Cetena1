package com.example.cetena1

import android.content.Context
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.cetena1.ui.theme.Cetena1Theme
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            Cetena1Theme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    SettingsScreen()
                }
            }
        }
    }
}

@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    val sharedPref = remember { context.getSharedPreferences("CetenaPrefs", Context.MODE_PRIVATE) }
    
    var serverUrl by remember { 
        mutableStateOf(sharedPref.getString("server_url", "https://subalated-invincibly-sudie.ngrok-free.dev/webhook/zalo") ?: "") 
    }
    var statusText by remember { mutableStateOf("Sẵn sàng") }

    Column(modifier = Modifier.padding(20.dp).fillMaxWidth()) {
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
                Toast.makeText(context, "Đã lưu cấu hình!", Toast.LENGTH_SHORT).show()
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("1. LƯU CẤU HÌNH")
        }
        
        Spacer(modifier = Modifier.height(10.dp))

        Button(
            onClick = {
                testConnection(serverUrl) { success, message ->
                    statusText = if (success) "✅ Kết nối thành công!" else "❌ Lỗi: $message"
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("2. KIỂM TRA KẾT NỐI (TEST)")
        }

        Spacer(modifier = Modifier.height(20.dp))
        Text(text = "Trạng thái: $statusText", style = MaterialTheme.typography.bodyLarge)
        
        Spacer(modifier = Modifier.height(40.dp))
        Text(
            text = "Lưu ý: Sau khi lưu, hãy Tắt/Bật lại Hỗ trợ tiếp cận và Truy cập thông báo.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.secondary
        )
    }
}

fun testConnection(url: String, onResult: (Boolean, String) -> Unit) {
    if (url.isBlank()) {
        onResult(false, "URL trống")
        return
    }
    val client = OkHttpClient()
    val json = """{"sender": "Test", "message": "Kiểm tra kết nối", "platform": "TEST", "direction": "PING"}"""
    val body = json.toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
    
    val request = try {
        Request.Builder().url(url).post(body).build()
    } catch (e: Exception) {
        onResult(false, "URL sai định dạng")
        return
    }

    client.newCall(request).enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) {
            onResult(false, e.message ?: "Unknown error")
        }
        override fun onResponse(call: Call, response: Response) {
            if (response.isSuccessful) {
                onResult(true, "OK")
            } else {
                onResult(false, "Server trả về lỗi ${response.code}")
            }
            response.close()
        }
    })
}