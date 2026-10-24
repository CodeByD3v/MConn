package com.mconn.app.queue

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface TransferDao {
    @Query("SELECT * FROM transfers ORDER BY createdAt DESC")
    fun observeAll(): Flow<List<TransferEntity>>

    @Query("SELECT * FROM transfers WHERE transferId = :id")
    suspend fun get(id: String): TransferEntity?

    @Query("SELECT * FROM transfers WHERE state NOT IN ('DELIVERED','REJECTED','CANCELLED')")
    suspend fun pending(): List<TransferEntity>

    @Insert suspend fun insert(t: TransferEntity)

    @Update suspend fun update(t: TransferEntity)

    @Query("UPDATE transfers SET bytesSent = :sent, updatedAt = :now WHERE transferId = :id")
    suspend fun setProgress(id: String, sent: Long, now: Long)
}

@Dao
interface PairedPcDao {
    @Query("SELECT * FROM paired_pc LIMIT 1")
    suspend fun get(): PairedPcEntity?

    @Query("SELECT * FROM paired_pc LIMIT 1")
    fun observe(): Flow<PairedPcEntity?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(pc: PairedPcEntity)

    @Query("UPDATE paired_pc SET lastGoodHost = :host WHERE pcId = :pcId")
    suspend fun setLastGoodHost(pcId: String, host: String)
}
