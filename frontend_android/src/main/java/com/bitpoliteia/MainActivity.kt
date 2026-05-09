package com.bitpoliteia

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.bitpoliteia.agent.AgentService
import com.bitpoliteia.ui.ChatScreen
import com.bitpoliteia.ui.theme.BitPoliteiaTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var preferenceManager: com.bitpoliteia.data.PreferenceManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Start the Agent Service (keep it running)
        startForegroundService(Intent(this, AgentService::class.java))

        setContent {
            BitPoliteiaTheme {
                val navController = androidx.navigation.compose.rememberNavController()
                val startDestination = if (preferenceManager.hasOnboarded) {
                    com.bitpoliteia.ui.Screen.Main.route
                } else {
                    com.bitpoliteia.ui.Screen.Onboarding.route
                }

                androidx.navigation.compose.NavHost(navController = navController, startDestination = startDestination) {
                    androidx.navigation.compose.composable(com.bitpoliteia.ui.Screen.Onboarding.route) {
                        com.bitpoliteia.ui.onboarding.OnboardingScreen(
                            onOnboardingComplete = {
                                navController.navigate(com.bitpoliteia.ui.Screen.Main.route) {
                                    popUpTo(com.bitpoliteia.ui.Screen.Onboarding.route) { inclusive = true }
                                }
                            }
                        )
                    }
                    androidx.navigation.compose.composable(com.bitpoliteia.ui.Screen.Main.route) {
                         com.bitpoliteia.ui.main.MainScreen()
                    }
                }
            }
        }
    }
}
