package com.mconn.app.share

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.mconn.app.queue.PairedPcEntity
import com.mconn.app.queue.TransferEntity
import com.mconn.app.transfer.TransferScheduler
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.security.MessageDigest
import java.util.UUID
import com.mconn.app.queue.AppDatabase

/**
 * Share Target back end: copy the shared content into app-private storage FIRST (the source app may revoke
 * its URI permission at any moment), hashing in the same pass, then enqueue.
 */
object FileStager {
    suspend fun stageAndEnqueue(context: Context, uri: Uri, pc: PairedPcEntity): TransferEntity = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver
        val id = UUID.randomUUID().toString()
        val dir = File(context.filesDir, "outgoing").apply { mkdirs() }
        val dest = File(dir, "$id.bin")

        val digest = MessageDigest.getInstance("SHA-256")
        var size = 0L
        resolver.openInputStream(uri)?.use { input ->
            dest.outputStream().use { out ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    digest.update(buf, 0, n)
                    size += n
                }
            }
        } ?: throw IllegalStateException("Cannot open shared content")

        val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: uri.lastPathSegment ?: "file"

        val now = System.currentTimeMillis()
        val entity = TransferEntity(
            transferId = id,
            pcId = pc.pcId,
            displayName = name,
            mime = resolver.getType(uri),
            sizeBytes = size,
            sha256 = digest.digest().joinToString("") { "%02x".format(it) },
            localPath = dest.absolutePath,
            createdAt = now,
            updatedAt = now,
        )
        AppDatabase.get(context).transfers().insert(entity)
        TransferScheduler.enqueue(context, id)
        entity
    }
}
