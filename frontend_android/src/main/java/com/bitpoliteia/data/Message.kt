package com.bitpoliteia.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "messages")
data class Message(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val content: String,
    val senderId: String,
    val timestamp: Long,
    val isFromUser: Boolean // true = User->Agent, false = Agent->User/CommonLog
)
