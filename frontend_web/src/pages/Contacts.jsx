import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { getGroups } from '../services/api'
import { Users, User, MessageSquare, ExternalLink } from 'lucide-react'
import { formatTime } from '../utils/date'

const Contacts = () => {
    const navigate = useNavigate()
    const [activeTab, setActiveTab] = useState('agents')
    const [peers, setPeers] = useState([])
    const [groups, setGroups] = useState([])
    const [loading, setLoading] = useState(true)

    const fetchContacts = async () => {
        try {
            const [pRes, gData] = await Promise.all([
                api.get('/api/v1/p2p/peers'),
                getGroups()
            ])
            setPeers(pRes.data || [])
            setGroups(gData || [])
        } catch (err) {
            console.error("Failed to load contacts", err)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchContacts()
    }, [])

    const handleChat = (id) => {
        // Navigate to Chat with session query param? 
        // For now, Chat.jsx doesn't read query params yet, but we will add support if needed.
        // Actually best way: pass state or use Context. 
        // Simplest: Just navigate to /chat. Chat.jsx defaults to first session.
        // To make it better: Update Chat.jsx to read ?session=ID
        navigate(`/chat?session=${id}`)
    }

    return (
        <div className="p-6 max-w-4xl mx-auto">
            <h1 className="text-2xl font-bold text-slate-800 mb-6">Contacts & Groups</h1>

            {/* Tabs */}
            <div className="flex gap-4 mb-6 border-b border-slate-200">
                <button
                    onClick={() => setActiveTab('agents')}
                    className={`pb-2 px-4 font-medium transition-colors ${activeTab === 'agents' ? 'text-primary border-b-2 border-primary' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    Agents ({peers.length})
                </button>
                <button
                    onClick={() => setActiveTab('groups')}
                    className={`pb-2 px-4 font-medium transition-colors ${activeTab === 'groups' ? 'text-primary border-b-2 border-primary' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    Groups ({groups.length})
                </button>
            </div>

            {loading ? (
                <div className="text-center py-10 text-slate-400">Loading contacts...</div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

                    {/* AGENTS LIST */}
                    {activeTab === 'agents' && peers.map(peer => (
                        <div key={peer.node_id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 hover:shadow-md transition-shadow">
                            <div className="flex items-start justify-between mb-3">
                                <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center text-blue-500">
                                    <User size={20} />
                                </div>
                                <div className="flex flex-col items-end gap-1">
                                    <div className="flex items-center gap-1.5">
                                        <div className={`w-2 h-2 rounded-full ${peer.status === 'online' ? 'bg-green-500 animate-pulse' : 'bg-slate-300'}`} />
                                        <span className={`text-[10px] font-bold uppercase tracking-wider ${peer.status === 'online' ? 'text-green-600' : 'text-slate-400'}`}>
                                            {peer.status}
                                        </span>
                                    </div>
                                    {peer.last_seen && (
                                        <span className="text-[9px] text-slate-400">
                                            {formatTime(peer.last_seen)}
                                        </span>
                                    )}
                                </div>
                            </div>
                            <h3 className="font-bold text-slate-800 mb-1">{peer.name || 'Unknown Agent'}</h3>
                            <p className="text-xs text-slate-400 font-mono mb-4 truncate" title={peer.node_id}>
                                {peer.node_id}
                            </p>
                            <button
                                onClick={() => handleChat(peer.node_id)}
                                className="w-full py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors"
                            >
                                <MessageSquare size={16} /> Send Message
                            </button>
                        </div>
                    ))}

                    {/* GROUPS LIST */}
                    {activeTab === 'groups' && groups.map(group => (
                        <div key={group.group_id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 hover:shadow-md transition-shadow relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-purple-100 to-transparent -mr-8 -mt-8 rounded-full" />

                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-12 h-12 rounded-xl bg-purple-50 flex items-center justify-center text-purple-600">
                                    <Users size={24} />
                                </div>
                                <div>
                                    <h3 className="font-bold text-slate-800">{group.name || `Group ${group.group_id.substring(0, 6)}...`}</h3>
                                    <div className="flex gap-2 mt-1">
                                        <span className="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">
                                            L{group.level}
                                        </span>
                                        <span className="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">
                                            {group.members ? group.members.length : 0} Members
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <button
                                    onClick={() => handleChat(group.group_id)}
                                    className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors shadow-sm"
                                >
                                    <MessageSquare size={16} /> Open Chat
                                </button>
                            </div>
                        </div>
                    ))}

                    {/* EMPTY STATES */}
                    {activeTab === 'agents' && peers.length === 0 && (
                        <div className="col-span-full py-10 text-center text-slate-400 italic">
                            No other agents found on the network.
                        </div>
                    )}
                    {activeTab === 'groups' && groups.length === 0 && (
                        <div className="col-span-full py-10 text-center text-slate-400 italic">
                            You are not a member of any groups yet.
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

export default Contacts
