package com.mconn.app.transfer

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import com.mconn.app.MConnApp
import com.mconn.app.queue.TransferEntity
import com.mconn.app.queue.TransferState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicLong

/**
 * Drives ONE transfer through QUEUED -> ... -> DELIVERED (DESIGN.md section 7). All state lives in Room, so a
 * killed process, reboot or app update loses nothing: the worker simply re-reads the row and continues.
 */
class TransferWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    private val dao = (context.applicationContext as MConnApp).db.transfers()
    private val pcDao = (context.applicationContext as MConnApp).db.pairedPc()

    override suspend fun doWork(): Result {
        val id = inputData.getString(KEY_ID) ?: return Result.failure()
        var t = dao.get(id) ?: return Result.failure()
        if (t.state in TransferState.terminal) return Result.success()

        val pc = pcDao.get() ?: return reject(t, "NOT_PAIRED", "Pair this phone with a PC first")
        if (t.sizeBytes > LARGE_FILE_BYTES) setForeground(foregroundInfo(t.displayName))

        t = save(t.copy(state = TransferState.DISCOVERING, attemptCount = t.attemptCount + 1))
        val api = when (val c = ConnectionManager(applicationContext).connect(pc)) {
            is Connection.Connected -> c.api
            is Connection.Rejected -> return reject(t, c.code, c.message)
            Connection.Unreachable -> return retryLater(t, "PC_UNREACHABLE", "PC not reachable; will retry")
        }

        t = save(t.copy(state = TransferState.CONNECTING))
        val created = when (val r = api.createTransfer(t)) {
            is ApiResult.Ok -> r.value
            is ApiResult.Reject -> return reject(t, r.code, r.message)
            is ApiResult.Retry -> return retryLater(t, r.code, r.message)
            is ApiResult.OffsetMismatch -> return retryLater(t, "OFFSET_MISMATCH", "Unexpected offset on create")
        }
        if (created.optString("state") == "COMMITTED") return delivered(t, created.optJSONObject("receipt"))

        t = save(t.copy(state = TransferState.UPLOADING, bytesSent = created.optLong("bytes_received")))
        val lastWrite = AtomicLong(0)
        val onProgress: (Long) -> Unit = { sent ->
            val now = SystemClock.elapsedRealtime()
            if (now - lastWrite.get() > 1000) { // throttle Room writes
                lastWrite.set(now)
                CoroutineScope(Dispatchers.IO).launch { dao.setProgress(t.transferId, sent, System.currentTimeMillis()) }
            }
        }
        var result = api.upload(t, created.optLong("bytes_received"), onProgress)
        if (result is ApiResult.OffsetMismatch) result = api.upload(t, result.serverOffset, onProgress) // re-sync once

        return when (result) {
            is ApiResult.Ok ->
                if (result.value.optString("state") == "COMMITTED") delivered(t, result.value.optJSONObject("receipt"))
                else retryLater(t, "INCOMPLETE", "Receiver has not committed the file yet")
            is ApiResult.Reject -> reject(t, result.code, result.message)
            is ApiResult.Retry -> retryLater(t, result.code, result.message)
            is ApiResult.OffsetMismatch -> retryLater(t, "OFFSET_MISMATCH", "Receiver offset changed again")
        }
    }

    private suspend fun save(t: TransferEntity): TransferEntity =
        t.copy(updatedAt = System.currentTimeMillis()).also { dao.update(it) }

    private suspend fun delivered(t: TransferEntity, receipt: JSONObject?): Result {
        val now = System.currentTimeMillis()
        save(
            t.copy(
                state = TransferState.DELIVERED, bytesSent = t.sizeBytes, receiptJson = receipt?.toString(),
                deliveredAt = now, cleanupAfter = now + CLEANUP_DELAY_MS, lastErrorCode = null, lastErrorMessage = null,
            )
        )
        // TODO(Phase 2): a cleanup worker deletes localPath once cleanupAfter has passed.
        return Result.success()
    }

    private suspend fun retryLater(t: TransferEntity, code: String, message: String): Result {
        save(t.copy(state = TransferState.RETRY_WAIT, lastErrorCode = code, lastErrorMessage = message))
        return Result.retry() // WorkManager applies exponential backoff (see TransferScheduler)
    }

    private suspend fun reject(t: TransferEntity, code: String, message: String): Result {
        save(t.copy(state = TransferState.REJECTED, lastErrorCode = code, lastErrorMessage = message))
        return Result.failure()
    }

    // Required for expedited work on API < 31, and used for large uploads.
    override suspend fun getForegroundInfo(): ForegroundInfo = foregroundInfo("Sending files")

    private fun foregroundInfo(title: String): ForegroundInfo {
        val nm = applicationContext.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Transfers", NotificationManager.IMPORTANCE_LOW))
        }
        val n = NotificationCompat.Builder(applicationContext, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("MConn")
            .setContentText(title)
            .setOngoing(true)
            .build()
        return if (Build.VERSION.SDK_INT >= 29) {
            ForegroundInfo(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(NOTIFICATION_ID, n)
        }
    }

    companion object {
        const val KEY_ID = "transfer_id"
        private const val CHANNEL = "transfers"
        private const val NOTIFICATION_ID = 1001
        private const val LARGE_FILE_BYTES = 25L * 1024 * 1024 // PROPOSED threshold (DESIGN.md 3.3)
        private const val CLEANUP_DELAY_MS = 24L * 3600 * 1000
    }
}
