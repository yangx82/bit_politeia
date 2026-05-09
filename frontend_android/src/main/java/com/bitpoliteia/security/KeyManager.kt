package com.bitpoliteia.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class KeyManager @Inject constructor() {

    private val keyStore = KeyStore.getInstance("AndroidKeyStore").apply {
        load(null)
    }

    private val KEY_ALIAS = "BitPoliteiaIdentity"

    fun generateIdentityIfNotExists(): String {
        if (!keyStore.containsAlias(KEY_ALIAS)) {
            val kpg: KeyPairGenerator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC,
                "AndroidKeyStore"
            )
            val parameterSpec: KeyGenParameterSpec = KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
            ).run {
                setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA512)
                build()
            }

            kpg.initialize(parameterSpec)
            kpg.generateKeyPair()
        }
        
        return getPublicKey()
    }

    fun getPublicKey(): String {
        val entry = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.PrivateKeyEntry
        return entry?.certificate?.publicKey?.encoded?.let {
            Base64.encodeToString(it, Base64.NO_WRAP)
        } ?: ""
    }
    
    // In a real app, integrate signing here using the private key
}
