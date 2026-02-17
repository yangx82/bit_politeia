export const Store = {
    saveUser: (email, field, apiKey, model = 'gpt-4o', llmBaseUrl = '', bootstrapUrl = 'http://localhost:8000', verboseLlm = false, bootstrapVerify = true, name = 'Agent', personality = 'Professional') => {
        localStorage.setItem('bp_email', email)
        localStorage.setItem('bp_field', field)
        if (apiKey) localStorage.setItem('bp_api_key', apiKey)
        localStorage.setItem('bp_model', model)
        if (llmBaseUrl) localStorage.setItem('bp_llm_base_url', llmBaseUrl)
        localStorage.setItem('bp_bootstrap_url', bootstrapUrl)
        localStorage.setItem('bp_verbose_llm', verboseLlm)
        localStorage.setItem('bp_bootstrap_verify', bootstrapVerify)
        localStorage.setItem('bp_name', name)
        localStorage.setItem('bp_personality', personality)
        localStorage.setItem('bp_onboarded', 'true')
    },

    getUser: () => ({
        email: localStorage.getItem('bp_email'),
        field: localStorage.getItem('bp_field'),
        apiKey: localStorage.getItem('bp_api_key'),
        model: localStorage.getItem('bp_model') || 'gpt-4o',
        apiUrl: localStorage.getItem('bp_api_url') || 'http://localhost:8001',
        llmBaseUrl: localStorage.getItem('bp_llm_base_url') || '',
        bootstrapUrl: localStorage.getItem('bp_bootstrap_url') || 'http://localhost:8000',
        verboseLlm: localStorage.getItem('bp_verbose_llm') === 'true',
        bootstrapVerify: localStorage.getItem('bp_bootstrap_verify') !== 'false',
        name: localStorage.getItem('bp_name') || 'Agent',
        personality: localStorage.getItem('bp_personality') || 'Professional'
    }),

    clear: () => {
        localStorage.clear()
        window.location.reload()
    }
}
