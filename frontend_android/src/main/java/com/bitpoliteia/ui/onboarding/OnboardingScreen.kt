package com.bitpoliteia.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import com.bitpoliteia.data.PreferenceManager
import com.bitpoliteia.security.KeyManager
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class OnboardingViewModel @Inject constructor(
    private val preferenceManager: PreferenceManager,
    private val keyManager: KeyManager,
    private val agentApi: com.bitpoliteia.network.AgentApi
) : ViewModel() {

    fun completeOnboarding(
        email: String,
        field: String,
        baseUrl: String,
        apiKey: String,
        model: String,
        onComplete: () -> Unit
    ) {
        androidx.lifecycle.viewModelScope.launch {
            try {
                // 1. Save Preferences (Set URL for Retrofit)
                preferenceManager.agentApiUrl = baseUrl
                preferenceManager.agentApiKey = apiKey
                preferenceManager.agentModel = model

                // 2. Generate Identity
                keyManager.generateIdentityIfNotExists()

                // 3. Push Config to Backend
                agentApi.configureAgent(
                    com.bitpoliteia.network.ConfigRequest(baseUrl, apiKey, model)
                )

                // 4. Finalize
                preferenceManager.userEmail = email
                preferenceManager.researchField = field
                preferenceManager.hasOnboarded = true

                onComplete()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}

@Composable
fun OnboardingScreen(
    onOnboardingComplete: () -> Unit,
    viewModel: OnboardingViewModel = hiltViewModel()
) {
    var email by remember { mutableStateOf("") }
    var field by remember { mutableStateOf("") }
    var baseUrl by remember { mutableStateOf("") }
    var apiKey by remember { mutableStateOf("") }
    var model by remember { mutableStateOf("gpt-4o") }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Welcome to Bit Politeia", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(24.dp))

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email (Verifiable)") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(8.dp))
        
        OutlinedTextField(
            value = field,
            onValueChange = { field = it },
            label = { Text("Research Field") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(16.dp))

        Text("Agent Configuration", style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = baseUrl,
            onValueChange = { baseUrl = it },
            label = { Text("Agent Node URL (e.g. http://192.168.1.5:8000)") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = apiKey,
            onValueChange = { apiKey = it },
            label = { Text("Agent API Key (Optional)") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(8.dp))
        
        OutlinedTextField(
            value = model,
            onValueChange = { model = it },
            label = { Text("Model Name (e.g. gpt-4o, claude-3-5-sonnet)") },
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(24.dp))

        if (errorMessage != null) {
            Text(errorMessage!!, color = MaterialTheme.colorScheme.error)
            Spacer(modifier = Modifier.height(8.dp))
        }

        Button(
            onClick = {
                if (email.isBlank() || field.isBlank() || baseUrl.isBlank()) {
                    errorMessage = "Please fill all required fields"
                } else {
                    viewModel.completeOnboarding(email, field, baseUrl, apiKey, model, onOnboardingComplete)
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Register & Initialize Identity")
        }
    }
}
