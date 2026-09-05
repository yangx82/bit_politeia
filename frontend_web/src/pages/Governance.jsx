import React, { useState, useEffect } from 'react';
import api, { getProposals, createProposal, getElections, castVote, getGroups, triggerEvolution } from '../services/api';
import { Scale, Clock, PenTool, Sparkles, Cpu, CheckCircle2, AlertCircle, Play, FileCode, Crown, XCircle, Filter, Microscope } from 'lucide-react';

const Governance = () => {
    const [activeTab, setActiveTab] = useState('proposals');
    const [proposals, setProposals] = useState([]);
    const [elections, setElections] = useState([]);
    const [groups, setGroups] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshTrigger, setRefreshTrigger] = useState(0);
    const [isTriggeringEvolution, setIsTriggeringEvolution] = useState(false);

    const [myNodeId, setMyNodeId] = useState(localStorage.getItem('bp_node_id') || '');
    const [archiveFilter, setArchiveFilter] = useState('all');

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
            const [props, elecs, grps, statusRes] = await Promise.all([
                getProposals(),
                getElections(),
                getGroups(),
                api.get('/api/v1/status').catch(() => null)
            ]);
            setProposals(props || []);
            setElections(elecs || []);
            setGroups(grps || []);
            if (statusRes?.data?.node_id) {
                setMyNodeId(statusRes.data.node_id);
                localStorage.setItem('bp_node_id', statusRes.data.node_id);
            }
        } catch (error) {
            console.error("Failed to fetch governance data", error);
        }
        setLoading(false);
    };

    const getRemainingTimeInfo = (endTimeStr) => {
        if (!endTimeStr) return null;
        const end = new Date(endTimeStr);
        const now = new Date();
        const diffMs = end - now;
        if (diffMs <= 0) return { text: '已到期结算中', urgent: false };
        const diffMins = Math.floor(diffMs / 60000);
        const hours = Math.floor(diffMins / 60);
        const mins = diffMins % 60;
        if (diffMins < 15) {
            return { text: `⚠️ 剩 ${diffMins} 分钟`, urgent: true };
        }
        if (hours > 0) {
            return { text: `⏱ 剩余 ${hours}h ${mins}m`, urgent: false };
        }
        return { text: `⏱ 剩余 ${mins} 分钟`, urgent: false };
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

    const handleTriggerEvolution = async () => {
        setIsTriggeringEvolution(true);
        try {
            const res = await triggerEvolution();
            alert(res.message || "Autonomous Evolution cycle initiated in background!");
            setTimeout(() => fetchData(), 3000);
        } catch (error) {
            alert("Failed to trigger evolution: " + error.message);
        } finally {
            setIsTriggeringEvolution(false);
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

    const aipProposals = proposals.filter(p => 
        p.scope === 'architecture_evolution' || (p.proposal_id && p.proposal_id.startsWith('AIP-'))
    );

    const renderAipCard = (aip) => {
        const meta = aip.metadata || {};
        const title = meta.title || aip.content || aip.proposal_id;
        const description = meta.description || aip.content;
        const status = aip.status || meta.status || 'draft';
        const targetFiles = meta.target_files || [];
        const sandbox = meta.sandbox_results || {};

        let statusBadge = "bg-amber-50 text-amber-700 border-amber-200";
        let statusLabel = "Draft 草案";
        if (status === 'verified_and_proposed' || status === 'sandbox_passed') {
            statusBadge = "bg-emerald-50 text-emerald-700 border-emerald-200";
            statusLabel = "Verified & Broadcasted 已验证并发布";
        } else if (status === 'passed' || status === 'merged') {
            statusBadge = "bg-blue-50 text-blue-700 border-blue-200";
            statusLabel = "Passed / Merged 已通过";
        } else if (status === 'stalled' || status === 'failed' || status === 'rejected') {
            statusBadge = "bg-rose-50 text-rose-700 border-rose-200";
            statusLabel = "Rejected / 归档";
        }

        return (
            <div key={aip.proposal_id} className="bg-surface p-6 rounded-xl border border-slate-200 shadow-sm mb-4">
                <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="bg-indigo-50 text-indigo-700 border border-indigo-200 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold">
                                {aip.proposal_id}
                            </span>
                            <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${statusBadge}`}>
                                ● {statusLabel}
                            </span>
                            <span className="text-xs text-slate-400 ml-auto">
                                {aip.timestamp ? new Date(aip.timestamp).toLocaleString() : ''}
                            </span>
                        </div>
                        <h3 className="text-lg font-semibold text-primary">{title}</h3>
                        <p className="text-sm text-slate-600 mt-2 whitespace-pre-line leading-relaxed">{description}</p>
                    </div>
                </div>

                {targetFiles.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-100 flex items-center gap-2 flex-wrap text-xs">
                        <span className="text-slate-400 flex items-center gap-1 font-medium"><FileCode size={13} /> 目标文件:</span>
                        {targetFiles.map(f => (
                            <span key={f} className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">
                                {f}
                            </span>
                        ))}
                    </div>
                )}

                {sandbox.timestamp && (
                    <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                        <span className={`flex items-center gap-1 font-medium ${sandbox.success ? 'text-emerald-600' : 'text-amber-600'}`}>
                            {sandbox.success ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                            沙盒验证: {sandbox.success ? '通过 (Exit 0)' : '需整改'}
                        </span>
                        <span className="text-slate-400">({new Date(sandbox.timestamp).toLocaleTimeString()})</span>
                    </div>
                )}
            </div>
        );
    };

    const renderGovernanceCard = (election) => {
        const proposal = proposals.find(p => p.proposal_id === election.proposal_id);
        const tally = election.tally || { approvals: 0, rejections: 0, total_votes: 0, winners: [] };
        
        // Match election type (backend uses 'core_node_election', 'proposal_vote', 'research_evaluation', 'architecture_evolution')
        const rawType = (election.election_type || '').toLowerCase();
        const electionContent = election.content || '';
        const proposalContent = proposal?.content || '';
        const proposalScope = (proposal?.scope || '').toLowerCase();
        const proposalId = (election.proposal_id || proposal?.proposal_id || '').toUpperCase();

        const isCoreNode = rawType.includes('core_node')
            || (election.candidates && election.candidates.length > 0)
            || electionContent.toLowerCase().includes('core node');

        const isAip = rawType.includes('architecture_evolution')
            || rawType.includes('aip')
            || proposalScope.includes('architecture')
            || proposalScope.includes('evolution')
            || proposalScope.includes('aip')
            || proposalId.startsWith('AIP-')
            || electionContent.toUpperCase().includes('AIP-')
            || proposalContent.toUpperCase().includes('AIP-')
            || electionContent.includes('架构')
            || electionContent.includes('进化')
            || proposalContent.includes('架构')
            || proposalContent.includes('进化')
            || (election.metadata && election.metadata.type === 'architecture_evolution')
            || (proposal?.metadata && proposal.metadata.type === 'architecture_evolution');

        const isResearch = !isAip && (
            rawType.includes('research')
            || proposalScope.includes('research')
            || Boolean(proposal?.pdf_hash)
            || electionContent.toLowerCase().includes('research')
            || proposalContent.toLowerCase().includes('research')
            || electionContent.includes('科研')
            || proposalContent.includes('科研')
            || electionContent.includes('论文')
            || proposalContent.includes('论文')
            || electionContent.includes('成果')
            || proposalContent.includes('成果')
            || electionContent.toLowerCase().includes('paper')
            || proposalContent.toLowerCase().includes('paper')
        );

        // Determine display title and type styling
        let title = election.content || "Community Governance Action";
        let typeBadgeClass = "bg-emerald-100 text-emerald-800 border-emerald-200";
        let typeLabel = "社区治理提案";
        let TypeIcon = Scale;

        if (isCoreNode) {
            title = election.content || "核心节点选举 (Core Node Selection)";
            typeBadgeClass = "bg-purple-100 text-purple-800 border-purple-200";
            typeLabel = "核心节点选举";
            TypeIcon = Crown;
        } else if (isAip) {
            title = proposal?.content || election.content || "AIP 架构自主进化提案";
            typeBadgeClass = "bg-indigo-100 text-indigo-800 border-indigo-200";
            typeLabel = "AIP 架构进化";
            TypeIcon = Cpu;
        } else if (isResearch) {
            title = election.content || "科研成果评定与激励";
            typeBadgeClass = "bg-cyan-100 text-cyan-800 border-cyan-200";
            typeLabel = "科研成果评估";
            TypeIcon = Microscope;
        } else if (proposal?.scope && proposal.scope !== 'group') {
            typeLabel = `提案 · ${proposal.scope}`;
        }

        const isElectionActive = election.is_active !== undefined ? election.is_active : election.status === 'active';
        const approvals = tally.approvals ?? 0;
        const total = tally.total_votes ?? 0;
        const percentage = total > 0 ? Math.round((approvals / total) * 100) : 0;
        const participation = Math.round((election.participation_rate || tally.participation_rate || 0) * 100);
        const isQuorumMet = tally.valid !== undefined ? tally.valid : (participation >= 80);

        // My Vote calculation
        let myVote = null;
        if (myNodeId && election.votes) {
            if (Array.isArray(election.votes)) {
                myVote = election.votes.find(v => v.voter_id === myNodeId);
            } else if (typeof election.votes === 'object') {
                const ballots = election.votes[myNodeId];
                if (Array.isArray(ballots) && ballots.length > 0) {
                    myVote = ballots[0];
                } else if (ballots && typeof ballots === 'object') {
                    myVote = ballots;
                }
            }
        }
        const isExcluded = Boolean(myNodeId && election.excluded_voters?.includes(myNodeId));
        const remainingInfo = isElectionActive ? getRemainingTimeInfo(election.end_time) : null;

        return (
            <div key={election.election_id} className="bg-surface p-6 rounded-xl border border-slate-200 shadow-sm mb-4">
                <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                            <span className={`${typeBadgeClass} border px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wide flex items-center gap-1.5`}>
                                <TypeIcon size={12} />
                                {typeLabel}
                            </span>
                            <span className="text-xs text-slate-400">
                                {new Date(election.start_time || election.timestamp).toLocaleString()}
                            </span>

                            {/* Top Right Status Badge inside header */}
                            <div className="ml-auto flex items-center gap-2">
                                {isElectionActive ? (
                                    <>
                                        {/* Countdown */}
                                        {remainingInfo && (
                                            <span className={`px-2.5 py-0.5 rounded-md text-xs font-mono border ${
                                                remainingInfo.urgent
                                                    ? 'bg-amber-100 text-amber-800 border-amber-300 animate-pulse font-bold'
                                                    : 'bg-slate-100 text-slate-600 border-slate-200'
                                            }`}>
                                                {remainingInfo.text}
                                            </span>
                                        )}
                                        {/* My Vote Status */}
                                        {isExcluded ? (
                                            <span className="px-2.5 py-0.5 rounded-md text-xs bg-slate-100 text-slate-500 font-medium border border-slate-200">
                                                🚫 发起人回避
                                            </span>
                                        ) : myVote ? (
                                            isCoreNode ? (
                                                <span className="px-2.5 py-0.5 rounded-md text-xs bg-purple-50 text-purple-700 font-medium border border-purple-200 flex items-center gap-1">
                                                    🗳 吾投: {myVote.candidate_id?.slice(0, 6)}
                                                </span>
                                            ) : myVote.approval ? (
                                                <span className="px-2.5 py-0.5 rounded-md text-xs bg-emerald-50 text-emerald-700 font-bold border border-emerald-200 flex items-center gap-1">
                                                    <CheckCircle2 size={12} /> 吾已赞成
                                                </span>
                                            ) : (
                                                <span className="px-2.5 py-0.5 rounded-md text-xs bg-rose-50 text-rose-700 font-bold border border-rose-200 flex items-center gap-1">
                                                    <XCircle size={12} /> 吾已反对
                                                </span>
                                            )
                                        ) : (
                                            <span className="px-2.5 py-0.5 rounded-md text-xs bg-amber-50 text-amber-700 font-medium border border-amber-200 flex items-center gap-1 animate-pulse">
                                                <Clock size={12} /> 待我表决
                                            </span>
                                        )}
                                    </>
                                ) : (
                                    /* Archive Outcome Badge: clear distinction between Early-Pass (green) & Fast-Reject (rose) */
                                    <>
                                        {!isQuorumMet ? (
                                            <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300 flex items-center gap-1.5 shadow-sm">
                                                <AlertCircle size={13} className="text-amber-600" />
                                                ⚠️ 流拍 · 投票率未达法定门槛 (&lt;80%)
                                            </span>
                                        ) : isCoreNode ? (
                                            tally.winners && tally.winners.length > 0 ? (
                                                <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-purple-100 text-purple-900 border border-purple-300 flex items-center gap-1.5 shadow-sm">
                                                    <Crown size={13} className="text-amber-500 fill-amber-400" />
                                                    👑 当选: {tally.winners.map(w => w.slice(0, 8)).join(', ')}
                                                </span>
                                            ) : (
                                                <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-300 flex items-center gap-1.5 shadow-sm">
                                                    <XCircle size={13} className="text-rose-500" />
                                                    ❌ 无人胜选 (得票未过半)
                                                </span>
                                            )
                                        ) : tally.early_passed ? (
                                            <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-400 flex items-center gap-1.5 shadow-sm">
                                                <span className="text-amber-500 text-sm leading-none font-black">⚡</span>
                                                快速通过 (Early Passed)
                                            </span>
                                        ) : tally.passed ? (
                                            <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-300 flex items-center gap-1.5 shadow-sm">
                                                <CheckCircle2 size={13} className="text-emerald-600" />
                                                决议通过 (Passed)
                                            </span>
                                        ) : tally.early_rejected ? (
                                            <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-rose-100 text-rose-800 border border-rose-400 flex items-center gap-1.5 shadow-sm">
                                                <span className="text-rose-600 text-sm leading-none font-black">⚡</span>
                                                提前否决 (Fast Rejected)
                                            </span>
                                        ) : (
                                            <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-300 flex items-center gap-1.5 shadow-sm">
                                                <XCircle size={13} className="text-rose-500" />
                                                决议否决 (Rejected)
                                            </span>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>

                        <h3 className="text-lg font-semibold text-primary line-clamp-2" title={title}>{title}</h3>

                        {isCoreNode && (
                            <div className="mt-3 flex flex-wrap gap-2">
                                {election.candidates?.map(c => {
                                    const votes = (tally.counts && tally.counts[c]) || 0;
                                    const isWinner = tally.winners?.includes(c);
                                    return (
                                        <span
                                            key={c}
                                            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-all ${
                                                isWinner
                                                    ? 'bg-purple-50 border-purple-300 text-purple-900 font-bold shadow-sm'
                                                    : 'bg-slate-50 border-slate-200 text-slate-600'
                                            }`}
                                        >
                                            {isWinner && <Crown size={12} className="text-amber-500 fill-amber-400" />}
                                            <span className="font-mono">{c.slice(0, 8)}</span>
                                            <span className={`px-1.5 py-0.2 rounded text-[11px] font-bold ${
                                                isWinner ? 'bg-purple-200 text-purple-900' : 'bg-slate-200 text-slate-700'
                                            }`}>
                                                {votes} 票
                                            </span>
                                            {isWinner && (
                                                <span className="text-[10px] bg-amber-100 text-amber-800 border border-amber-300 px-1 rounded font-bold">
                                                    当选
                                                </span>
                                            )}
                                        </span>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {!isCoreNode && (
                        <div className="text-right ml-6 min-w-[70px]">
                            <div className="text-2xl font-bold text-primary">{percentage}%</div>
                            <div className="text-xs text-slate-400 font-medium">支持率 (Approval)</div>
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-6 border-t border-slate-100 pt-4">
                    <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1.5">
                            {isCoreNode ? (
                                <div className="flex items-center gap-2">
                                    <span className="text-slate-600 font-medium">参投率: {participation}%</span>
                                    <span className={`text-[11px] font-medium ${isQuorumMet ? 'text-emerald-600' : 'text-amber-600'}`}>
                                        {isQuorumMet ? '✅ 法定有效 (≥80%)' : '⚠️ 未达法定门槛 (<80%)'}
                                    </span>
                                </div>
                            ) : (
                                <>
                                    <div className="flex items-center gap-3">
                                        <span className="text-emerald-600 font-semibold flex items-center gap-1">
                                            <CheckCircle2 size={12} /> 赞成: {approvals}
                                        </span>
                                        <span className="text-rose-500 font-semibold flex items-center gap-1">
                                            <XCircle size={12} /> 反对: {tally.rejections ?? 0}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-slate-500">参投率: {participation}%</span>
                                        <span className={`text-[11px] font-medium ${isQuorumMet ? 'text-emerald-600' : 'text-amber-600'}`}>
                                            {isQuorumMet ? '✅ 法定有效 (≥80%)' : '⚠️ 未达法定门槛 (<80%)'}
                                        </span>
                                    </div>
                                </>
                            )}
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden flex">
                            {isCoreNode ? (
                                <div style={{ width: `${participation}%` }} className="bg-purple-500 h-full transition-all duration-500" />
                            ) : (
                                <>
                                    <div style={{ width: `${percentage}%` }} className="bg-emerald-500 h-full transition-all duration-500" />
                                    <div style={{ width: `${100 - percentage}%` }} className="bg-rose-400 h-full transition-all duration-500" />
                                </>
                            )}
                        </div>
                    </div>

                    {isElectionActive && (
                        <div className="flex gap-2">
                            {isCoreNode ? (
                                election.candidates?.map(candidate => (
                                    <button
                                        key={candidate}
                                        onClick={() => handleVote(election.election_id, true, "", candidate)}
                                        className="px-3 py-1.5 bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 text-xs font-medium transition-colors"
                                    >
                                        投给 {candidate.slice(0, 4)}
                                    </button>
                                ))
                            ) : (
                                <>
                                    <button
                                        onClick={() => handleVote(election.election_id, true)}
                                        className="px-4 py-2 bg-emerald-50 text-emerald-700 rounded-lg hover:bg-emerald-100 text-sm font-medium transition-colors flex items-center gap-1"
                                    >
                                        <CheckCircle2 size={14} /> 赞成
                                    </button>
                                    <button
                                        onClick={() => handleVote(election.election_id, false)}
                                        className="px-4 py-2 bg-rose-50 text-rose-700 rounded-lg hover:bg-rose-100 text-sm font-medium transition-colors flex items-center gap-1"
                                    >
                                        <XCircle size={14} /> 反对
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
                    <h1 className="text-2xl font-bold text-primary mb-2">Governance & Evolution</h1>
                    <p className="text-secondary">Participate in community decision making and autonomous architecture evolution</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={handleTriggerEvolution}
                        disabled={isTriggeringEvolution}
                        className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-2 text-sm font-medium disabled:opacity-50"
                    >
                        <Sparkles size={16} />
                        {isTriggeringEvolution ? 'Evolving...' : 'Trigger Evolution'}
                    </button>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary-dark transition-colors flex items-center gap-2 text-sm font-medium"
                    >
                        <PenTool size={16} />
                        New Proposal
                    </button>
                </div>
            </div>

            {/* Tabs & Archive Filter Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
                <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit">
                    <button
                        onClick={() => setActiveTab('proposals')}
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'proposals' ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-primary'}`}
                    >
                        Active Governance
                    </button>
                    <button
                        onClick={() => setActiveTab('aips')}
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-1.5 ${activeTab === 'aips' ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-primary'}`}
                    >
                        <Cpu size={15} />
                        Autonomous Evolution (AIP)
                        {aipProposals.length > 0 && (
                            <span className="bg-indigo-100 text-indigo-700 text-[11px] font-bold px-1.5 py-0.2 rounded-full ml-1">
                                {aipProposals.length}
                            </span>
                        )}
                    </button>
                    <button
                        onClick={() => setActiveTab('history')}
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'history' ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-primary'}`}
                    >
                        Archive
                    </button>
                </div>

                {activeTab === 'history' && (
                    <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg text-xs font-medium">
                        <span className="text-slate-400 px-2 flex items-center gap-1"><Filter size={12} /> 筛选:</span>
                        {[
                            { id: 'all', label: '全部' },
                            { id: 'passed', label: '✅ 通过' },
                            { id: 'rejected', label: '❌ 否决/流拍' },
                            { id: 'aip', label: '⚡ AIP 进化' },
                            { id: 'elections', label: '👑 核心选举' },
                        ].map(f => (
                            <button
                                key={f.id}
                                onClick={() => setArchiveFilter(f.id)}
                                className={`px-2.5 py-1 rounded-md transition-all ${
                                    archiveFilter === f.id
                                        ? 'bg-white text-primary font-bold shadow-sm'
                                        : 'text-slate-500 hover:text-slate-800'
                                }`}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Content */}
            <div className="space-y-4">
                {loading ? (
                    <div className="text-center py-12 text-slate-400">Loading governance data...</div>
                ) : activeTab === 'aips' ? (
                    aipProposals.length > 0 ? (
                        aipProposals.map(renderAipCard)
                    ) : (
                        <div className="text-center py-12 bg-slate-50 rounded-xl border border-dashed border-slate-300">
                            <Cpu className="mx-auto text-slate-300 mb-3" size={48} />
                            <p className="text-slate-500 font-medium">No autonomous evolution proposals yet</p>
                            <p className="text-sm text-slate-400 mt-1">Click "Trigger Evolution" to start a proactive exploration loop!</p>
                        </div>
                    )
                ) : (() => {
                    const filteredElections = elections.filter(e => {
                        const isElectionActive = e.is_active !== undefined ? e.is_active : e.status === 'active';
                        if (activeTab === 'proposals') {
                            return isElectionActive;
                        }
                        // Archive tab
                        if (isElectionActive) return false;
                        if (archiveFilter === 'all') return true;
                        const rawType = (e.election_type || '').toLowerCase();
                        const isCoreNode = rawType.includes('core_node');
                        if (archiveFilter === 'elections') return isCoreNode;
                        if (archiveFilter === 'aip') {
                            const p = proposals.find(pr => pr.proposal_id === e.proposal_id);
                            const pScope = (p?.scope || '').toLowerCase();
                            const pId = (e.proposal_id || p?.proposal_id || '').toUpperCase();
                            const cText = (e.content || '') + (p?.content || '');
                            return rawType.includes('architecture_evolution')
                                || rawType.includes('aip')
                                || pScope.includes('architecture')
                                || pScope.includes('evolution')
                                || pScope.includes('aip')
                                || pId.startsWith('AIP-')
                                || cText.toUpperCase().includes('AIP-')
                                || cText.includes('架构')
                                || cText.includes('进化');
                        }
                        const t = e.tally || {};
                        const participation = Math.round((e.participation_rate || t.participation_rate || 0) * 100);
                        const isQuorumMet = t.valid !== undefined ? t.valid : (participation >= 80);
                        
                        if (archiveFilter === 'passed') {
                            if (!isQuorumMet) return false;
                            return isCoreNode ? (t.winners && t.winners.length > 0) : !!t.passed;
                        }
                        if (archiveFilter === 'rejected') {
                            if (!isQuorumMet) return true;
                            return isCoreNode ? (!t.winners || t.winners.length === 0) : !t.passed;
                        }
                        return true;
                    });
                    return filteredElections.length > 0 ? (
                        filteredElections.map(renderGovernanceCard)
                    ) : (
                        <div className="text-center py-12 bg-slate-50 rounded-xl border border-dashed border-slate-300">
                            <Scale className="mx-auto text-slate-300 mb-3" size={48} />
                            <p className="text-slate-500 font-medium">
                                {activeTab === 'proposals'
                                    ? '暂无进行中的治理提案 (No Active Proposals)'
                                    : archiveFilter !== 'all'
                                    ? '未找到符合筛选条件的归档提案'
                                    : '暂无归档提案 (No Archived Proposals)'}
                            </p>
                            <p className="text-sm text-slate-400">
                                {activeTab === 'proposals'
                                    ? '处于投票阶段的提案将在此处展示并可进行投票。'
                                    : '已完成或已否决的提案将统一归档于此。'}
                            </p>
                        </div>
                    );
                })()}
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
