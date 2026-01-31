package com.bitpoliteia.core

import android.content.Context
import androidx.room.Room
import com.bitpoliteia.data.AppDatabase
import com.bitpoliteia.data.MessageDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DataModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase {
        return Room.databaseBuilder(
            context,
            AppDatabase::class.java,
            "bit_politeia_db"
        ).build()
    }

    @Provides
    fun provideMessageDao(database: AppDatabase): MessageDao {
        return database.messageDao()
    }
}
