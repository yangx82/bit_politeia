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

    const renderProposalCard = (proposal) => {
        const election = elections.find(e => e.proposal_id === proposal.proposal_id);
        const tally = election?.tally || { approvals: 0, rejections: 0, total_votes: 0 };
        const percentage = tally.total_votes > 0
            ? Math.round((tally.approvals / tally.total_votes) * 100)
            : 0;

        return (
            <div key={proposal.proposal_id} className="bg-surface p-6 rounded-xl border border-slate-200 shadow-sm mb-4">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <span className="bg-primary/10 text-primary px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wide">
                                {proposal.scope}
                            </span>
                            <span className="text-xs text-slate-500">
                                {new Date(proposal.timestamp).toLocaleString()}
                            </span>
                        </div>
                        <h3 className="text-lg font-semibold text-primary">{proposal.content}</h3>
                    </div>
                    <div className="text-right">
                        <div className="text-2xl font-bold text-primary">{percentage}%</div>
                        <div className="text-xs text-slate-500">Approval</div>
                    </div>
                </div>

                <div className="flex items-center gap-6 border-t border-slate-100 pt-4">
                    <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1">
                            <span className="text-green-600 font-medium">Yes: {tally.approvals}</span>
                            <span className="text-red-500 font-medium">No: {tally.rejections}</span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden flex">
                            <div style={{ width: `${percentage}%` }} className="bg-green-500 h-full" />
                            <div style={{ width: `${100 - percentage}%` }} className="bg-red-400 h-full" />
                        </div>
                    </div>

                    {election && election.status === 'active' && (
                        <div className="flex gap-2">
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
                    Active Proposals
                </button>
                <button
                    onClick={() => setActiveTab('history')}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'history' ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-primary'}`}
                >
                    Past Votes
                </button>
            </div>

            {/* Content */}
            <div className="space-y-4">
                {loading ? (
                    <div className="text-center py-12 text-slate-400">Loading governance data...</div>
                ) : (
                    proposals.length > 0 ? (
                        proposals.map(renderProposalCard)
                    ) : (
                        <div className="text-center py-12 bg-slate-50 rounded-xl border border-dashed border-slate-300">
                            <Scale className="mx-auto text-slate-300 mb-3" size={48} />
                            <p className="text-slate-500 font-medium">No active proposals found</p>
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
