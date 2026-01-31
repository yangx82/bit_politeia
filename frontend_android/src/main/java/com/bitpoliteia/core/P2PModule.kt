package com.bitpoliteia.core

import com.bitpoliteia.p2p.MockP2PNode
import com.bitpoliteia.p2p.P2PNode
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class P2PModule {

    @Binds
    @Singleton
    abstract fun bindP2PNode(impl: MockP2PNode): P2PNode
}
