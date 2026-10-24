package com.mconn.app.transfer

import okhttp3.OkHttpClient
import okhttp3.Protocol
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * HTTPS client that trusts exactly ONE certificate: the receiver's, identified by the SHA-256 fingerprint
 * delivered in the pairing QR (ARCHITECTURE.md AD-4). This replaces CA validation; it never disables it.
 * Hostname verification is skipped only because the pinned leaf certificate already identifies the peer
 * The usual hostname verifier remains enabled. The receiver certificate includes
 * every advertised IP address in its Subject Alternative Name extension, so an
 * IP-based LAN connection still receives normal TLS hostname validation.
 */
object PinnedClient {
    fun build(certSha256Hex: String, connectSec: Long = 3, readSec: Long = 30, writeSec: Long = 60): OkHttpClient {
        val expected = certSha256Hex.lowercase()
        val trust = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) =
                throw CertificateException("client certificates are not used")

            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                val actual = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded)
                    .joinToString("") { "%02x".format(it) }
                if (!MessageDigest.isEqual(actual.toByteArray(), expected.toByteArray())) {
                    throw CertificateException("Receiver certificate does not match the pinned fingerprint")
                }
            }

            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trust), null) }
        return OkHttpClient.Builder()
            .sslSocketFactory(ssl.socketFactory, trust)
            .protocols(listOf(Protocol.HTTP_1_1))
            .connectTimeout(connectSec, TimeUnit.SECONDS)
            .readTimeout(readSec, TimeUnit.SECONDS)
            .writeTimeout(writeSec, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false)
            .build()
    }
}
