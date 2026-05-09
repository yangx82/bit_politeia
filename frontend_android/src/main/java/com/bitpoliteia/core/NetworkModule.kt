package com.bitpoliteia.core

import com.bitpoliteia.data.PreferenceManager
import com.bitpoliteia.network.AgentApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import javax.inject.Singleton
import java.util.concurrent.TimeUnit

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideRetrofit(preferenceManager: PreferenceManager): Retrofit {
        val baseUrl = preferenceManager.agentApiUrl.ifEmpty { "http://10.0.2.2:8000" } // Default to Emulator Localhost
        
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .addConverterFactory(GsonConverterFactory.create())
            .client(OkHttpClient.Builder().callTimeout(10, TimeUnit.SECONDS).build())
            .build()
    }

    @Provides
    @Singleton
    fun provideAgentApi(retrofit: Retrofit): AgentApi {
        return retrofit.create(AgentApi::class.java)
    }
}
