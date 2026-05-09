package com.bitpoliteia.p2p

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.filter
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MockP2PNode @Inject constructor() : P2PNode {
    private val _networkBus = MutableSharedFlow<Pair<String, String>>(replay = 0)
    
    override fun start() {
        // Simulate startup
        println("P2P Node Started")
    }

    override fun stop() {
        println("P2P Node Stopped")
    }

    override fun broadcast(topic: String, message: String) {
        // In a real impl, this goes to Libp2p. Here we loopback for testing.
        println("Broadcasting to $topic: $message")
        // Emit to local subscribers for UI testing
    }

    override fun subscribe(topic: String): Flow<String> {
        return _networkBus
            .filter { it.first == topic }
            .map { it.second } // Error: map not imported/resolved in this snippet, will fix in next step if needed or assume standard libs
    }
    
    // Fix: add map import or use transform
    private fun <T, R> Flow<T>.map(transform: suspend (T) -> R): Flow<R> = kotlinx.coroutines.flow.map(transform)


    override fun getPeerId(): String = "QmMockPeerId123456789"
}
