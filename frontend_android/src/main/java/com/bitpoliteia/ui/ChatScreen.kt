package com.bitpoliteia.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bitpoliteia.data.Message
import com.bitpoliteia.data.MessageDao
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val agentApi: com.bitpoliteia.network.AgentApi
) : ViewModel() {

    private val _messages = kotlinx.coroutines.flow.MutableStateFlow<List<Message>>(emptyList())
    val messages: kotlinx.coroutines.flow.StateFlow<List<Message>> = _messages

    init {
        fetchMessages()
    }

    private fun fetchMessages() {
        viewModelScope.launch {
            try {
                // Polling simulation (in real app use WebSocket or PeriodicWork)
                while(true) {
                    val history = agentApi.getHistory()
                    _messages.value = history.map { dto ->
                        Message(
                            id = dto.id.hashCode().toLong(), // Simple hash for ID
                            content = dto.content,
                            senderId = dto.sender, // Map dto.sender to senderId
                            timestamp = System.currentTimeMillis(), // Simplified timestamp
                            isFromUser = dto.sender == "user" // Infer isFromUser from sender
                        )
                    }
                    kotlinx.coroutines.delay(2000)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    fun sendMessage(text: String) {
        viewModelScope.launch {
            try {
                agentApi.sendInstruction(com.bitpoliteia.network.ChatRequest(text))
                fetchMessages() // Refresh immediately
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}

@Composable
fun ChatScreen(
    viewModel: ChatViewModel = hiltViewModel()
) {
    val messages by viewModel.messages.collectAsState(initial = emptyList())
    var inputText by remember { mutableStateOf("") }
    
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        LazyColumn(modifier = Modifier.weight(1f)) {
            items(messages) { msg ->
                MessageItem(msg)
            }
        }
        
        Row(modifier = Modifier.fillMaxWidth()) {
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                modifier = Modifier.weight(1f),
                label = { Text("Instruction for Agent") }
            )
            Button(
                onClick = { 
                    if (inputText.isNotBlank()) {
                        viewModel.sendMessage(inputText)
                        inputText = ""
                    }
                },
                modifier = Modifier.padding(start = 8.dp)
            ) {
                Text("Send")
            }
        }
    }
}

@Composable
fun MessageItem(message: Message) {
    Card(modifier = Modifier.fillMaxWidth().padding(4.dp)) {
        Column(modifier = Modifier.padding(8.dp)) {
            Text(text = if (message.isFromUser) "You" else "Agent", style = androidx.compose.material3.MaterialTheme.typography.labelSmall)
            Text(text = message.content)
        }
    }
}
