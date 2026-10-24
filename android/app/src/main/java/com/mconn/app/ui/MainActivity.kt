package com.mconn.app.ui

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.mconn.app.MConnApp
import com.mconn.app.pairing.PairingRepository
import com.mconn.app.queue.TransferEntity
import com.mconn.app.transfer.TransferScheduler
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { MainScreen() } }
    }
}

@Composable
fun MainScreen() {
    val context = LocalContext.current
    val app = context.applicationContext as MConnApp
    val scope = rememberCoroutineScope()
    val transfers by app.db.transfers().observeAll().collectAsState(initial = emptyList())
    val pc by app.db.pairedPc().observe().collectAsState(initial = null)
    var payload by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }

    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("MConn", style = MaterialTheme.typography.headlineMedium)

        val paired = pc
        if (paired == null) {
            Text("Not paired. On your PC open https://127.0.0.1:8443/admin, click \"Pair new phone\", and paste the pairing text here (QR scanner coming).")
            OutlinedTextField(payload, { payload = it }, label = { Text("Pairing payload") }, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                message = "Waiting for approval on the PC..."
                scope.launch {
                    message = PairingRepository(context).claim(payload).fold({ "Paired with ${it.pcName}" }, { "Pairing failed: ${it.message}" })
                }
            }) { Text("Pair") }
        } else {
            Text("Paired with ${paired.pcName}")
            Button(onClick = { scope.launch { TransferScheduler.resumePending(context) } }) { Text("Retry waiting transfers") }
        }
        message?.let { Text(it) }

        Text("Transfers", style = MaterialTheme.typography.titleMedium)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(transfers, key = { it.transferId }) { TransferRow(it) }
        }
    }
}

@Composable
private fun TransferRow(t: TransferEntity) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(t.displayName, style = MaterialTheme.typography.bodyLarge)
                Text(t.state)
            }
            val pct = if (t.sizeBytes > 0) (t.bytesSent * 100 / t.sizeBytes).toInt() else 100
            Text("${formatSize(t.sizeBytes)}  -  $pct%")
            t.lastErrorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}

private fun formatSize(bytes: Long): String = when {
    bytes >= 1L shl 30 -> "%.1f GiB".format(bytes / (1L shl 30).toDouble())
    bytes >= 1L shl 20 -> "%.1f MiB".format(bytes / (1L shl 20).toDouble())
    bytes >= 1L shl 10 -> "%.1f KiB".format(bytes / (1L shl 10).toDouble())
    else -> "$bytes B"
}
