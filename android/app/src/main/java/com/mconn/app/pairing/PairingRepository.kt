package com.mconn.app.pairing

import android.content.Context
import android.os.Build
import android.util.Base64
import com.mconn.app.queue.AppDatabase
import com.mconn.app.queue.PairedPcEntity
import com.mconn.app.transfer.PinnedClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException

/**
 * Completes pairing from the QR payload (DESIGN.md 2.2).
 * TODO(Phase 1): camera QR scanner (CameraX + ML Kit). Until then the UI accepts the payload as pasted text,
 * which the PC admin page also shows.
 */
class PairingRepository(private val context: Context) {
    suspend fun claim(encodedPayload: String): Result<PairedPcEntity> = withContext(Dispatchers.IO) {
        runCatching {
            val p = JSONObject(String(Base64.decode(encodedPayload.trim(), Base64.URL_SAFE), Charsets.UTF_8))
            require(p.getInt("v") == 1) { "Unsupported pairing payload version" }
            check(p.getLong("exp") > System.currentTimeMillis() / 1000) { "This QR code has expired" }

            val hosts = p.getJSONArray("hosts").let { a -> List(a.length()) { a.getString(it) } }
            val port = p.getInt("port")
            val client = PinnedClient.build(p.getString("cert_sha256"), connectSec = 5, readSec = 130) // PC user must approve
            val body = JSONObject()
                .put("token", p.getString("token"))
                .put("device_name", Build.MODEL)
                .put("public_key", DeviceKeys.publicKeyBase64())
                .toString().toRequestBody("application/json".toMediaType())

            var lastIo: IOException? = null
            for (host in hosts) {
                try {
                    val req = Request.Builder().url("https://$host:$port/v1/pair/claim").post(body).build()
                    client.newCall(req).execute().use { resp ->
                        val json = JSONObject(resp.body?.string().orEmpty())
                        check(resp.isSuccessful) { json.optString("message", "Pairing failed (HTTP ${resp.code})") }
                        val pc = PairedPcEntity(
                            pcId = json.getString("pc_id"),
                            pcName = json.getString("pc_name"),
                            deviceId = json.getString("device_id"),
                            certSha256 = p.getString("cert_sha256"),
                            lastGoodHost = host,
                            hostsJson = JSONArray(hosts).toString(),
                            port = port,
                            pairedAt = System.currentTimeMillis(),
                        )
                        AppDatabase.get(context).pairedPc().upsert(pc)
                        return@runCatching pc
                    }
                } catch (e: IOException) {
                    lastIo = e // host unreachable: try the next one
                }
            }
            throw lastIo ?: IllegalStateException("The QR code contains no hosts")
        }
    }
}
