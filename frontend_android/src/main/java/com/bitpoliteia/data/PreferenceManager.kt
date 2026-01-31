package com.bitpoliteia.data

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PreferenceManager @Inject constructor(
    @ApplicationContext context: Context
) {
    // In production, use EncryptedSharedPreferences
    private val prefs: SharedPreferences = context.getSharedPreferences("bit_politeia_prefs", Context.MODE_PRIVATE)

    var hasOnboarded: Boolean
        get() = prefs.getBoolean("has_onboarded", false)
        set(value) = prefs.edit { putBoolean("has_onboarded", value) }

    var agentApiUrl: String
        get() = prefs.getString("agent_api_url", "") ?: ""
        set(value) = prefs.edit { putString("agent_api_url", value) }

    var agentApiKey: String
        get() = prefs.getString("agent_api_key", "") ?: ""
        set(value) = prefs.edit { putString("agent_api_key", value) }
        
    var userEmail: String
        get() = prefs.getString("user_email", "") ?: ""
        set(value) = prefs.edit { putString("user_email", value) }
        
    var researchField: String
        get() = prefs.getString("research_field", "") ?: ""
        set(value) = prefs.edit { putString("research_field", value) }
        
    var agentModel: String
        get() = prefs.getString("agent_model", "gpt-4o") ?: "gpt-4o"
        set(value) = prefs.edit { putString("agent_model", value) }
}
