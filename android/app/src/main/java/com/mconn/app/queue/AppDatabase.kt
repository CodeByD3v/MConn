package com.mconn.app.queue

import android.content.Context
import androidx.room.Database
import androidx.room.migration.Migration
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(entities = [TransferEntity::class, PairedPcEntity::class], version = 2, exportSchema = true)
abstract class AppDatabase : RoomDatabase() {
    abstract fun transfers(): TransferDao
    abstract fun pairedPc(): PairedPcDao

    companion object {
        @Volatile private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "mconn.db")
                    .addMigrations(MIGRATION_1_2)
                    .build().also { instance = it }
            }
    }

    private object MIGRATION_1_2 : Migration(1, 2) {
        override fun migrate(database: SupportSQLiteDatabase) {
            database.execSQL("ALTER TABLE transfers ADD COLUMN localCopyDeleted INTEGER NOT NULL DEFAULT 0")
        }
    }
}
