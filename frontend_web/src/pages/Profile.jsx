import React, { useEffect, useState } from 'react'
import { Store } from '../services/store'
import { CryptoService } from '../services/crypto'
import { setApiUrl } from '../services/api'
import { User, Shield, CreditCard, LogOut, Settings } from 'lucide-react'

const Card = ({ title, icon: Icon, children }) => (
    <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm mb-6">
        <div className="flex items-center gap-2 mb-4 text-slate-800">
            <div className="p-2 bg-slate-50 rounded-lg">
                <Icon size={18} className="text-primary" />
            </div>
            <h3 className="font-semibold">{title}</h3>
        </div>
        {children}
    </div>
)

const Input = ({ label, ...props }) => (
    <div className="flex flex-col gap-1 mb-3">
        <label className="text-xs text-slate-500 uppercase font-bold">{label}</label>
        <input
            className="p-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
            {...props}
        />
    </div>
)

const Profile = () => {
    const [user, setUser] = useState(null)
    const [pubKey, setPubKey] = useState('')
    const [agentConfig, setAgentConfig] = useState({
        apiUrl: '',
        llmBaseUrl: '',
        apiKey: '',
        model: '',
        field: ''
    })
    const [updating, setUpdating] = useState(false)

    useEffect(() => {
        const userData = Store.getUser()
        setUser(userData)
        setPubKey(CryptoService.getPublicKey() || 'Generating...')
        setAgentConfig({
            apiUrl: userData.apiUrl,
            llmBaseUrl: userData.llmBaseUrl || 'https://api.openai.com/v1',
            apiKey: userData.apiKey || '',
            model: userData.model || 'gpt-4o',
            field: userData.field || ''
        })
    }, [])

    const handleUpdateConfig = async () => {
        setUpdating(true)
        try {
            setApiUrl(agentConfig.apiUrl)
            const { default: api } = await import('../services/api')
            await api.post('/api/v1/config', {
                base_url: agentConfig.llmBaseUrl,
                api_key: agentConfig.apiKey,
                model: agentConfig.model,
                research_field: agentConfig.field
            })
            // Update local storage
            localStorage.setItem('bp_api_url', agentConfig.apiUrl)
            localStorage.setItem('bp_llm_base_url', agentConfig.llmBaseUrl)
            localStorage.setItem('bp_api_key', agentConfig.apiKey)
            localStorage.setItem('bp_model', agentConfig.model)
            localStorage.setItem('bp_field', agentConfig.field)

            // Refresh local user state
            setUser(Store.getUser())
            alert('Agent Configuration Updated!')
        } catch (err) {
            console.error(err)
            alert('Failed to update configuration')
        } finally {
            setUpdating(false)
        }
    }

    if (!user) return null

    return (
        <div className="max-w-3xl mx-auto">
            <h1 className="text-2xl font-bold mb-6 text-slate-800">Profile & Wallet</h1>

            <div className="grid md:grid-cols-2 gap-6">
                <div className="md:col-span-2">
                    <Card title="Identity" icon={User}>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs text-slate-500 uppercase font-bold">Email</label>
                                <p className="font-medium text-slate-800">{user.email}</p>
                            </div>
                            <div>
                                <label className="text-xs text-slate-500 uppercase font-bold">Research Field</label>
                                <p className="font-medium text-slate-800">{user.field}</p>
                            </div>
                        </div>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Card title="Wallet Address" icon={Shield}>
                        <div className="bg-slate-50 p-4 rounded-lg break-all font-mono text-xs text-slate-600 border border-slate-200">
                            {pubKey}
                        </div>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Card title="Balance" icon={CreditCard}>
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-bold text-slate-800">1,250.00</span>
                            <span className="text-sm font-medium text-slate-500">STATER</span>
                        </div>
                        <p className="text-xs text-green-600 mt-2 font-medium">+50 STATER (Reward) • Today</p>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Card title="Agent Settings" icon={Settings}>
                        <Input
                            label="Agent Node URL"
                            value={agentConfig.apiUrl}
                            onChange={e => setAgentConfig({ ...agentConfig, apiUrl: e.target.value })}
                        />
                        <Input
                            label="LLM Provider Base URL"
                            placeholder="e.g. https://api.openai.com/v1"
                            value={agentConfig.llmBaseUrl}
                            onChange={e => setAgentConfig({ ...agentConfig, llmBaseUrl: e.target.value })}
                        />
                        <Input
                            label="API Key"
                            type="password"
                            value={agentConfig.apiKey}
                            onChange={e => setAgentConfig({ ...agentConfig, apiKey: e.target.value })}
                        />
                        <Input
                            label="Model Name"
                            placeholder="e.g. gpt-4o, claude-3-5-sonnet"
                            value={agentConfig.model}
                            onChange={e => setAgentConfig({ ...agentConfig, model: e.target.value })}
                        />
                        <Input
                            label="Monitoring Research Field"
                            placeholder="e.g. AI Governance, Quantum Computing"
                            value={agentConfig.field}
                            onChange={e => setAgentConfig({ ...agentConfig, field: e.target.value })}
                        />
                        <button
                            onClick={handleUpdateConfig}
                            disabled={updating}
                            className="w-full mt-2 bg-primary text-white py-2 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-70"
                        >
                            {updating ? 'Updating...' : 'Update Configuration'}
                        </button>
                    </Card>
                </div>
            </div>

            <button
                onClick={Store.clear}
                className="mt-8 flex items-center justify-center gap-2 w-full p-4 text-red-600 bg-red-50 hover:bg-red-100 rounded-xl transition-colors font-medium"
            >
                <LogOut size={18} />
                Reset Identity on this Device
            </button>
        </div>
    )
}

export default Profile
