export const Store = {
    saveUser: (email, field, apiKey, model = 'gpt-4o', llmBaseUrl = '') => {
        localStorage.setItem('bp_email', email)
        localStorage.setItem('bp_field', field)
        if (apiKey) localStorage.setItem('bp_api_key', apiKey)
        localStorage.setItem('bp_model', model)
        if (llmBaseUrl) localStorage.setItem('bp_llm_base_url', llmBaseUrl)
        localStorage.setItem('bp_onboarded', 'true')
    },

    getUser: () => ({
        email: localStorage.getItem('bp_email'),
        field: localStorage.getItem('bp_field'),
        apiKey: localStorage.getItem('bp_api_key'),
        model: localStorage.getItem('bp_model') || 'gpt-4o',
        apiUrl: localStorage.getItem('bp_api_url') || 'http://localhost:8001',
        llmBaseUrl: localStorage.getItem('bp_llm_base_url') || ''
    }),

    clear: () => {
        localStorage.clear()
        window.location.reload()
    }
}
