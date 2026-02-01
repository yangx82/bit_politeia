import React, { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import { Send, Search, Calendar, X } from 'lucide-react'

const Chat = () => {
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [sending, setSending] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [dateFrom, setDateFrom] = useState('')
    const [dateTo, setDateTo] = useState('')
    const [showFilters, setShowFilters] = useState(false)
    const bottomRef = useRef(null)
    const prevMessagesCount = useRef(0)

    const fetchHistory = async (isSearching = false) => {
        try {
            let url = '/api/v1/history'
            const params = new URLSearchParams()

            if (searchQuery) params.append('q', searchQuery)
            if (dateFrom) params.append('date_from', dateFrom)
            if (dateTo) params.append('date_to', dateTo)

            if (params.toString()) {
                url = `/api/v1/history/search?${params.toString()}`
            }

            const res = await api.get(url)
            setMessages(res.data)
        } catch (err) {
            console.error("Failed to fetch history:", err)
        }
    }

    const handleSend = async (e) => {
        e.preventDefault()
        if (!input.trim() || sending) return

        const content = input
        setInput('')
        setSending(true)

        // Optimistic Update
        const tempMsg = {
            id: Date.now().toString(),
            sender: 'user',
            content: content,
            timestamp: new Date().toISOString()
        }
        setMessages(prev => [...prev, tempMsg])

        try {
            await api.post('/api/v1/chat/instruction', { content })
            await fetchHistory()
        } catch (err) {
            console.error("Failed to send:", err)
        } finally {
            setSending(false)
        }
    }

    const clearFilters = () => {
        setSearchQuery('')
        setDateFrom('')
        setDateTo('')
        setShowFilters(false)
    }

    // Effect for polling (only when not searching)
    useEffect(() => {
        fetchHistory()
        const isFiltering = searchQuery || dateFrom || dateTo
        if (!isFiltering) {
            const interval = setInterval(fetchHistory, 3000)
            return () => clearInterval(interval)
        }
    }, [searchQuery, dateFrom, dateTo])

    useEffect(() => {
        if (messages.length > prevMessagesCount.current) {
            bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
        }
        prevMessagesCount.current = messages.length
    }, [messages])

    return (
        <div className="flex flex-col h-full max-h-[calc(100vh-3rem)]">
            {/* Header */}
            <div className="mb-4 flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-bold text-slate-800">Agent Chat</h2>
                    <p className="text-sm text-slate-500">Private Secure Channel</p>
                </div>
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className={`p-2 rounded-lg transition-colors ${showFilters ? 'bg-primary text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                    <Search size={18} />
                </button>
            </div>

            {/* Filter Bar */}
            {showFilters && (
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 mb-4 space-y-3">
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
                        <input
                            placeholder="Search keywords..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-primary/20"
                        />
                    </div>
                    <div className="flex gap-2">
                        <div className="flex-1">
                            <label className="text-[10px] uppercase font-bold text-slate-400 mb-1 block">From</label>
                            <input
                                type="date"
                                value={dateFrom}
                                onChange={(e) => setDateFrom(e.target.value)}
                                className="w-full p-2 text-xs rounded-lg border border-slate-200"
                            />
                        </div>
                        <div className="flex-1">
                            <label className="text-[10px] uppercase font-bold text-slate-400 mb-1 block">To</label>
                            <input
                                type="date"
                                value={dateTo}
                                onChange={(e) => setDateTo(e.target.value)}
                                className="w-full p-2 text-xs rounded-lg border border-slate-200"
                            />
                        </div>
                    </div>
                    {(searchQuery || dateFrom || dateTo) && (
                        <button
                            onClick={clearFilters}
                            className="text-xs text-red-500 font-medium flex items-center gap-1 hover:underline"
                        >
                            <X size={12} /> Clear Filters
                        </button>
                    )}
                </div>
            )}

            {/* Message List */}
            <div className="flex-1 overflow-y-auto space-y-4 pr-2 mb-4 scrollbar-thin">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-slate-400 italic">
                        <p>No messages found</p>
                    </div>
                ) : (
                    messages.map((msg) => {
                        const isUser = msg.sender === 'user'
                        return (
                            <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                                <div className={`max-w-[70%] rounded-2xl p-4 ${isUser ? 'bg-primary text-white rounded-br-none' : 'bg-white border border-slate-200 rounded-bl-none'
                                    }`}>
                                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                                    <span className={`text-[10px] mt-1 block ${isUser ? 'text-blue-100' : 'text-slate-400'}`}>
                                        {new Date(msg.timestamp).toLocaleString()}
                                    </span>
                                </div>
                            </div>
                        )
                    })
                )}
                <div ref={bottomRef} />
            </div>

            {/* Input Area */}
            <form onSubmit={handleSend} className="relative">
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Instruct your agent..."
                    className="w-full p-4 pr-12 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-primary/20 shadow-sm"
                />
                <button
                    type="submit"
                    disabled={!input.trim()}
                    className="absolute right-3 top-3 p-1.5 text-primary hover:bg-slate-50 rounded-lg transition-colors disabled:opacity-50"
                >
                    <Send size={20} />
                </button>
            </form>
        </div>
    )
}

export default Chat
