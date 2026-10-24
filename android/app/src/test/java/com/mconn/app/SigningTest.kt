package com.mconn.app

import com.mconn.app.transfer.Signing
import org.junit.Assert.assertEquals
import org.junit.Test

/** Vectors are asserted identically on the Python side (windows-receiver/tests/test_contract_vectors.py). */
class SigningTest {
    @Test fun sha256OfEmptyBody() {
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", Signing.sha256Hex(ByteArray(0)))
    }

    @Test fun canonicalStringMatchesContract() {
        val bytes = Signing.canonical("get", "/v1/inbox?limit=5", "1700000000", "abc_DEF-123", Signing.sha256Hex(ByteArray(0)))
        assertEquals(
            "GET\n/v1/inbox?limit=5\n1700000000\nabc_DEF-123\ne3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            String(bytes, Charsets.UTF_8),
        )
    }

    @Test fun streamedUploadUsesLiteralMarker() {
        val s = String(Signing.canonical("PUT", "/v1/transfers/x/content", "1", "n", Signing.UNSIGNED_PAYLOAD), Charsets.UTF_8)
        assertEquals("PUT\n/v1/transfers/x/content\n1\nn\nUNSIGNED-PAYLOAD", s)
    }
}
