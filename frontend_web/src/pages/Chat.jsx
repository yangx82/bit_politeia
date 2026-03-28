import React, { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { Send, Search, Users, User, MessageSquare, Clock, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { formatTime } from '../utils/date'



const Chat = () => {
    // URL Params
    const [searchParams] = useSearchParams()
    const urlSessionId = searchParams.get('session')

    // State
    const [messages, setMessages] = useState([])
    const [peersMap, setPeersMap] = useState({})
    const [groupsMap, setGroupsMap] = useState({})
    const [loading, setLoading] = useState(true)

    const [activeSessionId, setActiveSessionId] = useState(null)
    const [agentLogs, setAgentLogs] = useState([]) // Accumulated thoughts and tool logs

    const [input, setInput] = useState('')
    const [sending, setSending] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')

    // New: Date Filtering states (Session-specific)
    const [startDate, setStartDate] = useState('')
    const [endDate, setEndDate] = useState('')

    // Agent Identity for display
    const [agentName, setAgentName] = useState('Agent')

    // Refs
    const bottomRef = useRef(null)
    const prevMessagesLen = useRef(0)

    // --- DATA FETCHING ---



    // --- SESSION LOGIC ---

    const isInternalSender = (sender) => {
        // Core internal actors
        if (['user', 'agent', 'system', 'resident'].includes(sender)) return true
        // Channel messages like "[feishu] user_id" are also internal resident-agent comms
        if (sender.startsWith('[') && (sender.includes('feishu') || sender.includes('telegram'))) return true
        return false
    }

    // Derived state: Sessions
    // --- DATA FETCHING ---
    const fetchData = async () => {
        try {
            const [msgRes, peerRes, groupRes, statusRes] = await Promise.all([
                api.get('/api/v1/history'),
                api.get('/api/v1/p2p/peers'),
                api.get('/api/v1/p2p/groups'),
                api.get('/api/v1/status')
            ])

            // Deduplicate messages by ID to prevent key warnings/flicker
            const uniqueMsgs = Array.from(new Map(msgRes.data.map(m => [m.id, m])).values())
            // Sort by timestamp
            uniqueMsgs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
            setMessages(uniqueMsgs)

            // Update Agent Name from Backend
            if (statusRes.data.name) {
                setAgentName(statusRes.data.name)
            }

            // Map peers: ID -> Name
            const pMap = {}
            peerRes.data.forEach(p => {
                pMap[p.node_id] = p.name || 'Unknown Agent'
            })
            setPeersMap(pMap)

            // Map groups: ID -> Name (or true if just existence check needed, but name is better)
            const gMap = {}
            groupRes.data.forEach(g => {
                gMap[g.group_id] = g.name || `Group ${g.group_id.substring(0, 8)}`
            })
            setGroupsMap(gMap)

        } catch (err) {
            console.error("Failed to fetch chat data", err)
        }
    }

    // Initial Load & Polling
    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 3000) // Poll every 3s
        return () => clearInterval(interval)
    }, [])

    // --- WEBSOCKET FOR REALTIME THOUGHTS ---
    useEffect(() => {
        const apiUrl = localStorage.getItem('bp_api_url') || 'http://localhost:8000';
        let wsUrl = apiUrl.replace(/^http/, 'ws');
        if (!wsUrl.endsWith('/')) {
            wsUrl += '/';
        }
        wsUrl += 'ws/gateway';

        let ws = null;
        let retryTimeout = null;

        const connect = () => {
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('WebSocket connected for realtime thoughts');
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    // Handle GatewayEvent protocol (type='event', event_type='agent_xxx')
                    if (data.type === 'event') {
                        const eventType = data.event_type;
                        const payload = data.payload || {};

                        if (['agent_thought', 'agent_tool_call', 'agent_tool_result'].includes(eventType)) {
                            let formattedContent = payload.content;
                            const msgType = eventType.replace('agent_', '');

                            if (msgType === 'tool_call' && payload.metadata?.tool) {
                                formattedContent = `[🤔 Invoking ${payload.metadata.tool}] ${payload.content || ''}`;
                            } else if (msgType === 'tool_result' && payload.metadata?.tool) {
                                formattedContent = `[✅ Result from ${payload.metadata.tool}]`;
                            }

                            setAgentLogs(prev => [...prev, {
                                id: Date.now() + Math.random(),
                                type: msgType,
                                content: formattedContent,
                                timestamp: new Date()
                            }]);
                            scrollToBottom();
                        } else if (eventType === 'agent_status_update') {
                            const { message_id, status } = payload.metadata || {};
                            if (message_id && status) {
                                setMessages(prev => prev.map(m => 
                                    m.id === message_id ? { ...m, status } : m
                                ));
                            }
                        } else if (eventType === 'agent_message') {
                            // Clear logs when a final message arrives
                            setAgentLogs([]);
                        }
                    }
                } catch (e) {
                    console.error('WS Parse error', e);
                }
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected, retrying in 3s...');
                retryTimeout = setTimeout(connect, 3000);
            };
        };

        connect();

        return () => {
            if (retryTimeout) clearTimeout(retryTimeout);
            if (ws) {
                ws.onclose = null; // Prevent reconnect on unmount
                ws.close();
            }
        };
    }, []);

    // --- SESSION MANAGEMENT ---
    const sessions = useMemo(() => {
        const sessMap = {}
        const query = searchQuery.toLowerCase().trim()

        messages.forEach(msg => {
            // Use session_id if available (new backend), fallback to sender (old logic)
            let sessionId = msg.session_id || msg.chat_id || (isInternalSender(msg.sender) ? 'resident' : msg.sender)

            // Merge Bridge messages into resident session
            if (
                (msg.sender && (
                    msg.sender.startsWith('[feishu]') ||
                    msg.sender.startsWith('[telegram]') ||
                    msg.sender.startsWith('[gateway]')
                )) ||
                (typeof sessionId === 'string' && (
                    sessionId.startsWith('[feishu]') ||
                    sessionId.startsWith('[telegram]') ||
                    sessionId.startsWith('[gateway]')
                ))
            ) {
                sessionId = 'resident'
            }

            if (sessionId.startsWith('[p2p] ')) sessionId = sessionId.replace('[p2p] ', '')

            if (!sessMap[sessionId]) {
                let displayName = sessionId

                if (sessionId === 'resident') {
                    displayName = `${agentName} (My Agent)`
                } else if (groupsMap[sessionId]) {
                    displayName = groupsMap[sessionId]
                } else if (peersMap[sessionId]) {
                    displayName = peersMap[sessionId]
                } else {
                    const lowerId = sessionId.toLowerCase()
                    const peerKey = Object.keys(peersMap).find(k => k.toLowerCase() === lowerId)
                    if (peerKey) {
                        displayName = peersMap[peerKey]
                    } else {
                        displayName = sessionId.substring(0, 8)
                    }
                }

                sessMap[sessionId] = {
                    id: sessionId,
                    type: (sessionId === 'resident') ? 'resident' : 'direct',
                    name: displayName,
                    lastMessage: msg,
                    unread: 0,
                    avatar: sessionId === 'resident' ? '🤖' : (groupsMap[sessionId] ? '👥' : '👤'),
                    allMessagesContent: '' // To store accumulated content for search
                }
            }

            // Update last message
            if (new Date(msg.timestamp) > new Date(sessMap[sessionId].lastMessage.timestamp)) {
                sessMap[sessionId].lastMessage = msg
            }

            // Accumulate message content for deep search
            sessMap[sessionId].allMessagesContent += ' ' + (msg.content || '').toLowerCase()
        })

        let result = Object.values(sessMap)

        // Apply Global Deep Search
        if (query) {
            result = result.filter(s =>
                s.name.toLowerCase().includes(query) ||
                s.allMessagesContent.includes(query)
            )
        }

        return result.sort((a, b) =>
            new Date(b.lastMessage.timestamp) - new Date(a.lastMessage.timestamp)
        )
    }, [messages, peersMap, groupsMap, agentName, searchQuery])

    // --- NAVIGATION & SELECTION ---

    // Sync activeSessionId with URL param on mount/change
    useEffect(() => {
        if (urlSessionId) {
            setActiveSessionId(urlSessionId)
        } else if (!activeSessionId && sessions.length > 0) {
            setActiveSessionId(sessions[0].id)
        }
    }, [urlSessionId, sessions, activeSessionId])


    // --- RENDER HELPERS ---

    const getDisplayMessages = () => {
        if (!activeSessionId) return []

        return messages.filter(msg => {
            // Special handling for Resident Session (Merged View)
            if (activeSessionId === 'resident') {
                // Return true if:
                // 1. Internal Sender (User/Agent/System)
                // 2. Bridge Message (Sender starts with [feishu] etc)
                // 3. Bridge Message (ChatID starts with [feishu] etc)
                // 4. Explicit ChatID == 'resident'

                // 1. Explicitly EXCLUDE any outgoing P2P messages from polluting the Resident console
                // This MUST happen before isInternalSender(msg.sender) check because agent is an internal sender.
                if (msg.session_id && msg.session_id !== 'resident' && !msg.session_id.startsWith('[')) {
                    return false;
                }

                if (msg.session_id === 'resident') return true;

                return isInternalSender(msg.sender) ||
                    (msg.sender && (
                        msg.sender.startsWith('[feishu]') ||
                        msg.sender.startsWith('[telegram]') ||
                        msg.sender.startsWith('[gateway]')
                    )) ||
                    (msg.session_id && (
                        msg.session_id.startsWith('[feishu]') ||
                        msg.session_id.startsWith('[telegram]') ||
                        msg.session_id.startsWith('[gateway]')
                    ))
            }

            // Normal Sessions (P2P, Groups, or specific unmerged sessions)
            if (msg.session_id) {
                return msg.session_id === activeSessionId
            }
            return msg.sender === activeSessionId
        }).filter(msg => {
            // Apply Date Filter if set
            if (startDate) {
                const sDate = new Date(startDate)
                sDate.setHours(0, 0, 0, 0)
                if (new Date(msg.timestamp) < sDate) return false
            }
            if (endDate) {
                const eDate = new Date(endDate)
                eDate.setHours(23, 59, 59, 999)
                if (new Date(msg.timestamp) > eDate) return false
            }
            return true
        })
    }

    const handleSend = async (e) => {
        e.preventDefault()
        if (!input.trim()) return

        setSending(true)
        const content = input
        setInput('')
        setAgentLogs([])

        try {
            if (activeSessionId === 'resident') {
                // Internal Instruction
                await api.post('/api/v1/chat/instruction', { content })
            } else {
                // P2P Message (Now converted to suggestion in backend)
                const res = await api.post('/api/v1/p2p/send', {
                    target_id: activeSessionId,
                    content: { text: content }
                })
                // Optional: alert the user it was forwarded, or just let them see the system message
                console.log("Suggestion forwarded:", res.data);
            }
            // Give backend a moment to log the instruction before fetching
            setTimeout(() => {
                fetchData()
            }, 500)
        } catch (err) {
            console.error("Send failed", err)
            alert("Failed to send message")
        } finally {
            setSending(false)
        }
    }

    // Scroll Management
    const scrollToBottom = () => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }

    // Effect: Handle Messages Update (Smart Scroll)
    useEffect(() => {
        // Only scroll if:
        // 1. Initial Load (loading was just false)
        // 2. New message added AND user was near bottom
        // 3. User sent a message (we can track this via a ref or assumption)

        // For now, simple logic:
        // If we are significantly deeper than before (new messages), scroll down 
        // ONLY IF we were already near bottom. 
        // But since we don't track scroll position easily without more event listeners,
        // let's do:
        // - Indiscriminate scroll on First Load
        // - Scroll if new message is from 'me' or 'user' (self)
        // - Otherwise, show "New Message" badge if not at bottom? (Too complex for now)

        // Practical Fix:
        // If length changed...
        if (messages.length > prevMessagesLen.current) {
            const lastMsg = messages[messages.length - 1]
            // If I sent it, always scroll
            const isMe = lastMsg.sender === 'user' || lastMsg.sender === 'me'

            if (isMe) {
                scrollToBottom()
            } else {
                // If from others, only scroll if we are "close" to bottom?
                // Hard to detect "close" without onScroll listener state.
                // Let's just scroll for now to ensure visibility, BUT
                // we need to prevent scrolling when just polling same data.
                // The issue user reported "forces scroll" suggests it happens even when NO new messages, 
                // just because `messages` ref changes.

                // CHECK: prevMessagesLen check solves the "no new message" scroll.
                scrollToBottom()
            }
        }
        prevMessagesLen.current = messages.length
    }, [messages])

    // Effect: Session Change Scroll
    useEffect(() => {
        scrollToBottom()
    }, [activeSessionId])


    const [isRefreshing, setIsRefreshing] = useState(false)

    const handleManualRefresh = async () => {
        setIsRefreshing(true)
        await fetchData()
        setTimeout(() => setIsRefreshing(false), 500) // Ensure at least 500ms spin
    }

    return (
        <div className="flex h-[calc(100vh-2rem)] bg-white rounded-2xl shadow-sm overflow-hidden border border-slate-200">

            {/* LEFT SIDEBAR: SESSIONS */}
            <div className="w-80 shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col">
                {/* Search Bar */}
                <div className="p-4 border-b border-slate-200">
                    <div className="relative">
                        <Search size={16} className="absolute left-3 top-3 text-slate-400" />
                        <input
                            className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                            placeholder="Search chats..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                        />
                    </div>
                </div>

                {/* Session List */}
                <div className="flex-1 overflow-y-auto">
                    {sessions.map(session => (
                        <div
                            key={session.id}
                            onClick={() => setActiveSessionId(session.id)}
                            className={`p-4 flex items-center gap-3 cursor-pointer hover:bg-slate-100 transition-colors ${activeSessionId === session.id ? 'bg-white border-l-4 border-primary shadow-sm' : ''}`}
                        >
                            {/* Avatar */}
                            <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-lg shadow-sm border border-indigo-50">
                                {session.avatar}
                            </div>

                            {/* Info */}
                            <div className="flex-1 min-w-0">
                                <div className="flex justify-between items-baseline mb-1">
                                    <h3 className={`text-sm font-semibold truncate ${activeSessionId === session.id ? 'text-primary' : 'text-slate-800'}`}>
                                        {session.name}
                                    </h3>
                                    <span className="text-[10px] text-slate-400">
                                        {formatTime(session.lastMessage.timestamp)}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <p className="text-xs text-slate-500 truncate max-w-[140px]">
                                        {session.lastMessage.content}
                                    </p>
                                    {session.unread > 0 && (
                                        <span className="bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
                                            {session.unread}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}

                    {sessions.length === 0 && (
                        <div className="p-8 text-center text-slate-400 text-sm italic">
                            No active conversations.
                        </div>
                    )}
                </div>
            </div>

            {/* RIGHT MAIN: CHAT WINDOW */}
            <div className="flex-1 flex flex-col bg-slate-50/30 min-w-0">
                {activeSessionId ? (
                    <>
                        {/* Header */}
                        <div className="h-16 border-b border-slate-200 bg-white px-6 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center">
                                    {activeSessionId === 'resident' ? '🤖' : '👤'}
                                </div>
                                <div>
                                    <h2 className="font-bold text-slate-800">
                                        {activeSessionId === 'resident'
                                            ? `${agentName} (My Agent)`
                                            : (groupsMap[activeSessionId] || peersMap[activeSessionId] || activeSessionId)}
                                    </h2>
                                    <p className="text-xs text-slate-500 flex items-center gap-1">
                                        {activeSessionId === 'resident' ? 'Always Active' : (groupsMap[activeSessionId] ? 'P2P Group' : 'P2P Connection')}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                {/* Date Range Filter */}
                                <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 mr-2">
                                    <input
                                        type="date"
                                        className="bg-transparent text-[11px] text-slate-600 focus:outline-none"
                                        value={startDate}
                                        onChange={e => setStartDate(e.target.value)}
                                        title="Start Date"
                                    />
                                    <span className="text-slate-300">-</span>
                                    <input
                                        type="date"
                                        className="bg-transparent text-[11px] text-slate-600 focus:outline-none"
                                        value={endDate}
                                        onChange={e => setEndDate(e.target.value)}
                                        title="End Date"
                                    />
                                    {(startDate || endDate) && (
                                        <button
                                            onClick={() => { setStartDate(''); setEndDate(''); }}
                                            className="ml-1 text-slate-400 hover:text-red-500 text-[10px]"
                                            title="Clear Filter"
                                        >
                                            ✕
                                        </button>
                                    )}
                                </div>

                                {/* Refresh/History Manual Button */}
                                <button
                                    onClick={handleManualRefresh}
                                    title="Refresh & Load History"
                                    className="p-2 hover:bg-slate-100 rounded-full text-slate-400 transition-all active:scale-95"
                                >
                                    <div className={`${isRefreshing ? 'animate-spin' : ''}`}>
                                        <div className={`${isRefreshing ? 'text-primary' : ''}`}>
                                            <MessageSquare size={20} />
                                        </div>
                                    </div>
                                </button>
                            </div>
                        </div>

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto p-6 space-y-4">
                            {/* Top Spacer for comfortable scrolling */}
                            <div className="h-4"></div>

                            {getDisplayMessages().map((msg, idx) => {
                                // Determine Alignment and Style based on Role
                                let align = 'left' // 'left' or 'right'
                                let styleClass = ''
                                let timeClass = ''

                                const isUser = msg.sender === 'user' ||
                                    msg.sender === 'resident' ||
                                    (msg.sender && (
                                        msg.sender.startsWith('[feishu]') ||
                                        msg.sender.startsWith('[telegram]') ||
                                        msg.sender.startsWith('[gateway]')
                                    ))
                                const isAgent = msg.sender === 'agent' || msg.sender === 'me'
                                const isSystem = msg.sender === 'system'

                                if (isSystem) {
                                    return (
                                        <div key={msg.id || idx} className="flex justify-center my-4">
                                            <span className="text-[10px] bg-slate-200 text-slate-500 px-3 py-1 rounded-full">
                                                {msg.content}
                                            </span>
                                        </div>
                                    )
                                }

                                if (activeSessionId === 'resident') {
                                    // Scenario 1: Resident Chat
                                    // User -> Right (Green)
                                    // Agent -> Left (Blue)
                                    if (isUser) {
                                        align = 'right'
                                        styleClass = 'bg-emerald-100 text-emerald-900 border border-emerald-200 rounded-tr-none'
                                        timeClass = 'text-emerald-700/60'
                                    } else if (isAgent) {
                                        align = 'left'
                                        styleClass = 'bg-primary text-white rounded-tl-none'
                                        timeClass = 'text-blue-100'
                                    } else {
                                        // Fallback?
                                        align = 'left'
                                        styleClass = 'bg-white border border-slate-200 rounded-tl-none'
                                        timeClass = 'text-slate-400'
                                    }
                                } else {
                                    // Scenario 2: P2P Chat
                                    // Agent ("Me") -> Right (Blue)
                                    // Peer -> Left (White)
                                    // User (if injecting instruction) -> Right (Green)
                                    if (isAgent) {
                                        align = 'right'
                                        styleClass = 'bg-primary text-white rounded-tr-none'
                                        timeClass = 'text-blue-100'
                                    } else if (isUser) {
                                        align = 'right'
                                        styleClass = 'bg-emerald-100 text-emerald-900 border border-emerald-200 rounded-tr-none'
                                        timeClass = 'text-emerald-700/60'
                                    } else {
                                        // Peer
                                        align = 'left'
                                        styleClass = 'bg-white border border-slate-200 rounded-tl-none'
                                        timeClass = 'text-slate-400'
                                    }
                                }


                                // Prepare Content
                                let displayContent = msg.content

                                // Tag: From Source
                                if (msg.sender && msg.sender.startsWith('[')) {
                                    const match = msg.sender.match(/^\[(.*?)\].*/)
                                    if (match && match[1] !== 'p2p') {
                                        displayContent = (
                                            <span>
                                                {msg.content} <span className="text-[10px] opacity-60 ml-1">(From {match[1]})</span>
                                            </span>
                                        )
                                    }
                                }

                                // Tag: To Target
                                if (isAgent && msg.session_id && msg.session_id.startsWith('[')) {
                                    const match = msg.session_id.match(/^\[(.*?)\].*/)
                                    if (match && match[1] !== 'p2p') {
                                        displayContent = (
                                            <span>
                                                {msg.content} <span className="text-[10px] opacity-60 ml-1">(To {match[1]})</span>
                                            </span>
                                        )
                                    }
                                }

                                return (
                                    <div key={msg.id || idx} className={`flex ${align === 'right' ? 'justify-end' : 'justify-start'} mb-4`}>
                                        <div className={`max-w-[70%] rounded-2xl p-4 shadow-sm ${styleClass}`}>
                                            <div className="text-sm whitespace-pre-wrap leading-relaxed">{displayContent}</div>
                                            <div className={`text-[10px] mt-1 flex items-center justify-end gap-1 ${timeClass}`}>
                                                {formatTime(msg.timestamp)}
                                                {isAgent && activeSessionId !== 'resident' && (
                                                    <span title={msg.status || 'pending'}>
                                                        {(msg.status === 'pending' || !msg.status) && (
                                                            <Loader2 size={12} className="animate-spin text-blue-400" />
                                                        )}
                                                        {msg.status === 'sent' && (
                                                            <CheckCircle2 size={12} className="text-emerald-500 fill-emerald-50" />
                                                        )}
                                                        {msg.status === 'failed' && (
                                                            <AlertCircle size={12} className="text-rose-500" />
                                                        )}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )
                            })}
                            {/* Ephemeral Thought logs for Resident Session */}
                            {activeSessionId === 'resident' && agentLogs.length > 0 && (
                                <div className="flex w-full justify-start mb-4 group transition-opacity duration-300">
                                    <div className="max-w-[75%] bg-slate-50 text-slate-600 rounded-2xl rounded-tl-none p-4 border border-slate-200 shadow-sm opacity-95">
                                        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-100">
                                            <span className="font-semibold text-xs text-slate-400 tracking-wider uppercase">Agent's Thought & Action Log</span>
                                            <div className="flex space-x-1">
                                                <div className="w-1 h-1 bg-slate-300 rounded-full animate-pulse"></div>
                                                <div className="w-1 h-1 bg-slate-300 rounded-full animate-pulse" style={{ animationDelay: '150ms' }}></div>
                                                <div className="w-1 h-1 bg-slate-300 rounded-full animate-pulse" style={{ animationDelay: '300ms' }}></div>
                                            </div>
                                        </div>
                                        <div className="space-y-2 max-h-60 overflow-y-auto pr-2 custom-scrollbar">
                                            {agentLogs.map((log) => (
                                                <div
                                                    key={log.id}
                                                    className={`text-[12px] leading-relaxed p-2 rounded border ${log.type === 'thought'
                                                        ? 'italic bg-white/50 border-slate-100 text-slate-500'
                                                        : 'font-mono bg-slate-100 border-slate-200 text-slate-700'
                                                        }`}
                                                >
                                                    {log.content}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div ref={bottomRef} className="h-1" />
                        </div>

                        {/* Input */}
                        <div className="p-4 bg-white border-t border-slate-200">
                            <form onSubmit={handleSend} className="relative">
                                <input
                                    value={input}
                                    onChange={e => setInput(e.target.value)}
                                    placeholder={`Message ${activeSessionId === 'resident' ? 'Agent' : '...'}`}
                                    className="w-full pl-5 pr-14 py-4 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:bg-white transition-all shadow-inner"
                                />
                                <button
                                    type="submit"
                                    disabled={!input.trim() || sending}
                                    className="absolute right-3 top-3 p-2 bg-primary text-white rounded-lg shadow-md hover:bg-blue-600 disabled:opacity-50 disabled:shadow-none transition-all"
                                >
                                    <Send size={18} />
                                </button>
                            </form>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-300">
                        <MessageSquare size={64} className="mb-4 opacity-50" />
                        <p className="text-lg font-medium">Select a conversation</p>
                    </div>
                )}
            </div>
        </div>
    )
}

export default Chat
