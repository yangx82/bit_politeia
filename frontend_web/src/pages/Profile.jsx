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
        bootstrapUrl: '',
        llmBaseUrl: '',
        apiKey: '',
        model: '',
        field: '',
        verboseLlm: false,
        bootstrapVerify: true,
        p2pReplyDelay: 60,
        agentLanguage: '中文',
        ralphWiggumMode: false
    })
    const [updating, setUpdating] = useState(false)

    const fetchStatus = async () => {
        try {
            const { default: api } = await import('../services/api')
            const response = await api.get('/api/v1/status')
            const statusData = response.data
            setUser(prev => ({
                ...prev,
                balance: statusData.balance,
                relayConnected: statusData.relay_connected,
                nodeId: statusData.node_id,
                agentPubKey: statusData.public_key
            }))
        } catch (err) {
            console.error('Failed to fetch balance:', err)
        }
    }

    useEffect(() => {
        const userData = Store.getUser()
        setUser(userData)
        setPubKey(CryptoService.getPublicKey() || 'Generating...')
        setAgentConfig({
            apiUrl: userData.apiUrl,
            bootstrapUrl: userData.bootstrapUrl || 'http://localhost:8000',
            llmBaseUrl: userData.llmBaseUrl || 'https://api.openai.com/v1',
            apiKey: userData.apiKey || '',
            model: userData.model || 'gpt-4o',
            field: userData.field || '',
            verboseLlm: userData.verboseLlm || false,
            bootstrapVerify: userData.bootstrapVerify !== undefined ? userData.bootstrapVerify : true,
            name: userData.name || 'Agent',
            personality: userData.personality || 'Professional',
            p2pReplyDelay: userData.p2pReplyDelay || 60,
            agentLanguage: userData.agentLanguage || '中文',
            ralphWiggumMode: userData.ralphWiggumMode || false
        })
        fetchStatus()
    }, [])

    const handleUpdateConfig = async () => {
        setUpdating(true)
        try {
            setApiUrl(agentConfig.apiUrl)
            const { default: api } = await import('../services/api')
            const response = await api.post('/api/v1/config', {
                base_url: agentConfig.llmBaseUrl,
                api_key: agentConfig.apiKey,
                model: agentConfig.model,
                research_field: agentConfig.field,
                bootstrap_url: agentConfig.bootstrapUrl,
                verbose_llm: agentConfig.verboseLlm,
                bootstrap_verify: agentConfig.bootstrapVerify,
                name: agentConfig.name,
                personality: agentConfig.personality,
                p2p_reply_delay: Number(agentConfig.p2pReplyDelay),
                agent_language: agentConfig.agentLanguage,
                ralph_wiggum_mode: agentConfig.ralphWiggumMode
            })

            const updatedStatus = response.data

            // Update local storage
            localStorage.setItem('bp_api_url', agentConfig.apiUrl)
            localStorage.setItem('bp_llm_base_url', agentConfig.llmBaseUrl)
            localStorage.setItem('bp_api_key', agentConfig.apiKey)
            localStorage.setItem('bp_model', agentConfig.model)
            localStorage.setItem('bp_field', agentConfig.field)
            localStorage.setItem('bp_bootstrap_url', agentConfig.bootstrapUrl)
            localStorage.setItem('bp_verbose_llm', agentConfig.verboseLlm)
            localStorage.setItem('bp_bootstrap_verify', agentConfig.bootstrapVerify)
            localStorage.setItem('bp_name', agentConfig.name)
            localStorage.setItem('bp_personality', agentConfig.personality)
            localStorage.setItem('bp_p2p_reply_delay', agentConfig.p2pReplyDelay)
            localStorage.setItem('bp_agent_language', agentConfig.agentLanguage)
            localStorage.setItem('bp_ralph_wiggum_mode', agentConfig.ralphWiggumMode)

            // Refresh local user state with new balance
            const localUser = Store.getUser()
            setUser({ ...localUser, balance: updatedStatus.balance })
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
                                <label className="text-xs text-slate-500 uppercase font-bold">Agent Name</label>
                                <p className="font-medium text-slate-800">{agentConfig.name || 'Agent'}</p>
                            </div>
                            <div>
                                <label className="text-xs text-slate-500 uppercase font-bold">Email</label>
                                <p className="font-medium text-slate-800">{user.email}</p>
                            </div>
                            <div>
                                <label className="text-xs text-slate-500 uppercase font-bold">Research Field</label>
                                <p className="font-medium text-slate-800">{user.field}</p>
                            </div>
                            <div>
                                <label className="text-xs text-slate-500 uppercase font-bold">Network Status</label>
                                <div className="flex items-center gap-2 mt-1">
                                    <div className={`w-2 h-2 rounded-full ${user.relayConnected ? 'bg-green-500' : 'bg-slate-300'}`} />
                                    <span className="font-medium text-slate-800 text-sm">
                                        {user.relayConnected ? 'Internet P2P (Relay Connected)' : 'LAN P2P (Direct Only)'}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Card title="Agent Identity (Node ID)" icon={Shield}>
                        <div className="bg-slate-50 p-4 rounded-lg break-all font-mono text-xs text-slate-600 border border-slate-200">
                            {user.nodeId || 'Connecting to Node...'}
                        </div>
                        <p className="text-[10px] text-slate-400 mt-2 italic">This is your Agent's persistent P2P identity. It owns the balance and reputation shown below.</p>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Card title="Operator Identity (Current Device)" icon={User}>
                        <div className="bg-slate-50 p-4 rounded-lg break-all font-mono text-xs text-slate-400 border border-slate-200">
                            {pubKey}
                        </div>
                        <p className="text-[10px] text-slate-400 mt-2 italic">This key identifies your current browser as the authorized operator for this node. Resetting identity updates this key.</p>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Card title="Balance" icon={CreditCard}>
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-bold text-slate-800">
                                {user?.balance?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
                            </span>
                            <span className="text-sm font-medium text-slate-500">STATER</span>
                        </div>
                        <p className="text-xs text-green-600 mt-2 font-medium">Synced with Agent Node</p>
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
                            label="Bootstrap Server URL"
                            value={agentConfig.bootstrapUrl}
                            onChange={e => setAgentConfig({ ...agentConfig, bootstrapUrl: e.target.value })}
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
                            label="Agent Name"
                            value={agentConfig.name}
                            onChange={e => setAgentConfig({ ...agentConfig, name: e.target.value })}
                        />
                        <div className="flex flex-col gap-1 mb-3">
                            <label className="text-xs text-slate-500 uppercase font-bold">Personality Guidelines</label>
                            <textarea
                                className="p-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                                rows="3"
                                value={agentConfig.personality}
                                onChange={e => setAgentConfig({ ...agentConfig, personality: e.target.value })}
                            />
                        </div>

                        <Input
                            label="Agent Output Language"
                            placeholder="e.g. 中文, English"
                            value={agentConfig.agentLanguage}
                            onChange={e => setAgentConfig({ ...agentConfig, agentLanguage: e.target.value })}
                        />

                        <Input
                            label="Monitoring Research Field"
                            placeholder="e.g. AI Governance, Quantum Computing"
                            value={agentConfig.field}
                            onChange={e => setAgentConfig({ ...agentConfig, field: e.target.value })}
                        />

                        <Input
                            label="P2P Reply Delay (seconds)"
                            type="number"
                            min="0"
                            placeholder="e.g. 60"
                            value={agentConfig.p2pReplyDelay}
                            onChange={e => setAgentConfig({ ...agentConfig, p2pReplyDelay: e.target.value })}
                            title="How many seconds the Agent should wait before broadcasting a P2P reply to the network."
                        />

                        <div className="flex items-center mt-4 mb-2">
                            <input
                                type="checkbox"
                                id="verboseLlm"
                                checked={agentConfig.verboseLlm}
                                onChange={e => setAgentConfig({ ...agentConfig, verboseLlm: e.target.checked })}
                                className="w-4 h-4 text-primary focus:ring-primary border-slate-300 rounded"
                            />
                            <label htmlFor="verboseLlm" className="ml-2 text-sm text-slate-600">Enable Verbose LLM Output</label>
                        </div>
                        <div className="flex items-center mb-4">
                            <input
                                type="checkbox"
                                id="bootstrapVerify"
                                checked={agentConfig.bootstrapVerify}
                                onChange={e => setAgentConfig({ ...agentConfig, bootstrapVerify: e.target.checked })}
                                className="w-4 h-4 text-primary focus:ring-primary border-slate-300 rounded"
                            />
                            <label htmlFor="bootstrapVerify" className="ml-2 text-sm text-slate-600">Verify Bootstrap SSL Certificate</label>
                        </div>
                        <div className="flex items-start mb-4 p-3 bg-red-50 border border-red-100 rounded-lg">
                            <div className="flex items-center h-5">
                                <input
                                    type="checkbox"
                                    id="ralphWiggumMode"
                                    checked={agentConfig.ralphWiggumMode}
                                    onChange={e => setAgentConfig({ ...agentConfig, ralphWiggumMode: e.target.checked })}
                                    className="w-4 h-4 text-red-600 focus:ring-red-600 border-slate-300 rounded"
                                />
                            </div>
                            <div className="ml-2 text-sm">
                                <label htmlFor="ralphWiggumMode" className="font-semibold text-red-800">Enable Ralph Wiggum Loop (Continuous Execution)</label>
                                <p className="text-red-600 mt-1 text-xs">WARNING: Bypasses the 50-step execution limit. The agent will run endlessly until the task is complete or it hits the maximum 5 loop epochs guardrail. Use with caution as this may consume high API credits.</p>
                            </div>
                        </div>

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
