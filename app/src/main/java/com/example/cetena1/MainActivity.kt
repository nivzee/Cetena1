package com.example.cetena1

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.cetena1.ui.theme.Cetena1Theme

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
    
    var serverIp by remember { 
        mutableStateOf(sharedPref.getString("server_url", "https://subalated-invincibly-sudie.ngrok-free.dev/webhook/zalo") ?: "") 
    }

    Column(modifier = Modifier.padding(20.dp).fillMaxWidth()) {
        Text(text = "Cấu hình Cetena1", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(20.dp))
        
        OutlinedTextField(
            value = serverIp,
            onValueChange = { serverIp = it },
            label = { Text("Địa chỉ Webhook (URL)") },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("https://your-ngrok.ngrok-free.app/webhook/zalo") }
        )
        
        Spacer(modifier = Modifier.height(20.dp))
        
        Button(
            onClick = {
                sharedPref.edit().putString("server_url", serverIp).apply()
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Lưu cấu hình")
        }
        
        Spacer(modifier = Modifier.height(40.dp))
        Text(
            text = "Trạng thái: Đảm bảo đã bật Quyền hỗ trợ tiếp cận và Truy cập thông báo trong Cài đặt.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.secondary
        )
    }
}