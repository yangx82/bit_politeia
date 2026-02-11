import React, { useState, useEffect } from 'react';
import api from '../services/api';

const Contacts = () => {
    const [peers, setPeers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedPeer, setSelectedPeer] = useState(null);
    const [messageContent, setMessageContent] = useState("");
    const [sending, setSending] = useState(false);

    useEffect(() => {
        fetchPeers();
        // Poll for updates every 10 seconds
        const interval = setInterval(fetchPeers, 10000);
        return () => clearInterval(interval);
    }, []);

    const fetchPeers = async () => {
        try {
            const response = await api.get('/api/v1/p2p/peers');
            // Ensure endpoint exists on backend before enabling (returns 404 if not deployed)
            if (response.data) {
                setPeers(response.data);
                setError(null);
            }
        } catch (err) {
            console.error("Failed to fetch peers:", err);
            // Don't show error on first load to avoid flashing if backend is starting
            if (!peers.length) {
                setError("Failed to load contacts. Ensure backend is running.");
            }
        } finally {
            setLoading(false);
        }
    };

    const handleSendMessage = async () => {
        if (!selectedPeer || !messageContent.trim()) return;

        setSending(true);
        try {
            await api.post('/api/v1/p2p/send', {
                target_id: selectedPeer.node_id,
                content: messageContent
            });
            alert(`Message sent to ${selectedPeer.node_id.substring(0, 8)}...`);
            setMessageContent("");
            setSelectedPeer(null); // Close modal
        } catch (err) {
            console.error("Failed to send message:", err);
            alert("Failed to send message: " + (err.response?.data?.detail || err.message));
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-gray-50 text-gray-900 font-sans">
            {/* Header */}
            <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 shadow-sm z-10">
                <h2 className="text-xl font-semibold text-gray-800 tracking-tight">Network Contacts</h2>
                <div className="text-sm text-gray-500">
                    <span className="font-medium text-emerald-600">{peers.length}</span> Active Node{peers.length !== 1 && 's'}
                </div>
            </header>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
                {loading && !peers.length ? (
                    <div className="flex justify-center items-center h-64 text-gray-400">Loading network topology...</div>
                ) : error ? (
                    <div className="text-center p-8 bg-red-50 rounded-xl border border-red-100 text-red-600">
                        {error}
                    </div>
                ) : peers.length === 0 ? (
                    <div className="text-center p-12 bg-white rounded-xl border border-gray-100 shadow-sm">
                        <div className="text-4xl mb-4">🕸️</div>
                        <h3 className="text-lg font-medium text-gray-700">No Peers Discovered Yet</h3>
                        <p className="text-gray-500 mt-2">
                            Wait for other nodes to join the network or check your Bootstrap URL configuration.
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {peers.map((peer) => (
                            <div key={peer.node_id} className="bg-white rounded-xl border border-gray-100 shadow-md hover:shadow-lg transition-all duration-200 overflow-hidden flex flex-col">
                                <div className="p-5 flex-1">
                                    <div className="flex justify-between items-start mb-3">
                                        <div className="bg-blue-50 text-blue-700 text-xs font-mono px-2 py-1 rounded border border-blue-100">
                                            {peer.node_id.substring(0, 12)}...
                                        </div>
                                        <div className={`w-2.5 h-2.5 rounded-full ${peer.status === 'online' ? 'bg-emerald-500' : 'bg-gray-300'}`} title={peer.status}></div>
                                    </div>

                                    <div className="space-y-2 text-sm text-gray-600 mb-4">
                                        <div className="flex items-center gap-2">
                                            <span className="w-4 text-center">🌍</span>
                                            <span className="font-mono text-xs truncate max-w-[200px]" title={peer.endpoint}>
                                                {peer.endpoint || "Unknown Endpoint"}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="w-4 text-center">⏱️</span>
                                            <span className="text-xs">
                                                Last seen: {new Date(peer.last_seen).toLocaleTimeString()}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <button
                                    onClick={() => setSelectedPeer(peer)}
                                    className="w-full py-3 bg-gray-50 hover:bg-indigo-50 text-indigo-600 font-medium text-sm border-t border-gray-100 transition-colors flex items-center justify-center gap-2"
                                >
                                    <span>✉️</span> Send Message
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Message Modal */}
            {selectedPeer && (
                <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all scale-100">
                        <div className="px-6 py-4 bg-gray-50 border-b border-gray-100 flex justify-between items-center">
                            <h3 className="font-semibold text-gray-800">Message to Peer</h3>
                            <button onClick={() => setSelectedPeer(null)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
                        </div>

                        <div className="p-6">
                            <div className="mb-4 text-sm text-gray-500 bg-gray-50 p-3 rounded-lg border border-gray-100">
                                <span className="font-semibold text-gray-700">To:</span> {selectedPeer.node_id.substring(0, 16)}...
                            </div>

                            <textarea
                                className="w-full p-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-none min-h-[120px] text-gray-700"
                                placeholder="Type your message here..."
                                value={messageContent}
                                onChange={(e) => setMessageContent(e.target.value)}
                                autoFocus
                            />
                        </div>

                        <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-end gap-3">
                            <button
                                onClick={() => setSelectedPeer(null)}
                                className="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSendMessage}
                                disabled={sending || !messageContent.trim()}
                                className={`px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm font-medium transition-all ${(sending || !messageContent.trim()) ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-md hover:-translate-y-0.5'
                                    }`}
                            >
                                {sending ? 'Sending...' : 'Send'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Contacts;
