package com.bitpoliteia.p2p

import kotlinx.coroutines.flow.Flow

interface P2PNode {
    fun start()
    fun stop()
    fun broadcast(topic: String, message: String)
    fun subscribe(topic: String): Flow<String>
    fun getPeerId(): String
}
