package com.mconn.app

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import com.mconn.app.queue.AppDatabase
import com.mconn.app.transfer.TransferScheduler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class MConnApp : Application() {
    val db: AppDatabase by lazy { AppDatabase.get(this) }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        TransferScheduler.schedulePeriodicResume(this)
        scope.launch { TransferScheduler.resumePending(this@MConnApp) }

        // Any network coming up (including Wi-Fi with no internet) is a reason to retry waiting transfers.
        getSystemService(ConnectivityManager::class.java).registerDefaultNetworkCallback(
            object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    scope.launch { TransferScheduler.resumePending(this@MConnApp) }
                }
            }
        )
    }
}
