import React, { useState, useEffect } from 'react';
import { getProposals, createProposal, getElections, castVote, getGroups } from '../services/api';
import { Scale, Clock, PenTool } from 'lucide-react';

const Governance = () => {
    const [activeTab, setActiveTab] = useState('proposals');
    const [proposals, setProposals] = useState([]);
    const [elections, setElections] = useState([]);
    const [groups, setGroups] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshTrigger, setRefreshTrigger] = useState(0);

    // Form State
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newProposalContent, setNewProposalContent] = useState('');
    const [selectedGroup, setSelectedGroup] = useState('');
    const [duration, setDuration] = useState(60);

    useEffect(() => {
        fetchData();
    }, [refreshTrigger]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [props, elecs, grps] = await Promise.all([
                getProposals(),
                getElections(),
                getGroups()
            ]);
            setProposals(props);
            setElections(elecs);
            setGroups(grps);
        } catch (error) {
            console.error("Failed to fetch governance data", error);
        }
        setLoading(false);
    };

    const handleCreateProposal = async () => {
        if (!newProposalContent || !selectedGroup) return;
        try {
            const res = await createProposal(selectedGroup, newProposalContent, duration);
            setShowCreateModal(false);
            setNewProposalContent('');
            alert(res.message || "Suggestion forwarded to your agent!");
            // No immediate refresh since agent needs time to think
        } catch (error) {
            alert("Failed to send suggestion: " + error.message);
        }
    };

    const handleVote = async (electionId, approval) => {
        const reason = prompt(approval ? "Reason for approval (optional):" : "Reason for rejection (required):");
        if (approval === false && !reason) {
            alert("Reason is required for rejection.");
            return;
        }
        try {
            const res = await castVote(electionId, approval, reason || "No reason provided");
            alert(res.message || "Suggestion forwarded to your agent!");
            // No immediate refresh since agent needs time to think
        } catch (error) {
            alert("Failed to send suggestion: " + error.message);
        }
    };

    const renderGovernanceCard = (election) => {
        const proposal = proposals.find(p => p.proposal_id === election.proposal_id);
        const tally = election.tally || { approvals: 0, rejections: 0, total_votes: 0, winners: [] };
        
        // Match election type (backend uses 'core_node_election' and 'proposal_vote')
        const rawType = (election.election_type || '').toLowerCase();
        const isCoreNode = rawType.includes('core_node');
        const isProposal = rawType.includes('proposal');

        // Determine display title and content
        let title = election.content || "Community Governance Action";
        let badgeColor = "bg-slate-100 text-slate-600";
        let typeLabel = "Governance";

        if (isCoreNode) {
            title = "Core Node Selection";
            badgeColor = "bg-purple-100 text-purple-700";
            typeLabel = "Core Node";
        } else if (isProposal || proposal) {
            // Use proposal content if available, then election content, then default
            title = proposal?.content || election.content || "Governance Proposal Vote";
            badgeColor = "bg-primary/10 text-primary";
            typeLabel = proposal?.scope || "Proposal";
        }

        // Fix: Ensure 0 is treated as 0, not falsey
        const approvals = tally.approvals ?? 0;
        const total = tally.total_votes ?? 0;
        const percentage = total > 0 ? Math.round((approvals / total) * 100) : 0;
            
        const participation = Math.round((election.participation_rate || tally.participation_rate || 0) * 100);

        return (
            <div key={election.election_id} className="bg-surface p-6 rounded-xl border border-slate-200 shadow-sm mb-4">
                <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                            <span className={`${badgeColor} px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wide`}>
                                {typeLabel}
                            </span>
                            <span className="text-xs text-slate-500">
                                {new Date(election.start_time || election.timestamp).toLocaleString()}
                            </span>
                            <span className={`text-xs ml-auto ${election.status === 'active' ? 'text-green-500' : 'text-slate-400'}`}>
                                ● {election.status === 'active' ? 'Active' : 'Finished'}
                            </span>
                        </div>
                        <h3 className="text-lg font-semibold text-primary line-clamp-2" title={title}>{title}</h3>
                        {isCoreNode && (
                            <div className="mt-2 flex flex-wrap gap-1">
                                {election.candidates?.map(c => {
                                    const votes = (tally.counts && tally.counts[c]) || 0;
                                    return (
                                        <span key={c} className="flex items-center gap-1.5 text-[10px] bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded text-slate-500">
                                            {c.slice(0, 8)}: <span className="font-bold text-purple-600">{votes}</span>
                                        </span>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                    {!isCoreNode && (
                        <div className="text-right ml-4 min-w-[60px]">
                            <div className="text-2xl font-bold text-primary">{percentage}%</div>
                            <div className="text-xs text-slate-500">Approval</div>
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-6 border-t border-slate-100 pt-4">
                    <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1">
                            {isCoreNode ? (
                                <span className="text-slate-600 font-medium font-mono uppercase tracking-tight">Participation: {participation}%</span>
                            ) : (
                                <>
                                    <span className="text-green-600 font-medium">Yes: {approvals}</span>
                                    <span className="text-red-500 font-medium">No: {tally.rejections ?? 0}</span>
                                </>
                            )}
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden flex">
                            {isCoreNode ? (
                                <div style={{ width: `${participation}%` }} className="bg-purple-500 h-full transition-all duration-500" />
                            ) : (
                                <>
                                    <div style={{ width: `${percentage}%` }} className="bg-green-500 h-full transition-all duration-500" />
                                    <div style={{ width: `${100 - percentage}%` }} className="bg-red-400 h-full transition-all duration-500" />
                                </>
                            )}
                        </div>
                    </div>

                    {election.status === 'active' && (
                        <div className="flex gap-2">
                             {isCoreNode ? (
                                 election.candidates?.map(candidate => (
                                    <button
                                        key={candidate}
                                        onClick={() => handleVote(election.election_id, true, "", candidate)}
                                        className="px-3 py-1.5 bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 text-xs font-medium transition-colors"
                                    >
                                        Vote {candidate.slice(0, 4)}
                                    </button>
                                 ))
                             ) : (
                                <>
                                    <button
                                        onClick={() => handleVote(election.election_id, true)}
                                        className="px-4 py-2 bg-green-50 text-green-700 rounded-lg hover:bg-green-100 text-sm font-medium transition-colors"
                                    >
                                        Vote Yes
                                    </button>
                                    <button
                                        onClick={() => handleVote(election.election_id, false)}
                                        className="px-4 py-2 bg-red-50 text-red-700 rounded-lg hover:bg-red-100 text-sm font-medium transition-colors"
                                    >
                                        Vote No
                                    </button>
                                </>
                             )}
                        </div>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="max-w-4xl mx-auto">
            {/* Header */}
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-primary mb-2">Governance</h1>
                    <p className="text-secondary">Participate in community decision making</p>
                </div>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary-dark transition-colors flex items-center gap-2"
                >
                    <PenTool size={18} />
                    New Proposal
                </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit mb-6">
                <button
                    onClick={() => setActiveTab('proposals')}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'proposals' ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-primary'}`}
                >
                    Active Governance
                </button>
                <button
                    onClick={() => setActiveTab('history')}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'history' ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-primary'}`}
                >
                    Archive
                </button>
            </div>

            {/* Content */}
            <div className="space-y-4">
                {loading ? (
                    <div className="text-center py-12 text-slate-400">Loading governance data...</div>
                ) : (
                    elections.length > 0 ? (
                        elections
                            .filter(e => activeTab === 'proposals' ? e.status === 'active' : e.status !== 'active')
                            .map(renderGovernanceCard)
                    ) : (
                        <div className="text-center py-12 bg-slate-50 rounded-xl border border-dashed border-slate-300">
                            <Scale className="mx-auto text-slate-300 mb-3" size={48} />
                            <p className="text-slate-500 font-medium">No governance events found</p>
                            <p className="text-sm text-slate-400">Be the first to propose a change!</p>
                        </div>
                    )
                )}
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 animate-in fade-in zoom-in duration-200">
                        <h2 className="text-xl font-bold text-primary mb-4">Create Proposal</h2>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Target Group</label>
                                <select
                                    value={selectedGroup}
                                    onChange={(e) => setSelectedGroup(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                                >
                                    <option value="">Select a group...</option>
                                    {groups.map(g => (
                                        <option key={g.group_id} value={g.group_id}>
                                            {g.name || g.group_id} (Level {g.level})
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Proposal Content</label>
                                <textarea
                                    value={newProposalContent}
                                    onChange={(e) => setNewProposalContent(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none h-32 resize-none"
                                    placeholder="Describe your proposal..."
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Voting Duration (Minutes)</label>
                                <input
                                    type="number"
                                    value={duration}
                                    onChange={(e) => setDuration(parseInt(e.target.value))}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                                    min="10"
                                />
                            </div>
                        </div>

                        <div className="flex justify-end gap-3 mt-6">
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleCreateProposal}
                                disabled={!newProposalContent || !selectedGroup}
                                className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                Submit Proposal
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Governance;
