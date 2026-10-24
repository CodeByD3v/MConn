package com.mconn.app.transfer

import com.mconn.app.queue.TransferEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile

sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>
    /** Transient: keep the transfer queued and try again later. */
    data class Retry(val code: String, val message: String) : ApiResult<Nothing>
    /** Permanent: show to the user, stop retrying. */
    data class Reject(val code: String, val message: String) : ApiResult<Nothing>
    /** Receiver and phone disagree about progress: continue from [serverOffset]. */
    data class OffsetMismatch(val serverOffset: Long) : ApiResult<Nothing>
}

/** Client for the protocol in protocol/transfer-contracts.md. Blocking OkHttp calls run on Dispatchers.IO. */
class MConnApi(
    private val baseUrl: String,
    private val client: OkHttpClient,
    private val signer: RequestSigner,
) {
    suspend fun status(): ApiResult<JSONObject> = callJson("GET", "/v1/device/status", null)

    suspend fun createTransfer(t: TransferEntity): ApiResult<JSONObject> {
        val body = JSONObject()
            .put("transfer_id", t.transferId)
            .put("name", t.displayName)
            .put("size", t.sizeBytes)
            .put("sha256", t.sha256)
            .apply { t.mime?.let { put("mime", it) } }
            .toString()
        return callJson("POST", "/v1/transfers", body)
    }

    /** Uploads bytes [offset, size) in a single streamed PUT. Chunking (Phase 4) reuses this endpoint. */
    suspend fun upload(t: TransferEntity, offset: Long, onProgress: (Long) -> Unit): ApiResult<JSONObject> =
        withContext(Dispatchers.IO) {
            val path = "/v1/transfers/${t.transferId}/content"
            val request = Request.Builder()
                .url(baseUrl + path)
                .put(FileSliceBody(File(t.localPath), offset, t.sizeBytes, onProgress))
                .header("Upload-Offset", offset.toString())
                .apply { signer.headers("PUT", path, null).forEach { (k, v) -> header(k, v) } }
                .build()
            execute(request)
        }

    private suspend fun callJson(method: String, path: String, json: String?): ApiResult<JSONObject> =
        withContext(Dispatchers.IO) {
            val bytes = json?.toByteArray(Charsets.UTF_8) ?: ByteArray(0)
            val headers = signer.headers(method, path, Signing.sha256Hex(bytes))
            val builder = Request.Builder().url(baseUrl + path)
            headers.forEach { (k, v) -> builder.header(k, v) }
            if (method == "POST") builder.post(bytes.toRequestBody(JSON)) else builder.get()
            execute(builder.build())
        }

    private fun execute(request: Request): ApiResult<JSONObject> = try {
        client.newCall(request).execute().use { resp -> parse(resp.code, resp.body?.string().orEmpty()) }
    } catch (e: IOException) {
        ApiResult.Retry("NETWORK", e.message ?: "Network error")
    }

    private fun parse(http: Int, text: String): ApiResult<JSONObject> {
        val json = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
        if (http in 200..299) return ApiResult.Ok(json)
        val code = json.optString("error", "HTTP_$http")
        val message = json.optString("message", "HTTP $http")
        return when {
            http == 409 && code == "OFFSET_MISMATCH" -> ApiResult.OffsetMismatch(json.optLong("bytes_received"))
            code == "STALE_REQUEST" -> ApiResult.Retry(code, message)
            json.optBoolean("retryable", false) -> ApiResult.Retry(code, message)
            http >= 500 || http == 408 -> ApiResult.Retry(code, message)
            else -> ApiResult.Reject(code, message)
        }
    }

    private companion object {
        val JSON = "application/json".toMediaType()
    }
}

/** Streams [offset, length) of a file. Reports bytes sent, counted from the start of the file. */
private class FileSliceBody(
    private val file: File,
    private val offset: Long,
    private val length: Long,
    private val onProgress: (Long) -> Unit,
) : RequestBody() {
    override fun contentType() = "application/octet-stream".toMediaType()
    override fun contentLength(): Long = length - offset

    override fun writeTo(sink: BufferedSink) {
        RandomAccessFile(file, "r").use { raf ->
            raf.seek(offset)
            val buf = ByteArray(64 * 1024)
            var sent = offset
            while (sent < length) {
                val n = raf.read(buf, 0, minOf(buf.size.toLong(), length - sent).toInt())
                if (n < 0) throw IOException("Local file is shorter than recorded")
                sink.write(buf, 0, n)
                sent += n
                onProgress(sent)
            }
        }
    }
}
