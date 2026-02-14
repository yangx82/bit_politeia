import React, { useState } from 'react'
import { Store } from '../services/store'
import { CryptoService } from '../services/crypto'
import { setApiUrl } from '../services/api'

const Input = ({ label, ...props }) => (
    <div className="flex flex-col gap-1 mb-4">
        <label className="text-sm font-medium text-secondary">{label}</label>
        <input
            className="p-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary/50"
            {...props}
        />
    </div>
)

const Onboarding = ({ onComplete }) => {
    const [formData, setFormData] = useState({
        email: '',
        field: '',
        agentUrl: 'http://localhost:8001',
        bootstrapUrl: 'http://localhost:8000',
        llmBaseUrl: 'https://api.openai.com/v1',
        apiKey: '',
        model: 'gpt-4o',
        verboseLlm: false,
        bootstrapVerify: true
    })
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault()
        setLoading(true)

        try {
            // 1. Generate Identity
            const pubKey = await CryptoService.generateKeyPair()
            console.log("Generated Identity:", pubKey)

            // 2. Configure API with Agent Node URL
            setApiUrl(formData.agentUrl)

            // 3. Push Config to Backend Agent Node
            const { default: api } = await import('../services/api')
            await api.post('/api/v1/config', {
                base_url: formData.llmBaseUrl,
                api_key: formData.apiKey,
                model: formData.model,
                research_field: formData.field,
                bootstrap_url: formData.bootstrapUrl,
                verbose_llm: formData.verboseLlm,
                bootstrap_verify: formData.bootstrapVerify
            })

            // 4. Save Preference Locally
            localStorage.setItem('bp_api_url', formData.agentUrl)
            Store.saveUser(formData.email, formData.field, formData.apiKey, formData.model, formData.llmBaseUrl, formData.bootstrapUrl, formData.verboseLlm, formData.bootstrapVerify)

            onComplete()
        } catch (err) {
            console.error(err)
            alert("Failed to Initialize Identity")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50">
            <div className="bg-white p-8 rounded-xl shadow-lg w-full max-w-md">
                <h1 className="text-2xl font-bold text-center mb-2 text-slate-800">Welcome to Bit Politeia</h1>
                <p className="text-center text-slate-500 mb-8 text-sm">Initialize your Agent Node Identity</p>

                <form onSubmit={handleSubmit}>
                    <Input
                        label="Email (Verifiable)"
                        type="email" required
                        value={formData.email}
                        onChange={e => setFormData({ ...formData, email: e.target.value })}
                    />

                    <Input
                        label="Research Field"
                        placeholder="e.g. AI Governance" required
                        value={formData.field}
                        onChange={e => setFormData({ ...formData, field: e.target.value })}
                    />

                    <div className="h-px bg-slate-100 my-6" />

                    <h3 className="font-medium mb-4 text-slate-700">Agent Configuration</h3>

                    <Input
                        label="Agent Node URL (Backend address)"
                        value={formData.agentUrl}
                        onChange={e => setFormData({ ...formData, agentUrl: e.target.value })}
                    />

                    <Input
                        label="Bootstrap Server URL"
                        value={formData.bootstrapUrl}
                        onChange={e => setFormData({ ...formData, bootstrapUrl: e.target.value })}
                    />

                    <Input
                        label="LLM Provider Base URL (OpenAI compatible)"
                        placeholder="e.g. https://api.openai.com/v1"
                        value={formData.llmBaseUrl}
                        onChange={e => setFormData({ ...formData, llmBaseUrl: e.target.value })}
                    />

                    <Input
                        label="API Key (Optional)"
                        type="password"
                        value={formData.apiKey}
                        onChange={e => setFormData({ ...formData, apiKey: e.target.value })}
                    />

                    <Input
                        label="Model Name"
                        placeholder="e.g. gpt-4o, claude-3-5-sonnet"
                        value={formData.model}
                        onChange={e => setFormData({ ...formData, model: e.target.value })}
                    />

                    <div className="flex items-center mb-4">
                        <input
                            type="checkbox"
                            id="verboseLlm"
                            checked={formData.verboseLlm}
                            onChange={e => setFormData({ ...formData, verboseLlm: e.target.checked })}
                            className="w-4 h-4 text-primary focus:ring-primary border-slate-300 rounded"
                        />
                        <label htmlFor="verboseLlm" className="ml-2 text-sm text-slate-600">Enable Verbose LLM Output</label>
                    </div>

                    <div className="flex items-center mb-6">
                        <input
                            type="checkbox"
                            id="bootstrapVerify"
                            checked={formData.bootstrapVerify}
                            onChange={e => setFormData({ ...formData, bootstrapVerify: e.target.checked })}
                            className="w-4 h-4 text-primary focus:ring-primary border-slate-300 rounded"
                        />
                        <label htmlFor="bootstrapVerify" className="ml-2 text-sm text-slate-600">Verify Bootstrap SSL Certificate</label>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-primary text-white py-2.5 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-70 mt-4"
                    >
                        {loading ? 'Initializing...' : 'Create Identity & Connect'}
                    </button>
                </form>
            </div>
        </div>
    )
}

export default Onboarding
