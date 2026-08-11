package com.bitpoliteia.ui.profile

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bitpoliteia.data.PreferenceManager
import com.bitpoliteia.network.AgentApi
import com.bitpoliteia.network.ConfigRequest
import com.bitpoliteia.security.KeyManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val preferenceManager: PreferenceManager,
    private val keyManager: KeyManager,
    private val agentApi: AgentApi
) : ViewModel() {
    val email = preferenceManager.userEmail
    val publicKey = keyManager.getPublicKey()
    
    // Agent Config State
    val apiUrl = mutableStateOf(preferenceManager.agentApiUrl)
    val apiKey = mutableStateOf(preferenceManager.agentApiKey)
    val model = mutableStateOf(preferenceManager.agentModel)
    val isUpdating = mutableStateOf(false)
    
    fun updateConfig(onSuccess: () -> Unit, onError: (String) -> Unit) {
        viewModelScope.launch {
            isUpdating.value = true
            try {
                agentApi.configureAgent(
                    ConfigRequest(apiUrl.value, apiKey.value, model.value)
                )
                preferenceManager.agentApiUrl = apiUrl.value
                preferenceManager.agentApiKey = apiKey.value
                preferenceManager.agentModel = model.value
                onSuccess()
            } catch (e: Exception) {
                onError(e.message ?: "Update failed")
            } finally {
                isUpdating.value = false
            }
        }
    }
    
    fun reset() {
        preferenceManager.hasOnboarded = false
    }
}

@Composable
fun ProfileScreen(
    viewModel: ProfileViewModel = hiltViewModel()
) {
    var showSuccess by remember { mutableStateOf(false) }
    
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Profile & Wallet", style = MaterialTheme.typography.headlineMedium)
        
        // Identity Section
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Identity", style = MaterialTheme.typography.titleMedium)
                Text("Email: ${viewModel.email}")
                Text("Wallet Address (Public Key):")
                Text(viewModel.publicKey.take(20) + "...", style = MaterialTheme.typography.bodySmall)
            }
        }

        // Wallet Section
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
           Column(modifier = Modifier.padding(16.dp)) {
               Text("Wallet Balance", style = MaterialTheme.typography.titleMedium)
               Text("1250 Stater", style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.primary)
           }
        }
        
        // Agent Settings Section
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Agent Settings", style = MaterialTheme.typography.titleMedium)
                Spacer(modifier = Modifier.height(8.dp))
                
                OutlinedTextField(
                    value = viewModel.apiUrl.value,
                    onValueChange = { viewModel.apiUrl.value = it },
                    label = { Text("Agent Node URL") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(8.dp))
                
                OutlinedTextField(
                    value = viewModel.apiKey.value,
                    onValueChange = { viewModel.apiKey.value = it },
                    label = { Text("API Key") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(8.dp))
                
                OutlinedTextField(
                    value = viewModel.model.value,
                    onValueChange = { viewModel.model.value = it },
                    label = { Text("Model Name") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(12.dp))
                
                Button(
                    onClick = {
                        viewModel.updateConfig(
                            onSuccess = { showSuccess = true },
                            onError = { /* Show error */ }
                        )
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !viewModel.isUpdating.value
                ) {
                    Text(if (viewModel.isUpdating.value) "Updating..." else "Update Configuration")
                }
                
                if (showSuccess) {
                    Text("Configuration Updated!", color = Color.Green, modifier = Modifier.padding(top = 8.dp))
                }
            }
        }

        // Transactions Section
        Text("Recent Transactions", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp))
        LazyColumn(modifier = Modifier.weight(1f)) {
            items(5) { index ->
                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Reward from Community")
                    Text("+50 Stater", color = Color.Green)
                }
            }
        }

        Button(
            onClick = { viewModel.reset() },
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
        ) {
            Text("Reset Onboarding (Debug)")
        }
    }
}
