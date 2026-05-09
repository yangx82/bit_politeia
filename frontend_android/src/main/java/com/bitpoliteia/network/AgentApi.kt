package com.bitpoliteia.network

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

data class ChatRequest(val content: String)

data class MessageDto(
    val id: String,
    val content: String,
    val sender: String,
    val timestamp: String
)

data class ConfigRequest(
    val base_url: String,
    val api_key: String,
    val model: String = "gpt-4o"
)

interface AgentApi {
    @POST("/api/v1/config")
    suspend fun configureAgent(@Body request: ConfigRequest)

    @GET("/api/v1/history")
    suspend fun getHistory(): List<MessageDto>

    @POST("/api/v1/chat/instruction")
    suspend fun sendInstruction(@Body request: ChatRequest): MessageDto
}
