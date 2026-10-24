package com.mconn.app.transfer

import android.util.Base64
import com.mconn.app.pairing.DeviceKeys
import java.security.MessageDigest
import java.security.SecureRandom

/** Must match windows-receiver/mconn_receiver/api/auth.py and protocol/transfer-contracts.md section 3. */
object Signing {
    const val UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"

    fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /** METHOD \n PATH[?QUERY] \n TIMESTAMP \n NONCE \n BODY_SHA256 (UTF-8). Pure function, unit-tested. */
    fun canonical(method: String, pathAndQuery: String, timestamp: String, nonce: String, bodySha256: String): ByteArray =
        listOf(method.uppercase(), pathAndQuery, timestamp, nonce, bodySha256).joinToString("\n").toByteArray(Charsets.UTF_8)
}

class RequestSigner(private val deviceId: String) {
    private val random = SecureRandom()

    /** @param bodySha256Hex hex SHA-256 of the raw body, or null for a streamed upload (UNSIGNED-PAYLOAD). */
    fun headers(method: String, pathAndQuery: String, bodySha256Hex: String?): Map<String, String> {
        val timestamp = (System.currentTimeMillis() / 1000).toString()
        val nonce = ByteArray(16).also(random::nextBytes).let { Base64.encodeToString(it, URL_SAFE_NO_PAD) }
        val message = Signing.canonical(method, pathAndQuery, timestamp, nonce, bodySha256Hex ?: Signing.UNSIGNED_PAYLOAD)
        val signature = Base64.encodeToString(DeviceKeys.sign(message), URL_SAFE_NO_PAD)
        return mapOf(
            "X-MConn-Device" to deviceId,
            "X-MConn-Timestamp" to timestamp,
            "X-MConn-Nonce" to nonce,
            "X-MConn-Signature" to signature,
        )
    }

    private companion object {
        const val URL_SAFE_NO_PAD = Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP
    }
}
