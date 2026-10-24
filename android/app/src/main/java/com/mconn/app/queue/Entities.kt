package com.mconn.app.queue

import androidx.room.Entity
import androidx.room.PrimaryKey

/** State names match DESIGN.md section 7. Stored as plain strings (no type converters needed). */
object TransferState {
    const val QUEUED = "QUEUED"
    const val DISCOVERING = "DISCOVERING"
    const val CONNECTING = "CONNECTING"
    const val UPLOADING = "UPLOADING"
    const val VERIFYING = "VERIFYING"
    const val DELIVERED = "DELIVERED"
    const val RETRY_WAIT = "RETRY_WAIT"
    const val REJECTED = "REJECTED"
    const val CANCELLED = "CANCELLED"

    val terminal = setOf(DELIVERED, REJECTED, CANCELLED)
}

/** PHONE_TRANSFER in DATABASE.mmd. Room is the single source of truth for the queue. */
@Entity(tableName = "transfers")
data class TransferEntity(
    @PrimaryKey val transferId: String,
    val pcId: String,
    val displayName: String,
    val mime: String?,
    val sizeBytes: Long,
    val sha256: String,
    val localPath: String,
    val state: String = TransferState.QUEUED,
    val bytesSent: Long = 0,
    val attemptCount: Int = 0,
    val nextRetryAt: Long? = null,
    val lastErrorCode: String? = null,
    val lastErrorMessage: String? = null,
    val receiptJson: String? = null,
    val createdAt: Long,
    val updatedAt: Long,
    val deliveredAt: Long? = null,
    val cleanupAfter: Long? = null,
    val localCopyDeleted: Boolean = false,
)

/** PHONE_PAIRED_PC in DATABASE.mmd. One PC per phone in v1. */
@Entity(tableName = "paired_pc")
data class PairedPcEntity(
    @PrimaryKey val pcId: String,
    val pcName: String,
    val deviceId: String,
    val certSha256: String,
    val lastGoodHost: String?,
    val hostsJson: String,
    val port: Int,
    val pairedAt: Long,
)
