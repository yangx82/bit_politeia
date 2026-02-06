import React, { useState, useEffect } from 'react';
import api from '../services/api';

const Archive = () => {
    const [chain, setChain] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedBlock, setSelectedBlock] = useState(null);

    useEffect(() => {
        fetchChain();
    }, []);

    const fetchChain = async () => {
        try {
            const response = await api.get('/api/v1/archive/chain');
            if (response.data) {
                // Sort by index descending (latest first)
                setChain(response.data.reverse());
                setError(null);
            }
        } catch (err) {
            console.error("Failed to fetch archive chain:", err);
            setError("Failed to load blockchain archive.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-gray-50 text-gray-900 font-sans">
            {/* Header */}
            <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 shadow-sm z-10">
                <h2 className="text-xl font-semibold text-gray-800 tracking-tight">Local Blockchain Archive</h2>
                <div className="text-sm text-gray-500">
                    <span className="font-medium text-emerald-600">{chain.length}</span> Blocks
                </div>
            </header>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
                {loading ? (
                    <div className="flex justify-center items-center h-64 text-gray-400">Loading blockchain...</div>
                ) : error ? (
                    <div className="text-center p-8 bg-red-50 rounded-xl border border-red-100 text-red-600">
                        {error}
                    </div>
                ) : chain.length === 0 ? (
                    <div className="text-center p-12 bg-white rounded-xl border border-gray-100">
                        <div className="text-4xl mb-4">📦</div>
                        <h3 className="text-lg font-medium text-gray-700">Empty Chain</h3>
                        <p className="text-gray-500 mt-2">No blocks recorded yet.</p>
                    </div>
                ) : (
                    <div className="max-w-4xl mx-auto space-y-4">
                        {chain.map((block) => (
                            <div
                                key={block.hash}
                                onClick={() => setSelectedBlock(block)}
                                className="bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-all cursor-pointer group"
                            >
                                <div className="p-5 flex items-center gap-4">
                                    <div className="flex flex-col items-center justify-center p-3 bg-gray-50 rounded-lg min-w-[60px]">
                                        <span className="text-xs text-gray-400 font-medium">BLOCK</span>
                                        <span className="text-xl font-bold text-gray-700">{block.index}</span>
                                    </div>

                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="font-mono text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded border border-gray-100 truncate max-w-[200px]" title={block.hash}>
                                                {block.hash}
                                            </span>
                                            <span className="text-xs text-gray-400 whitespace-nowrap">
                                                • {new Date(block.timestamp * 1000).toLocaleString()}
                                            </span>
                                        </div>

                                        <div className="text-sm text-gray-600 line-clamp-1 group-hover:text-indigo-600 transition-colors">
                                            {block.index === 0 ? "Genesis Block" : `Data Hash: ${JSON.stringify(block.data).substring(0, 100)}...`}
                                        </div>
                                    </div>

                                    <div className="text-gray-300 group-hover:text-indigo-400">
                                        👉
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Block Detail Modal */}
            {selectedBlock && (
                <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
                        <div className="px-6 py-4 bg-gray-50 border-b border-gray-100 flex justify-between items-center">
                            <h3 className="font-semibold text-gray-800">Block Details #{selectedBlock.index}</h3>
                            <button onClick={() => setSelectedBlock(null)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
                        </div>

                        <div className="p-6 overflow-y-auto flex-1 font-mono text-sm">
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1">HASH</label>
                                    <div className="bg-gray-50 p-2 rounded border border-gray-100 break-all text-gray-700">{selectedBlock.hash}</div>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-medium text-gray-400 mb-1">PREVIOUS HASH</label>
                                        <div className="bg-gray-50 p-2 rounded border border-gray-100 break-all text-gray-600 text-xs">{selectedBlock.prev_hash}</div>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-gray-400 mb-1">TIMESTAMP</label>
                                        <div className="bg-gray-50 p-2 rounded border border-gray-100 text-gray-700">
                                            {new Date(selectedBlock.timestamp * 1000).toLocaleString()}
                                        </div>
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1">DATA PAYLOAD</label>
                                    <div className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto">
                                        <pre>{JSON.stringify(selectedBlock.data, null, 2)}</pre>
                                    </div>
                                </div>

                                {selectedBlock.signature && (
                                    <div>
                                        <label className="block text-xs font-medium text-gray-400 mb-1">SIGNATURE</label>
                                        <div className="bg-amber-50 text-amber-900 p-2 rounded border border-amber-100 text-xs break-all">
                                            {selectedBlock.signature}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-end">
                            <button
                                onClick={() => setSelectedBlock(null)}
                                className="px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg shadow-sm transition-colors"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Archive;
