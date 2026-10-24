package com.mconn.app.transfer

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.mconn.app.queue.AppDatabase
import java.io.File
import java.util.concurrent.TimeUnit

object TransferScheduler {
    /**
     * NetworkType.NOT_REQUIRED on purpose: WorkManager's CONNECTED constraint needs a *validated* (internet-capable)
     * network, which would block local-only Wi-Fi transfers. We probe the receiver ourselves instead.
     * UNVERIFIED on device: confirm this behaviour in the Phase 1 exit test (Wi-Fi with no internet).
     * TODO: WorkManager backoff caps at 5h; DESIGN.md wants a 15 min cap, so reschedule manually in Phase 2.
     */
    fun enqueue(context: Context, transferId: String) {
        val request = OneTimeWorkRequestBuilder<TransferWorker>()
            .setInputData(workDataOf(TransferWorker.KEY_ID to transferId))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.NOT_REQUIRED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.SECONDS)
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork("transfer-$transferId", ExistingWorkPolicy.KEEP, request)
    }

    /** Re-enqueue everything not yet terminal: app start, network change, manual retry. KEEP makes this idempotent. */
    suspend fun resumePending(context: Context) {
        AppDatabase.get(context).transfers().pending().forEach { enqueue(context, it.transferId) }
    }

    /** Safety net: wakes the queue every 15 min even if the process was killed. */
    fun schedulePeriodicResume(context: Context) {
        val request = PeriodicWorkRequestBuilder<ResumeWorker>(15, TimeUnit.MINUTES).build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork("mconn-resume", ExistingPeriodicWorkPolicy.KEEP, request)
    }

    /** Removes only MConn's private outgoing copies after a stored receipt's retention period. */
    fun schedulePeriodicCleanup(context: Context) {
        val request = PeriodicWorkRequestBuilder<CleanupWorker>(24, TimeUnit.HOURS).build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork("mconn-cleanup", ExistingPeriodicWorkPolicy.KEEP, request)
    }
}

class ResumeWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        TransferScheduler.resumePending(applicationContext)
        return Result.success()
    }
}

class CleanupWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val dao = AppDatabase.get(applicationContext).transfers()
        val outgoing = File(applicationContext.filesDir, "outgoing").canonicalFile
        for (transfer in dao.cleanupDue(System.currentTimeMillis())) {
            val local = File(transfer.localPath).canonicalFile
            if (!local.path.startsWith(outgoing.path + File.separator)) return Result.failure()
            if (local.exists() && !local.delete()) return Result.retry()
            dao.markLocalCopyDeleted(transfer.transferId, System.currentTimeMillis())
        }
        return Result.success()
    }
}
