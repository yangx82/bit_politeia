import React, { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import { Send } from 'lucide-react'

const Chat = () => {
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [sending, setSending] = useState(false)
    const bottomRef = useRef(null)

    const fetchHistory = async () => {
        try {
            const res = await api.get('/api/v1/history')
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
            await fetchHistory() // Refresh full history to get agent response
        } catch (err) {
            console.error("Failed to send:", err)
        } finally {
            setSending(false)
        }
    }

    // Poll for new messages every 2s
    useEffect(() => {
        fetchHistory()
        const interval = setInterval(fetchHistory, 2000)
        return () => clearInterval(interval)
    }, [])

    // Auto-scroll
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    return (
        <div className="flex flex-col h-full max-h-[calc(100vh-3rem)]">
            {/* Header */}
            <div className="mb-4">
                <h2 className="text-xl font-bold text-slate-800">Agent Chat</h2>
                <p className="text-sm text-slate-500">Private Secure Channel</p>
            </div>

            {/* Message List */}
            <div className="flex-1 overflow-y-auto space-y-4 pr-2 mb-4 scrollbar-thin">
                {messages.map((msg) => {
                    const isUser = msg.sender === 'user'
                    return (
                        <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[70%] rounded-2xl p-4 ${isUser ? 'bg-primary text-white rounded-br-none' : 'bg-white border border-slate-200 rounded-bl-none'
                                }`}>
                                <p className="text-sm">{msg.content}</p>
                                <span className={`text-[10px] mt-1 block ${isUser ? 'text-blue-100' : 'text-slate-400'}`}>
                                    {new Date(msg.timestamp).toLocaleTimeString()}
                                </span>
                            </div>
                        </div>
                    )
                })}
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
