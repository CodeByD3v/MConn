package com.mconn.app.pairing

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/** ECDSA P-256 key in the Android Keystore. The private key is non-exportable (ARCHITECTURE.md section 6). */
object DeviceKeys {
    private const val ALIAS = "mconn_device_key"
    private const val PROVIDER = "AndroidKeyStore"

    private val keyStore: KeyStore get() = KeyStore.getInstance(PROVIDER).apply { load(null) }

    private fun ensureKey() {
        if (keyStore.containsAlias(ALIAS)) return
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, PROVIDER).apply { initialize(spec) }.generateKeyPair()
    }

    /** base64 (standard alphabet, padded) of the X.509 SubjectPublicKeyInfo DER, as the receiver expects. */
    fun publicKeyBase64(): String {
        ensureKey()
        val pub = keyStore.getCertificate(ALIAS).publicKey
        return Base64.encodeToString(pub.encoded, Base64.NO_WRAP)
    }

    /** SHA256withECDSA, DER-encoded signature. */
    fun sign(message: ByteArray): ByteArray {
        ensureKey()
        val key = keyStore.getKey(ALIAS, null) as PrivateKey
        return Signature.getInstance("SHA256withECDSA").run {
            initSign(key)
            update(message)
            sign()
        }
    }
}
