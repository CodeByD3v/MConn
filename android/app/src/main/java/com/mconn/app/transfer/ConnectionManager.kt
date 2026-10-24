package com.mconn.app.transfer

import android.content.Context
import com.mconn.app.queue.AppDatabase
import com.mconn.app.queue.PairedPcEntity
import org.json.JSONArray

sealed interface Connection {
    data class Connected(val api: MConnApi, val host: String) : Connection
    data object Unreachable : Connection
    data class Rejected(val code: String, val message: String) : Connection
}

/**
 * Tries hosts in order (DESIGN.md 3.4): last good host, then the hosts from the pairing QR (LAN, then Tailscale).
 * TODO(Phase 0 spike): add NsdManager (mDNS `_mconn._tcp`) discovery before the QR hosts.
 */
class ConnectionManager(context: Context) {
    private val db = AppDatabase.get(context)

    suspend fun connect(pc: PairedPcEntity): Connection {
        val probeClient = PinnedClient.build(pc.certSha256, connectSec = 3, readSec = 3)
        val transferClient = probeClient.newBuilder()
            .readTimeout(java.time.Duration.ofSeconds(120)) // the receiver hashes large files before replying
            .writeTimeout(java.time.Duration.ofSeconds(60))
            .build()
        val signer = RequestSigner(pc.deviceId)

        val hosts = (listOfNotNull(pc.lastGoodHost) + JSONArray(pc.hostsJson).let { a -> List(a.length()) { a.getString(it) } })
            .distinct()
        for (host in hosts) {
            val probe = MConnApi("https://$host:${pc.port}", probeClient, signer)
            when (val r = probe.status()) {
                is ApiResult.Ok -> {
                    if (host != pc.lastGoodHost) db.pairedPc().setLastGoodHost(pc.pcId, host)
                    return Connection.Connected(MConnApi("https://$host:${pc.port}", transferClient, signer), host)
                }
                is ApiResult.Reject -> return Connection.Rejected(r.code, r.message)
                else -> Unit // unreachable or transient: try the next host
            }
        }
        return Connection.Unreachable
    }
}
