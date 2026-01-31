package com.bitpoliteia.agent

import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.bitpoliteia.data.Message
import com.bitpoliteia.data.MessageDao
import com.bitpoliteia.p2p.P2PNode
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class AgentService : Service() {

    @Inject
    lateinit var p2pNode: P2PNode

    @Inject
    lateinit var messageDao: MessageDao

    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)

    override fun onCreate() {
        super.onCreate()
        startForegroundService()
        p2pNode.start()
        
        // Listen to User instructions or Network events here
        serviceScope.launch {
            // Placeholder: Initial Greeting
            messageDao.insertMessage(
                Message(
                    content = "Agent Service initialized. Waiting for instructions.",
                    senderId = "System",
                    timestamp = System.currentTimeMillis(),
                    isFromUser = false
                )
            )
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Handle commands from UI (e.g., "Analyze this proposal")
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        p2pNode.stop()
        serviceJob.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startForegroundService() {
        val notification = NotificationCompat.Builder(this, "channel_agent")
            .setContentTitle("Bit Politeia Agent")
            .setContentText("Agent is active and listening to the network.")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .build()

        startForeground(1, notification)
    }
}
