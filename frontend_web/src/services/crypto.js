export const CryptoService = {
    async generateKeyPair() {
        if (localStorage.getItem('bp_public_key')) return localStorage.getItem('bp_public_key')

        const keyPair = await window.crypto.subtle.generateKey(
            {
                name: "ECDSA",
                namedCurve: "P-256",
            },
            true,
            ["sign", "verify"]
        )

        const exportedPub = await window.crypto.subtle.exportKey("spki", keyPair.publicKey)
        const exportedPriv = await window.crypto.subtle.exportKey("pkcs8", keyPair.privateKey)

        const pubBase64 = btoa(String.fromCharCode(...new Uint8Array(exportedPub)))
        const privBase64 = btoa(String.fromCharCode(...new Uint8Array(exportedPriv)))

        localStorage.setItem('bp_public_key', pubBase64)
        localStorage.setItem('bp_private_key', privBase64)

        return pubBase64
    },

    getPublicKey: () => localStorage.getItem('bp_public_key')
}
