package com.mconn.app.share

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.mconn.app.MConnApp
import kotlinx.coroutines.launch

/**
 * Appears in the system Share menu. Template behaviour: send immediately, no confirmation sheet.
 * TODO(Phase 1): optional confirmation sheet (name, size, PC status) per DESIGN.md 2.3.
 */
class ShareReceiverActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val uris = extractUris(intent)
        if (uris.isEmpty()) {
            Toast.makeText(this, "MConn can only send files, not plain text", Toast.LENGTH_LONG).show()
            finish()
            return
        }
        lifecycleScope.launch {
            val pc = (application as MConnApp).db.pairedPc().get()
            if (pc == null) {
                Toast.makeText(this@ShareReceiverActivity, "Pair MConn with your PC first", Toast.LENGTH_LONG).show()
                finish()
                return@launch
            }
            var queued = 0
            for (uri in uris) {
                runCatching { FileStager.stageAndEnqueue(applicationContext, uri, pc) }
                    .onSuccess { queued++ }
                    .onFailure { Toast.makeText(this@ShareReceiverActivity, "Could not read file: ${it.message}", Toast.LENGTH_LONG).show() }
            }
            if (queued > 0) Toast.makeText(this@ShareReceiverActivity, "Queued $queued file(s) for ${pc.pcName}", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    @Suppress("DEPRECATION")
    private fun extractUris(intent: Intent): List<Uri> = when (intent.action) {
        Intent.ACTION_SEND ->
            listOfNotNull(
                if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else intent.getParcelableExtra(Intent.EXTRA_STREAM) as? Uri
            )
        Intent.ACTION_SEND_MULTIPLE ->
            (if (Build.VERSION.SDK_INT >= 33) intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
            else intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)).orEmpty()
        else -> emptyList()
    }
}
