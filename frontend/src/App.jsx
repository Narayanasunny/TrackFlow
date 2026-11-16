import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from "react-markdown";
import {
  Activity, AlertTriangle, ArrowRight, Bell, CheckCircle2, ChevronDown,
  Clock3, GitCompareArrows, LayoutDashboard, Layers3, Menu, RefreshCw,
  Route, Sparkles, TrainFront, Zap, Search, Filter, Bot, Send, MessageSquare,
  Copy, Trash2, WandSparkles, ShieldCheck, Gauge, X, Command,
} from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip
} from 'recharts';

const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const arr = value => Array.isArray(value) ? value : [];
const val = (object, keys, fallback = null) => {
  for (const key of keys) {
    if (object?.[key] !== undefined && object[key] !== null) return object[key];
  }
  return fallback;
};

// React cannot render plain JavaScript objects as text. Convert API values safely.
function displayText(value, fallback = '—') {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(item => displayText(item, '')).filter(Boolean).join(' · ') || fallback;
  }
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([key, item]) => {
        const label = key.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
        return `${label}: ${displayText(item, '—')}`;
      })
      .join(' · ') || fallback;
  }
  return fallback;
}
const trainId = (train, index = 0) => val(train, ['train_id', 'id'], `Train ${index + 1}`);
const departure = train => Number(val(train, ['scheduled_departure', 'departure'], 0)) || 0;
const arrival = train => Number(val(train, ['simulated_arrival', 'arrival', 'target_arrival'], 0)) || 0;
const arrivalDelay = train => Number(val(train, ['delay_minutes', 'delay'], 0)) || 0;
const addedDelay = train => Number(val(train, ['added_departure_delay_minutes', 'added_departure_delay'], 0)) || 0;

function formatConflictType(type) {
  const labels = {
    headway_violation: 'Headway violation',
    overlapping_occupancy: 'Track occupancy overlap',
    single_track_occupancy: 'Single-track occupancy',
    opposing_movements: 'Opposing train movements',
    route_contention: 'Route contention'
  };
  return labels[type] || String(type || 'Track conflict')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}
function minute(value) {
  return value === undefined || value === null || value === '' ? '—' : `${value} min`;
}
function conflictDetails(conflict) {
  const type = val(conflict, ['conflict_type', 'type'], '');
  if (type === 'headway_violation' ||
      (conflict.actual_separation_minutes != null && conflict.required_headway_minutes != null)) {
    return `Actual separation: ${minute(conflict.actual_separation_minutes)} · Required: ${minute(conflict.required_headway_minutes)}`;
  }
  if (conflict.overlap_start != null || conflict.overlap_end != null) {
    return `Overlap window: ${minute(conflict.overlap_start)}–${minute(conflict.overlap_end)}`;
  }
  return displayText(val(conflict, ['message', 'description'], 'No additional measurements were provided by the API.'));
}

function createTrackFlowSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `trackflow-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function App() {
  const [base, setBase] = useState(null);
  const [opt, setOpt] = useState(null);
  const [tab, setTab] = useState('overview');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState('');
  const [mobile, setMobile] = useState(false);
  const [trainSearch, setTrainSearch] = useState('');
  const [conflictSearch, setConflictSearch] = useState('');
  const [conflictFilter, setConflictFilter] = useState('all');

  // Agentic AI chat workspace
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [chatSessionId, setChatSessionId] = useState(() => {
    try {
      const saved = sessionStorage.getItem('trackflow_chat_session_id');
      if (saved) return saved;
      const created = createTrackFlowSessionId();
      sessionStorage.setItem('trackflow_chat_session_id', created);
      return created;
    } catch {
      return createTrackFlowSessionId();
    }
  });
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState('');
  const chatEndRef = useRef(null);
  const chatInputRef = useRef(null);

  const [trafficAnalysis, setTrafficAnalysis] = useState(null);

  const [explainability, setExplainability] = useState(null);

  
  const [selectedSection, setSelectedSection] = useState(null);

  const [trackSections, setTrackSections] = useState([]);
  const [trackSectionsError, setTrackSectionsError] = useState('');


  
  const sectionConflictCounts = (trafficAnalysis?.most_affected_sections || []).reduce(
    (counts, item) => {
      counts[item.section_id] = item.conflict_count;
      return counts;
    },
    {}
  );

  const maxSectionConflicts = Math.max(
    1,
    ...Object.values(sectionConflictCounts)
  );

  function getSectionClass(sectionId) {
    const count = sectionConflictCounts[sectionId] || 0;
    const hotspotClass =
      count >= maxSectionConflicts * 0.7 && count > 0
        ? 'conflict-hotspot-high'
        : count > 0
          ? 'conflict-hotspot'
          : '';

    const routeClass = selectedRouteSections.has(sectionId)
      ? 'route-selected'
      : '';

    return `${hotspotClass} ${routeClass}`.trim();
  }


  const [trafficBusy, setTrafficBusy] = useState(false);
  const [trafficError, setTrafficError] = useState('');

  const [disruptionTrain, setDisruptionTrain] = useState('T101');

  
  const selectedRouteTrain = (base?.trains || []).find(
    train => train.train_id === disruptionTrain
  );

  const selectedRouteSections = new Set(
    (selectedRouteTrain?.movements || []).map(
      movement => movement.section_id
    )
  );


  const [disruptionDelay, setDisruptionDelay] = useState(10);
  const [disruptionResult, setDisruptionResult] = useState(null);
  const [disruptionMode, setDisruptionMode] = useState('train-delay');
  const [closureSection, setClosureSection] = useState('SEC_DE');
  const [closureStart, setClosureStart] = useState(30);
  const [closureEnd, setClosureEnd] = useState(50);
  const [closureResult, setClosureResult] = useState(null);

  const baselineTrains = arr(val(base, ['trains', 'simulated_trains', 'results'], []));
  const optimizedTrains = arr(val(opt, ['optimized_trains', 'trains'], []));
  const trains = optimizedTrains.length ? optimizedTrains : baselineTrains;
  const conflicts = arr(val(base, ['conflicts', 'detected_conflicts', 'conflict_details'], []));
  const conflictCount = Number(val(base, ['conflict_count', 'total_conflicts'], conflicts.length));
  const optCount = Number(val(opt, ['optimized_conflicts', 'conflict_count'], 0));
  const addedTotal = Number(val(opt, ['total_added_departure_delay_minutes'],
    optimizedTrains.reduce((sum, train) => sum + addedDelay(train), 0)));
  const isOptimized = Boolean(opt);

  async function load(runOptimization = false) {
    setBusy(true);
    setError('');
    try {
      const baselineResponse = await fetch(`${API}/api/simulation/baseline`);
      if (!baselineResponse.ok) throw new Error(`Baseline API returned ${baselineResponse.status}`);
      const baselineBody = await baselineResponse.json();
      setBase(baselineBody);

      if (runOptimization) {
        const optimizationResponse = await fetch(`${API}/api/optimization`);
        const optimizationBody = await optimizationResponse.json();
        if (!optimizationResponse.ok) {
          throw new Error(optimizationBody.detail || `Optimization API returned ${optimizationResponse.status}`);
        }
        setOpt(optimizationBody);
      }
      setUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    } catch (err) {
      setError(`Cannot reach ${API}. Start the FastAPI server and retry. ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  
async function loadTrafficAnalysis() {
  setTrafficBusy(true);
  setTrafficError('');

  try {
    const response = await fetch(
      `${API}/api/agents/traffic-analysis`
    );

    if (!response.ok) {
      throw new Error(
        `Traffic analysis failed (HTTP ${response.status})`
      );
    }

    const data = await response.json();
    setTrafficAnalysis(data);
  } catch (err) {
    setTrafficError(
      err.message || 'Unable to load traffic analysis.'
    );
  } finally {
    setTrafficBusy(false);
  }
}


// ADD THIS NEW FUNCTION HERE
async function loadExplainability() {
  try {
    const response = await fetch(
      `${API}/api/agents/explainability`
    );

    if (!response.ok) {
      throw new Error(
        `Explainability API failed (HTTP ${response.status})`
      );
    }

    const data = await response.json();
    setExplainability(data);
  } catch (err) {
    console.error('Explainability error:', err);
  }
}


async function loadTrackSections() {
  setTrackSectionsError('');

  try {
    const response = await fetch(`${API}/api/track-sections`);

    if (!response.ok) {
      throw new Error('Failed to load track sections.');
    }

    const data = await response.json();
    setTrackSections(data.track_sections || []);
  } catch (err) {
    setTrackSectionsError(
      err.message || 'Unable to load track sections.'
    );
  }
}



  async function runDisruption() {
  setBusy(true);
  setError('');
  setDisruptionResult(null);
  setClosureResult(null);

  try {
    const response = await fetch(`${API}/api/simulation/disruption`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        train_id: disruptionTrain,
        delay_minutes: Number(disruptionDelay),
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.detail || 'Failed to run disruption simulation.'
      );
    }

    setDisruptionResult(data);
  } catch (err) {
    setError(err.message || 'Unable to run disruption simulation.');
  } finally {
    setBusy(false);
  }
}


  async function runTrackClosure() {
    setBusy(true);
    setError('');
    setClosureResult(null);
    setDisruptionResult(null);

    try {
      const response = await fetch(`${API}/api/simulation/track-closure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section_id: closureSection,
          start_minute: Number(closureStart),
          end_minute: Number(closureEnd),
        }),
      });

      const data = await response.json();
      if (data.session_id && data.session_id !== chatSessionId) {
        setChatSessionId(data.session_id);
        try { sessionStorage.setItem('trackflow_chat_session_id', data.session_id); } catch {}
      }
      if (!response.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail || data);
        throw new Error(detail || `Track closure request failed (HTTP ${response.status}).`);
      }

      setClosureResult(data);
    } catch (err) {
      setError(err.message || 'Unable to run track-closure simulation.');
    } finally {
      setBusy(false);
    }
  }

  async function sendAgentMessage(messageOverride) {
    const message = String(messageOverride ?? chatInput).trim();
    if (!message || chatBusy) return;

    const userMessage = {
      id: `${Date.now()}-user`,
      role: 'user',
      content: message,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setChatMessages(previous => [...previous, userMessage]);
    setChatInput('');
    setChatError('');
    setChatBusy(true);

    try {
      const response = await fetch(`${API}/api/agent/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_request: message, session_id: chatSessionId }),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : displayText(data.detail || data, 'Agent request failed.');
        throw new Error(detail || `Agent request failed (HTTP ${response.status}).`);
      }

      const optimization = data.optimization || {};
      const traffic = data.traffic_analysis || {};
      const validation = optimization.validation || {};
      const toolsUsed = [];
      if (Object.keys(traffic).length) toolsUsed.push('Traffic analysis');
      if (Object.keys(optimization).length) toolsUsed.push('OR-Tools rescheduling');
      if (Object.keys(data.explanation || {}).length) toolsUsed.push('Explainability');

      const assistantMessage = {
        id: `${Date.now()}-assistant`,
        role: 'assistant',
        content: data.final_response || 'The agent returned results without a text explanation.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        meta: {
          toolsUsed,
          traffic,
          optimization,
          explanation: data.explanation || {},
          disruptions: data.disruptions || [],
          error: data.error || null,
          validationPassed: validation.passed ?? validation.is_valid ?? null,
        },
      };
      setChatMessages(previous => [...previous, assistantMessage]);
    } catch (err) {
      setChatError(err.message || 'Unable to reach the TrackFlow agent.');
      setChatMessages(previous => [...previous, {
        id: `${Date.now()}-error`,
        role: 'assistant',
        content: `I couldn't complete that request. ${err.message || 'Please check the backend and try again.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        failed: true,
      }]);
    } finally {
      setChatBusy(false);
    }
  }

  function clearAgentChat() {
    if (chatBusy) return;
    setChatMessages([]);
    setChatError('');
    setChatInput('');
    const nextSessionId = createTrackFlowSessionId();
    setChatSessionId(nextSessionId);
    try { sessionStorage.setItem('trackflow_chat_session_id', nextSessionId); } catch {}
  }

  async function copyChatText(text) {
    try {
      await navigator.clipboard.writeText(String(text || ''));
    } catch (err) {
      console.error('Unable to copy chat response:', err);
    }
  }

  useEffect(() => {
    load();
    loadTrackSections();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [chatMessages, chatBusy]);

  const nav = [
    ['overview', 'Command center', LayoutDashboard],
    ['trains', 'Train operations', TrainFront],
    ['conflicts', 'Conflict intelligence', GitCompareArrows],
    ['disruption', 'Disruption simulator', Zap],
    ['assistant', 'AI operations assistant', Bot]
  ];
  const chartData = baselineTrains.map((train, index) => ({
    train: trainId(train, index),
    baseline: arrivalDelay(train),
    added: addedDelay(optimizedTrains[index] || {})
  }));
  const filteredTrains = useMemo(() => trains.filter((train, index) =>
    trainId(train, index).toLowerCase().includes(trainSearch.toLowerCase())), [trains, trainSearch]);
  const filteredConflicts = useMemo(() => conflicts.filter(conflict => {
    const text = [
      val(conflict, ['train_1', 'train_a', 'train1'], ''),
      val(conflict, ['train_2', 'train_b', 'train2'], ''),
      val(conflict, ['section_id', 'section'], ''),
      val(conflict, ['message'], ''),
      formatConflictType(val(conflict, ['conflict_type', 'type'], ''))
    ].join(' ').toLowerCase();
    const type = val(conflict, ['conflict_type', 'type'], '');
    return text.includes(conflictSearch.toLowerCase()) &&
      (conflictFilter === 'all' || type === conflictFilter);
  }), [conflicts, conflictSearch, conflictFilter]);

  return (
    <div className="shell">
      <TrackFlowChatStyles />
      <aside className={`sidebar ${mobile ? 'show' : ''}`}>
        <div className="brand">
          <div className="brand-icon"><Route size={21} /></div>
          <div><b>trackflow<span>.</span></b><small>TRAFFIC INTELLIGENCE</small></div>
        </div>
        <p className="side-label">WORKSPACE</p>
        {nav.map(([key, label, Icon]) => (
          <button key={key} onClick={() => { setTab(key); setMobile(false); }}
            className={`nav ${tab === key ? 'active' : ''}`}>
            <Icon size={17} /> {label}
            {key === 'conflicts' && <em>{conflictCount}</em>}
          </button>
        ))}
        <div className="push" />
        <div className="online-card">
          <div><i /> SIMULATION ENVIRONMENT</div>
          <strong>{error ? 'API disconnected' : 'Synthetic network'}</strong>
          <p>5 stations · 8 track sections · 10 sample trains</p>
          <div className="mini-track">{Array.from({ length: 14 }, (_, i) => <span key={i} />)}</div>
        </div>
        <div className="profile"><div>TF</div><span><b>TrackFlow AI</b><small>Decision support prototype</small></span><ChevronDown size={14} /></div>
      </aside>

      <main>
        <header>
          <div className="crumb">
            <button className="hamb" onClick={() => setMobile(!mobile)}><Menu size={18} /></button>
            Workspace <span>/</span> <b>{nav.find(item => item[0] === tab)?.[1]}</b>
          </div>
          <div className="top-actions">
            <div className="api-state"><i /> API <b>{error ? 'Disconnected' : base ? 'Connected' : 'Connecting'}</b></div>
            <button className="square" onClick={() => load(isOptimized)} title="Refresh" disabled={busy}>
              <RefreshCw size={16} className={busy ? 'spin' : ''} />
            </button>
            <button className="square" title="Notifications"><Bell size={16} /></button>
            <div className="user">TF</div>
          </div>
        </header>

        <div className="page">
          <section className="hero">
            <div>
              <div className="kicker"><Sparkles size={14} /> RAILWAY OPERATIONS · AI DECISION SUPPORT</div>
              <h1>{tab === 'overview' ? <>See the network.<br /><span>Move smarter.</span></> :
                tab === 'trains' ? <>Train <span>operations.</span></> :
                tab === 'conflicts' ? <>Conflict <span>intelligence.</span></> :
                tab === 'assistant' ? <>Your rail network.<br /><span>One AI copilot.</span></> :
                <>Disruption <span>simulator.</span></>}</h1>
              <p>{tab === 'disruption' ? 'Model a train delay or temporary track closure, then inspect the optimizer response and validation results.' : tab === 'assistant' ? 'Ask operational questions in plain language. TrackFlow coordinates analysis, optimization and configured validation tools.' : 'Explore the synthetic rail network, inspect detected conflicts, and compare a proposed schedule from the optimizer.'}</p>
            </div>
            <div className="hero-buttons">
              <button className="secondary" onClick={() => load(false)} disabled={busy}><RefreshCw size={15} /> Refresh data</button>
              <button className="primary" onClick={() => load(true)} disabled={busy}>
                <Zap size={15} /> {busy ? 'Running…' : isOptimized ? 'Re-run optimization' : 'Run optimization'} <ArrowRight size={15} />
              </button>
            </div>
          </section>

          {error && <div className="error"><AlertTriangle size={18} /><div><b>API connection needs attention</b><p>{error}</p></div><button onClick={() => load(false)}>Retry</button></div>}

        <div className="status">

            <div className="status-icon">
                <Activity size={17} />
        </div>

        <div className="status-copy">
            <b>
                {isOptimized
                    ? 'Optimization result loaded'
                    : 'Baseline simulation'}
            </b>

            <span>
            {isOptimized
                ? opt?.validation?.passed
                ? 'The optimized schedule passed the configured model checks.'
                : 'The schedule needs review. Check the validation results.'
                : 'Baseline data is loaded from the FastAPI backend.'}
            </span>
        </div>

        <div
            className={`pill ${
            isOptimized
                ? opt?.validation?.passed
                ? 'green'
                : 'amber'
                : 'amber'
            }`}
        >
            <i />
            {isOptimized
            ? opt?.validation?.passed
                ? 'VALIDATION PASSED'
                : 'VALIDATION NEEDS REVIEW'
            : 'BASELINE'}
        </div>

            <small>
                {updated ? `Updated ${updated}` : 'Waiting for API'}
            </small>
        </div>

          {tab === 'assistant' && (
            <section className="tf-chat-layout">
              <div className="tf-chat-main panel">
                <div className="tf-chat-topbar">
                  <div className="tf-chat-agent-mark"><Bot size={22} /></div>
                  <div className="tf-chat-agent-title">
                    <b>TrackFlow Operations Copilot</b>
                    <span><i /> Agent online · Groq + LangGraph</span>
                  </div>
                  <button className="tf-icon-button" onClick={clearAgentChat} disabled={chatBusy || !chatMessages.length} title="Clear conversation"><Trash2 size={16} /></button>
                </div>

                <div className="tf-chat-messages" aria-live="polite">
                  {!chatMessages.length && (
                    <div className="tf-chat-welcome">
                      <div className="tf-welcome-orb"><WandSparkles size={25} /></div>
                      <div className="tf-chat-eyebrow">INTELLIGENT RAIL OPERATIONS</div>
                      <h2>Good day, operator.</h2>
                      <p>Tell me what is happening on the network. I'll select the relevant TrackFlow tools and return the results from your simulation and optimization modules.</p>
                      <div className="tf-prompt-grid">
                        {[
                          ['Analyze network congestion', 'Analyze current railway traffic and identify the most affected trains and track sections.'],
                          ['Resolve a track closure', 'Close track section SEC_DE from minute 30 to minute 50. Reschedule affected trains, validate the schedule, and explain the changes.'],
                          ['Explain schedule decisions', 'Explain why the optimizer adds departure delays and summarize the schedule changes.'],
                          ['Inspect conflict hotspots', 'Analyze the current network and summarize conflict types, affected trains, and affected sections.'],
                        ].map(([title, prompt], index) => (
                          <button className="tf-prompt-card" key={title} onClick={() => sendAgentMessage(prompt)} disabled={chatBusy}>
                            <span className="tf-prompt-icon">{index === 0 ? <Activity size={17} /> : index === 1 ? <Route size={17} /> : index === 2 ? <GitCompareArrows size={17} /> : <Gauge size={17} />}</span>
                            <b>{title}</b><small>{prompt}</small><ArrowRight size={15} className="tf-prompt-arrow" />
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {chatMessages.map(message => (
                    <article className={`tf-message ${message.role === 'user' ? 'tf-message-user' : 'tf-message-ai'}`} key={message.id}>
                      <div className="tf-message-avatar">{message.role === 'user' ? 'YOU' : <Bot size={17} />}</div>
                      <div className="tf-message-body">
                        <div className="tf-message-meta"><b>{message.role === 'user' ? 'You' : 'TrackFlow AI'}</b><time>{message.timestamp}</time></div>
                        <div className={`tf-message-bubble ${message.failed ? 'tf-message-failed' : ''}`}>
                          {message.role === 'assistant' ? <ReactMarkdown>{message.content}</ReactMarkdown> : <p>{message.content}</p>}
                        </div>
                        {message.meta && (
                          <div className="tf-result-panel">
                            <div className="tf-result-heading"><span><ShieldCheck size={15} /> EXECUTION SUMMARY</span><button onClick={() => copyChatText(message.content)} title="Copy response"><Copy size={14} /> Copy</button></div>
                            {message.meta.toolsUsed?.length > 0 ? <div className="tf-tool-chips">{message.meta.toolsUsed.map(toolName => <span key={toolName}><CheckCircle2 size={12} /> {toolName}</span>)}</div> : <p className="tf-result-muted">No structured tool output was included in this response.</p>}
                            {message.meta.optimization && Object.keys(message.meta.optimization).length > 0 && (
                              <div className="tf-result-stats">
                                <div><small>SOLVER</small><b>{message.meta.optimization.status || '—'}</b></div>
                                <div><small>TRAINS</small><b>{message.meta.optimization.optimized_train_count ?? message.meta.optimization.optimized_trains?.length ?? '—'}</b></div>
                                <div><small>ADDED DELAY</small><b>{message.meta.optimization.total_added_departure_delay_minutes ?? '—'} min</b></div>
                                <div><small>VALIDATION</small><b className={message.meta.validationPassed === true ? 'tf-good' : message.meta.validationPassed === false ? 'tf-warn' : ''}>{message.meta.validationPassed === true ? 'PASSED' : message.meta.validationPassed === false ? 'REVIEW' : '—'}</b></div>
                              </div>
                            )}
                            {message.meta.traffic?.network_summary && (
                              <div className="tf-result-stats tf-traffic-stats">
                                <div><small>TRAINS</small><b>{message.meta.traffic.network_summary.train_count ?? '—'}</b></div>
                                <div><small>CONFLICTS</small><b>{message.meta.traffic.network_summary.baseline_conflict_count ?? '—'}</b></div>
                                <div><small>STATIONS</small><b>{message.meta.traffic.network_summary.station_count ?? '—'}</b></div>
                                <div><small>SECTIONS</small><b>{message.meta.traffic.network_summary.track_section_count ?? '—'}</b></div>
                              </div>
                            )}
                            {message.meta.disruptions?.length > 0 && <p className="tf-result-muted">Disruptions: {displayText(message.meta.disruptions)}</p>}
                            {message.meta.error && <p className="tf-result-error">{message.meta.error}</p>}
                            <p className="tf-safety-note">Synthetic decision-support output only. Configured validation is not real-world railway safety certification.</p>
                          </div>
                        )}
                      </div>
                    </article>
                  ))}
                  {chatBusy && <div className="tf-typing"><span className="tf-message-avatar"><Bot size={17} /></span><div><b>TrackFlow is working</b><p><i /><i /><i /> Selecting tools and processing results…</p></div></div>}
                  <div ref={chatEndRef} />
                </div>

                {chatError && <div className="tf-chat-error"><AlertTriangle size={15} /> {chatError} <button onClick={() => setChatError('')}><X size={14} /></button></div>}
                <form className="tf-chat-composer" onSubmit={event => { event.preventDefault(); sendAgentMessage(); }}>
                  <textarea ref={chatInputRef} value={chatInput} onChange={event => setChatInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendAgentMessage(); } }} placeholder="Ask TrackFlow to analyze traffic, simulate a disruption, or explain a schedule…" rows={2} maxLength={2000} disabled={chatBusy} />
                  <div className="tf-composer-footer"><span><Command size={12} /> Enter to send · Shift + Enter for new line · {chatInput.length}/2000</span><button type="submit" disabled={chatBusy || chatInput.trim().length < 3}><Send size={15} /> {chatBusy ? 'Working…' : 'Send request'}</button></div>
                </form>
              </div>

              <aside className="tf-chat-sidebar">
                <div className="panel tf-capability-panel"><div className="tf-side-kicker">AVAILABLE CAPABILITIES</div><h3>One agent. Multiple tools.</h3>
                  <div className="tf-capability"><span><Activity size={16} /></span><div><b>Traffic analysis</b><small>Find conflict hotspots</small></div><i /></div>
                  <div className="tf-capability"><span><Route size={16} /></span><div><b>Dynamic rescheduling</b><small>OR-Tools optimization</small></div><i /></div>
                  <div className="tf-capability"><span><ShieldCheck size={16} /></span><div><b>Schedule validation</b><small>Configured model checks</small></div><i /></div>
                  <div className="tf-capability"><span><GitCompareArrows size={16} /></span><div><b>Explainability</b><small>Explain schedule changes</small></div><i /></div>
                </div>
                <div className="panel tf-tips-panel"><div className="tf-side-kicker">REQUEST EXAMPLES</div><h3>Be specific for best results</h3><ul><li>Include the exact track section ID.</li><li>Provide closure start and end minutes.</li><li>Ask for validation and an explanation.</li><li>Never treat simulated output as live dispatch advice.</li></ul></div>
                <div className="tf-chat-status"><span><i /> API endpoint</span><b>POST /api/agent/chat</b><small>{API}</small></div>
              </aside>
            </section>
          )}

          {tab === 'overview' && (
            <>
              <section className="stats">
                <Stat icon={TrainFront} label="Trains in simulation" value={baselineTrains.length || '—'} sub="From baseline API" color="blue" />
                <Stat icon={GitCompareArrows} label="Detected conflicts" value={base ? (isOptimized ? `${conflictCount} → ${optCount}` : conflictCount) : '—'} sub={isOptimized ? 'Baseline → optimized model' : 'From baseline run'} color="orange" />
                <Stat icon={Clock3} label="Added departure delay" value={isOptimized ? `${addedTotal} min` : '—'} sub="Optimizer intervention total" color="violet" />
                <Stat icon={Layers3} label="Network footprint" value={base ? `${val(base, ['station_count'], 5)} / ${val(base, ['track_section_count', 'section_count'], 8)}` : '—'} sub="Stations / track sections" color="mint" />
              </section>

              <section className="grid">
                <div className="panel">
                  <Heading eyebrow="NETWORK TOPOLOGY" title="Your rail network" tag="SYNTHETIC DATA" />
                  
                  <div className="map-controls" style={{ marginBottom: 12 }}>
                    <label htmlFor="route-train">Highlight train route</label>
                    <select
                      id="route-train"
                      value={disruptionTrain}
                      onChange={event => setDisruptionTrain(event.target.value)}
                    >
                      {(base?.trains || []).map(train => (
                        <option key={train.train_id} value={train.train_id}>
                          {train.train_id} — {train.train_name || train.train_id}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="railmap">
                    <div className="mapgrid" />
                    <svg viewBox="0 0 640 240" preserveAspectRatio="none">
                      
                      
                      
                      
                      
                      <path
                        className={`mainroute ${getSectionClass('SEC_AB')} ${selectedSection === 'SEC_AB' ? 'section-selected' : ''}`}
                        d="M62 120 L178 64"
                        onClick={() => setSelectedSection('SEC_AB')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`mainroute ${getSectionClass('SEC_BC')} ${selectedSection === 'SEC_BC' ? 'section-selected' : ''}`}
                        d="M178 64 L300 120"
                        onClick={() => setSelectedSection('SEC_BC')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`mainroute ${getSectionClass('SEC_CD')} ${selectedSection === 'SEC_CD' ? 'section-selected' : ''}`}
                        d="M300 120 L428 64"
                        onClick={() => setSelectedSection('SEC_CD')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`mainroute ${getSectionClass('SEC_DE')} ${selectedSection === 'SEC_DE' ? 'section-selected' : ''}`}
                        d="M428 64 L568 120"
                        onClick={() => setSelectedSection('SEC_DE')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`branch ${getSectionClass('SEC_BD')} ${selectedSection === 'SEC_BD' ? 'section-selected' : ''}`}
                        d="M178 64 L300 190 L428 64"
                        onClick={() => setSelectedSection('SEC_BD')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`secondaryroute ${getSectionClass('SEC_CE')} ${selectedSection === 'SEC_CE' ? 'section-selected' : ''}`}
                        d="M300 120 L428 190 L568 120"
                        onClick={() => setSelectedSection('SEC_CE')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`mutedroute ${getSectionClass('SEC_AC')} ${selectedSection === 'SEC_AC' ? 'section-selected' : ''}`}
                        d="M62 120 L300 120"
                        onClick={() => setSelectedSection('SEC_AC')}
                        style={{ cursor: 'pointer' }}
                      />

                      <path
                        className={`critical ${getSectionClass('SEC_BD_LOOP')} ${selectedSection === 'SEC_BD_LOOP' ? 'section-selected' : ''}`}
                        d="M178 64 L428 64"
                        onClick={() => setSelectedSection('SEC_BD_LOOP')}
                        style={{ cursor: 'pointer' }}
                      />



                      {[[62,120],[178,64],[300,120],[428,64],[568,120],[178,190],[300,190],[428,190]].map(([x,y],i) =>
                        <g key={i}><circle cx={x} cy={y} r="13" className="halo" /><circle cx={x} cy={y} r="6" className="node" /><circle cx={x} cy={y} r="2" className="core" /></g>)}
                    </svg>
                    {['STA','STB','STC','STD','STE'].map((station, index) => <div key={station} className={`station ${['a','b','c','d','e'][index]}`}><b>{station}</b><small>{index === 0 || index === 4 ? 'Terminal' : 'Junction'}</small></div>)}
                    <div className="legend"><span><i /> Primary route</span><span><i /> Critical segment</span></div>
                  </div>
                  <div className="mapfoot"><div><small>MODEL SCOPE</small><b>5 stations · 8 sections · 10 trains</b></div><button onClick={() => setTab('trains')}>Explore train movements <ArrowRight size={14} /></button></div>
                </div>

                
                <div className="panel" style={{ marginTop: 16 }}>
                  <Heading
                    eyebrow="TRACK INSPECTOR"
                    title="Track section details"
                    tag={selectedSection || 'SELECT A TRACK'}
                  />

                  {!selectedSection ? (
                    <p className="description">
                      Click a track line on the railway map to inspect its
                      section details and detected conflicts.
                    </p>
                  ) : (
                    <>
                      {(() => {
                        const sectionDetails = trackSections.find(
                          section => section.section_id === selectedSection
                        );

                        const sectionConflicts = (
                          trafficAnalysis?.conflicts || []
                        ).filter(
                          conflict => conflict.section_id === selectedSection
                        );

                        const trainIds = [
                          ...new Set(
                            sectionConflicts
                              .flatMap(conflict => [
                                conflict.train_id,
                                conflict.train_a,
                                conflict.train_b,
                                conflict.train_1,
                                conflict.train_2,
                                ...(Array.isArray(conflict.train_ids)
                                  ? conflict.train_ids
                                  : [])
                              ])
                              .filter(id => typeof id === 'string')
                          )
                        ];

                        return (
                          <>
                            <div className="stats-grid" style={{ marginTop: 16 }}>
                              <div className="stat">
                                <span>Selected section</span>
                                <strong>{selectedSection}</strong>
                              </div>

                              <div className="stat">
                                <span>Detected conflicts</span>
                                <strong>
                                  {sectionConflictCounts[selectedSection] ?? 0}
                                </strong>
                              </div>
                            </div>

                            <Heading
                              eyebrow="SECTION INFORMATION"
                              title="Track properties"
                            />

                            {trackSectionsError ? (
                              <p className="description">{trackSectionsError}</p>
                            ) : sectionDetails ? (
                              <div className="stats-grid" style={{ marginTop: 16 }}>
                                <div className="stat">
                                  <span>From station</span>
                                  <strong>{sectionDetails.from_station}</strong>
                                </div>

                                <div className="stat">
                                  <span>To station</span>
                                  <strong>{sectionDetails.to_station}</strong>
                                </div>

                                <div className="stat">
                                  <span>Travel time</span>
                                  <strong>
                                    {sectionDetails.travel_time_minutes} min
                                  </strong>
                                </div>

                                <div className="stat">
                                  <span>Minimum headway</span>
                                  <strong>
                                    {sectionDetails.minimum_headway_minutes} min
                                  </strong>
                                </div>

                                <div className="stat">
                                  <span>Track type</span>
                                  <strong>{sectionDetails.track_type}</strong>
                                </div>

                                <div className="stat">
                                  <span>Availability</span>
                                  <strong>
                                    {sectionDetails.available
                                      ? 'Available'
                                      : 'Unavailable'}
                                  </strong>
                                </div>

                                <div className="stat">
                                  <span>Crossing allowed</span>
                                  <strong>
                                    {sectionDetails.crossing_allowed ? 'Yes' : 'No'}
                                  </strong>
                                </div>
                              </div>
                            ) : (
                              <p className="description">
                                Track section details are loading or unavailable.
                              </p>
                            )}

                            <Heading
                              eyebrow="CONFLICT INTELLIGENCE"
                              title="Conflict records"
                            />

                            {sectionConflicts.length > 0 ? (
                              <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
                                {sectionConflicts.map((conflict, index) => {
                                  const conflictType =
                                    conflict.conflict_type ||
                                    conflict.type ||
                                    'Unspecified conflict';

                                  const conflictTrainIds = [
                                    ...new Set(
                                      [
                                        conflict.train_id,
                                        conflict.train_a,
                                        conflict.train_b,
                                        conflict.train_1,
                                        conflict.train_2,
                                        ...(Array.isArray(conflict.train_ids)
                                          ? conflict.train_ids
                                          : [])
                                      ].filter(id => typeof id === 'string')
                                    )
                                  ];

                                  return (
                                    <div
                                      className="explain"
                                      key={`${selectedSection}-${index}`}
                                    >
                                      <span>
                                        <AlertTriangle size={16} />
                                      </span>

                                      <div style={{ minWidth: 0 }}>
                                        <b>{conflictType}</b>

                                        <p>
                                          <strong>Section:</strong>{' '}
                                          {conflict.section_id || selectedSection}
                                        </p>

                                        <p>
                                          <strong>Trains:</strong>{' '}
                                          {conflictTrainIds.length
                                            ? conflictTrainIds.join(', ')
                                            : 'Not specified'}
                                        </p>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <Empty
                                title="No matching conflicts"
                                text="No conflict records were returned for this section."
                              />
                            )}

                            <button
                              className="wide"
                              onClick={() => setSelectedSection(null)}
                            >
                              Clear selection
                            </button>
                          </>
                        );
                      })()}

                      <div className="disclaimer" style={{ marginTop: 12 }}>
                        Conflict information comes from synthetic data and the
                        project's configured conflict detector.
                      </div>
                    </>
                  )}
                </div>


                <div className="panel">
                  <Heading eyebrow="MODEL SUMMARY" title="What needs attention?" tag="INSIGHTS" />
                  <div className="insight"><div className="warn-icon"><AlertTriangle size={18} /></div><div>
                    <b>{isOptimized ? 'Optimization result available' : 'Baseline conflicts require review'}</b>
                    <p>{isOptimized ? `The current optimizer reports ${optCount} conflicts under its configured model checks, with ${addedTotal} total minutes of added departure delay.` : base ? `${conflictCount} conflict records were returned by the baseline API. Inspect the conflict register for the specific trains, sections, and measurements.` : 'Connect to the backend to load real simulation results.'}</p>
                  </div></div>
                  <Explain number="01" title="Occupancy overlap">Two movements overlap in time on a track section according to the simplified model.</Explain>
                  <Explain number="02" title="Headway protection">Same-direction movements may require a minimum time gap.</Explain>
                  <Explain number="03" title="Delay trade-off">The optimizer shifts departures; added departure delay is not the same as arrival delay.</Explain>
                  <div className="disclaimer">ⓘ Synthetic decision-support prototype — not a certified railway signalling system.</div>
                </div>
              </section>

              <section className="grid lower">
                <div className="panel">
                  <Heading eyebrow="SCHEDULE IMPACT" title="Delay by train" tag="MINUTES" />
                  {chartData.length ? <div className="chart"><ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 8, right: 5, left: -20, bottom: 0 }} barGap={4}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#26364a" />
                      <XAxis dataKey="train" tick={{ fill: '#91a2b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: '#91a2b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ background: '#111e30', border: '1px solid #2b3d54', borderRadius: 10, color: '#edf4ff' }} />
                      <Bar dataKey="baseline" name="Baseline arrival delay" fill="#7188ff" radius={[4,4,0,0]} />
                      <Bar dataKey="added" name="Added departure delay" fill="#31cbb8" radius={[4,4,0,0]} />
                    </BarChart>
                  </ResponsiveContainer></div> : <Empty title="No chart data yet" text="Load the baseline API to populate this chart." />}
                  <p className="chart-note">Simulation minutes. Added departure delay is an intervention, not the same as arrival delay.</p>
                </div>
                <div className="panel">
                  <Heading eyebrow="PRIORITY QUEUE" title="Conflict snapshot" tag={`${conflicts.length} RECORDS`} />
                  {conflicts.length ? conflicts.slice(0, 4).map((conflict, index) => <ConflictCard key={`${val(conflict,['section_id'],'section')}-${index}`} conflict={conflict} />) :
                    <Empty title="No conflict records loaded" text="Refresh the baseline API to inspect detected conflicts." />}
                  <button className="wide" onClick={() => setTab('conflicts')}>Open conflict register <ArrowRight size={15} /></button>
                </div>
              </section>

              
              <section className="panel" style={{ marginBottom: 24 }}>
                <Heading
                  eyebrow="AI AGENT"
                  title="Traffic analysis"
                  tag="LIVE MODEL DATA"
                />

                <p className="description">
                  Analyze the current synthetic traffic and inspect
                  conflict hotspots using the Traffic Analysis Agent.
                </p>

                <button
                  className="primary"
                  onClick={loadTrafficAnalysis}
                  disabled={trafficBusy}
                >
                  <Activity size={16} />
                  {trafficBusy ? 'Analyzing traffic...' : 'Run traffic analysis'}
                </button>

                <button
                  className="primary"
                  onClick={loadExplainability}
                  style={{ marginTop: 12 }}
                >
                  Explain schedule decisions
                </button>

                {explainability && (
                  <div style={{ marginTop: 20 }}>
                    <Heading
                      eyebrow="EXPLAINABILITY AGENT"
                      title="Schedule decision analysis"
                      tag="ANALYSIS"
                    />

                    <div className="stats-grid" style={{ marginTop: 16 }}>
                      <div className="stat">
                        <span>Trains analyzed</span>
                        <strong>
                          {explainability.summary?.optimized_train_count ?? '—'}
                        </strong>
                      </div>

                      <div className="stat">
                        <span>Baseline conflicts</span>
                        <strong>
                          {explainability.summary?.baseline_conflict_count ?? '—'}
                        </strong>
                      </div>

                      <div className="stat">
                        <span>Remaining conflicts</span>
                        <strong>
                          {explainability.summary?.remaining_conflict_count ?? '—'}
                        </strong>
                      </div>

                      <div className="stat">
                        <span>Trains delayed</span>
                        <strong>
                          {explainability.summary?.trains_with_added_departure_delay ?? '—'}
                        </strong>
                      </div>
                    </div>

                    <h3 style={{ marginTop: 24 }}>Why individual trains were delayed</h3>

                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        gap: 16,
                        marginTop: 16,
                      }}
                    >
                      {(explainability.explanations || []).map(item => (
                        <div
                          key={item.train_id}
                          className="explain-cards"
                          style={{ marginTop: 0, minWidth: 0 }}
                        >
                          <div>
                            <b>{item.train_id}</b>
                            <p>{displayText(item.summary, 'No summary provided.')}</p>
                            <p>{displayText(item.reason, 'No reason provided.')}</p>
                          </div>
                        </div>
                      ))}
                    </div>

                    {explainability.limitations?.length > 0 && (
                      <div className="disclaimer" style={{ marginTop: 16 }}>
                        <b>Model limitations</b>
                        <ul>
                          {explainability.limitations.map((item, index) => (
                            <li key={index}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {trafficError && (
                  <div className="error" style={{ marginTop: 16 }}>
                    <AlertTriangle size={18} />
                    <span>{trafficError}</span>
                  </div>
                )}

                {trafficAnalysis && (
                  <>
                    <div className="stats-grid" style={{ marginTop: 20 }}>
                      <div className="stat">
                        <span>Trains analyzed</span>
                        <strong>
                          {trafficAnalysis.network_summary?.train_count ?? '—'}
                        </strong>
                      </div>
                      <div className="stat">
                        <span>Detected conflicts</span>
                        <strong>
                          {trafficAnalysis.network_summary?.baseline_conflict_count ?? '—'}
                        </strong>
                      </div>
                      <div className="stat">
                        <span>Stations</span>
                        <strong>
                          {trafficAnalysis.network_summary?.station_count ?? '—'}
                        </strong>
                      </div>
                      <div className="stat">
                        <span>Track sections</span>
                        <strong>
                          {trafficAnalysis.network_summary?.track_section_count ?? '—'}
                        </strong>
                      </div>
                    </div>

                    <div className="grid" style={{ marginTop: 20 }}>
                      <div className="panel">
                        <Heading
                          eyebrow="CONFLICT HOTSPOTS"
                          title="Most affected trains"
                        />
                        {(trafficAnalysis.most_affected_trains || []).length ? (
                          trafficAnalysis.most_affected_trains.slice(0, 5).map(item => (
                            <div className="explain" key={item.train_id}>
                              <span><TrainFront size={16} /></span>
                              <div>
                                <b>{item.train_id}</b>
                                <p>{item.conflict_count} detected conflicts</p>
                              </div>
                            </div>
                          ))
                        ) : (
                          <Empty
                            title="No train hotspots"
                            text="The agent returned no train-level conflict counts."
                          />
                        )}
                      </div>

                      <div className="panel">
                        <Heading
                          eyebrow="NETWORK HOTSPOTS"
                          title="Most affected sections"
                        />
                        {(trafficAnalysis.most_affected_sections || []).length ? (
                          trafficAnalysis.most_affected_sections.slice(0, 5).map(item => (
                            <div className="explain" key={item.section_id}>
                              <span><Route size={16} /></span>
                              <div>
                                <b>{item.section_id}</b>
                                <p>{item.conflict_count} detected conflicts</p>
                              </div>
                            </div>
                          ))
                        ) : (
                          <Empty
                            title="No section hotspots"
                            text="The agent returned no section-level conflict counts."
                          />
                        )}
                      </div>
                    </div>

                    <Heading
                      eyebrow="AGENT OUTPUT"
                      title="Conflict type breakdown"
                    />

                    {(trafficAnalysis.conflict_types || []).map(item => (
                      <div className="explain" key={item.type}>
                        <span><GitCompareArrows size={16} /></span>
                        <div>
                          <b>{String(item.type).replaceAll('_', ' ')}</b>
                          <p>{item.count} detected conflicts</p>
                        </div>
                      </div>
                    ))}

                    <Heading
                      eyebrow="RECOMMENDATIONS"
                      title="Suggested areas to review"
                    />

                    {(trafficAnalysis.recommendations || []).map((item, index) => (
                      <div className="insight" key={index}>
                        <div className="warn-icon">
                          <Sparkles size={18} />
                        </div>
                        <div><p>{displayText(item)}</p></div>
                      </div>
                    ))}

                    <div className="disclaimer">
                      Analysis uses synthetic data and the project's configured
                      conflict detector. Recommendations are for demonstration
                      and do not establish real-world railway safety.
                    </div>
                  </>
                )}
              </section>


              
              <section className="panel" style={{ marginBottom: 24 }}>
                <Heading
                  eyebrow="SCHEDULE COMPARISON"
                  title="Baseline vs optimized schedule"
                  tag={opt?.status || 'OPTIMIZATION'}
                />

                {!base || !opt ? (
                  <Empty
                    title="Schedule data unavailable"
                    text="Load the baseline and optimization results using the dashboard refresh control."
                  />
                ) : (
                  <>
                    <div className="stats-grid" style={{ marginTop: 20 }}>
                      <div className="stat">
                        <span>Baseline conflicts</span>
                        <strong>{conflictCount}</strong>
                      </div>

                      <div className="stat">
                        <span>Optimized conflicts</span>
                        <strong>{optCount}</strong>
                      </div>

                      <div className="stat">
                        <span>Added departure delay</span>
                        <strong>{addedTotal} min</strong>
                      </div>

                      <div className="stat">
                        <span>Solver status</span>
                        <strong>{opt.status || '—'}</strong>
                      </div>
                    </div>

                      <div
                      className="panel"
                      style={{
                        marginTop: 20,
                        marginBottom: 20,
                        padding: 20,
                        background: "#111827",
                        color: "#e5e7eb",
                        border: "1px solid #334155",
                      }}
                    >
                      <Heading
                        eyebrow="AI-POWERED EXPLANATION"
                        title="TrackFlow AI insights"
                        tag="GROQ"
                      />

                      <div
                      style={{
                        marginTop: 16,
                        lineHeight: 1.8,
                        color: "#e5e7eb",
                        fontSize: 15,
                      }}
                    >
                      <ReactMarkdown>
                        {typeof opt.final_response === 'string'
                          ? opt.final_response
                          : displayText(opt.final_response, 'AI explanation is not available. Run the optimization again.')}
                      </ReactMarkdown>
                    </div>
                    </div>

                    
                    <Heading
                      eyebrow="TRAIN-BY-TRAIN IMPACT"
                      title="Departure schedule comparison"
                      tag={`${(opt.optimized_trains || []).length} TRAINS`}
                    />

                    <div style={{ overflowX: 'auto', marginTop: 16 }}>
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Train</th>
                            <th>Original departure</th>
                            <th>Optimized departure</th>
                            <th>Added delay</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(opt.optimized_trains  || []).map((train) => {
                            const baselineTrain = (base.trains || []).find(
                              item => item.train_id === train.train_id
                            );

                            const originalDeparture =
                              baselineTrain?.scheduled_departure ?? '—';

                            const optimizedDeparture =
                              train.scheduled_departure ?? '—';

                            const addedDelay =
                              typeof originalDeparture === 'number' &&
                              typeof optimizedDeparture === 'number'
                                ? optimizedDeparture - originalDeparture
                                : '—';

                            return (
                              <tr key={train.train_id}>
                                <td><strong>{train.train_id}</strong></td>
                                <td>{originalDeparture} min</td>
                                <td>{optimizedDeparture} min</td>
                                <td>
                                  {typeof addedDelay === 'number'
                                    ? `+${addedDelay} min`
                                    : addedDelay}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>


                    <div className="disclaimer" style={{ marginTop: 20 }}>
                      The comparison uses synthetic train schedules and the
                      project's configured optimization checks. A zero-conflict
                      result does not establish real-world railway safety.
                    </div>
                  </>
                )}
              </section>


            </>
          )}

          {tab === 'trains' && (
            <section className="panel table-panel">
              <Heading eyebrow="LIVE SIMULATION DATA" title="Train operations" tag={`${trains.length} TRAINS`} />
              <p className="description">Train values are read from the baseline or optimizer API response. All times are simulation minutes.</p>
              <div className="toolbar"><div className="searchbox"><Search size={16} /><input value={trainSearch} onChange={event => setTrainSearch(event.target.value)} placeholder="Search train ID…" /></div>
                <button className="secondary" onClick={() => load(isOptimized)} disabled={busy}><RefreshCw size={14} /> Refresh</button></div>
              {filteredTrains.length ? <TrainTable trains={filteredTrains} optimized={isOptimized} /> : <Empty title="No train records found" text={trains.length ? 'Try another train ID.' : 'Start the backend and refresh the page.'} />}
              <div className="disclaimer">ⓘ This prototype displays simulated values only and must not be used for real train movement decisions.</div>
            </section>
          )}

          {tab === 'conflicts' && (
            <section className="panel table-panel">
              <Heading eyebrow="CONFLICT REGISTER" title="Conflict intelligence" tag={`${filteredConflicts.length} SHOWN`} />
              <p className="description">A conflict is a potential incompatibility detected by the current model rules. This prototype does not represent every real railway safety constraint.</p>
              <div className="toolbar">
                <div className="searchbox"><Search size={16} /><input value={conflictSearch} onChange={event => setConflictSearch(event.target.value)} placeholder="Search train, section, or message…" /></div>
                <div className="selectbox"><Filter size={15} /><select value={conflictFilter} onChange={event => setConflictFilter(event.target.value)}>
                  <option value="all">All conflict types</option>
                  <option value="overlapping_occupancy">Track occupancy overlap</option>
                  <option value="headway_violation">Headway violation</option>
                  <option value="opposing_movements">Opposing train movements</option>
                  <option value="single_track_occupancy">Single-track occupancy</option>
                </select></div>
              </div>
              {isOptimized && <div className="success"><CheckCircle2 size={18} /><span>Optimizer response reports {optCount} conflicts under the configured validator. This is not a real-world safety certification.</span></div>}
              {filteredConflicts.length ? <div className="conflict-list">{filteredConflicts.map((conflict, index) => <ConflictCard key={`${val(conflict,['section_id'],'section')}-${index}`} conflict={conflict} detailed />)}</div> :
                <Empty title={conflicts.length ? 'No matching conflicts' : 'No conflict records loaded'} text={conflicts.length ? 'Change the search text or filter.' : 'Refresh the baseline API to load the conflict register.'} />}
              <div className="disclaimer">ⓘ Model-level checks only. Do not use this prototype to issue real-world train movement instructions.</div>
            </section>
          )}

          
          {tab === 'disruption' && (
            <section className="panel table-panel">
              <Heading
                eyebrow="WHAT-IF SCENARIO LAB"
                title="Disruption simulator"
                tag="SIMULATION ONLY"
              />
              <p className="description">
                Choose a disruption scenario. Train delay changes one train's departure;
                track closure blocks a selected section for a time window. TrackFlow then
                evaluates the scenario using the configured optimizer and validator.
              </p>

              <div className="toolbar" style={{ marginTop: 20 }}>
                <button
                  className={disruptionMode === 'train-delay' ? 'primary' : 'secondary'}
                  onClick={() => { setDisruptionMode('train-delay'); setError(''); setDisruptionResult(null); setClosureResult(null); }}
                  type="button"
                >
                  <TrainFront size={16} /> Train delay
                </button>
                <button
                  className={disruptionMode === 'track-closure' ? 'primary' : 'secondary'}
                  onClick={() => { setDisruptionMode('track-closure'); setError(''); setDisruptionResult(null); setClosureResult(null); }}
                  type="button"
                >
                  <Layers3 size={16} /> Track closure
                </button>
              </div>

              <div className="panel" style={{ marginTop: 16, background: 'rgba(15, 29, 47, 0.72)' }}>
                {disruptionMode === 'train-delay' ? (
                  <>
                    <Heading eyebrow="SCENARIO 01" title="Apply a train departure delay" tag="TRAIN DELAY" />
                    <p className="description">Select a train and add a synthetic delay between 1 and 120 minutes.</p>
                    <div className="toolbar" style={{ marginTop: 16 }}>
                      <div className="selectbox">
                        <TrainFront size={16} />
                        <select value={disruptionTrain} onChange={event => setDisruptionTrain(event.target.value)}>
                          {(base?.trains || []).map(train => (
                            <option key={train.train_id} value={train.train_id}>{train.train_id} — {train.train_name || train.train_id}</option>
                          ))}
                        </select>
                      </div>
                      <div className="searchbox">
                        <Clock3 size={16} />
                        <input type="number" min="1" max="120" value={disruptionDelay}
                          onChange={event => setDisruptionDelay(event.target.value)} aria-label="Delay in minutes" />
                        <span>min</span>
                      </div>
                      <button className="primary" onClick={runDisruption}
                        disabled={busy || !disruptionTrain || Number(disruptionDelay) < 1 || Number(disruptionDelay) > 120}>
                        <Zap size={15} /> {busy ? 'Running scenario…' : 'Run train-delay scenario'}
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <Heading eyebrow="SCENARIO 02" title="Temporarily close a track section" tag="TRACK CLOSURE" />
                    <p className="description">Choose a section and define when it is unavailable. Times are simulation minutes from the start of the scenario.</p>
                    <div className="toolbar" style={{ marginTop: 16 }}>
                      <div className="selectbox">
                        <Route size={16} />
                        <select value={closureSection} onChange={event => setClosureSection(event.target.value)} aria-label="Track section">
                          {(trackSections.length ? trackSections : [
                            { section_id: 'SEC_AB' }, { section_id: 'SEC_BC' },
                            { section_id: 'SEC_CD' }, { section_id: 'SEC_DE' },
                            { section_id: 'SEC_BD' }, { section_id: 'SEC_CE' },
                            { section_id: 'SEC_AC' }, { section_id: 'SEC_BD_LOOP' },
                          ]).map(section => (
                            <option key={section.section_id} value={section.section_id}>{section.section_id}</option>
                          ))}
                        </select>
                      </div>
                      <label className="searchbox" style={{ gap: 8 }}>
                        <Clock3 size={16} /><span>Start</span>
                        <input type="number" min="0" value={closureStart}
                          onChange={event => setClosureStart(event.target.value)} aria-label="Closure start minute" />
                      </label>
                      <label className="searchbox" style={{ gap: 8 }}>
                        <Clock3 size={16} /><span>End</span>
                        <input type="number" min="1" value={closureEnd}
                          onChange={event => setClosureEnd(event.target.value)} aria-label="Closure end minute" />
                      </label>
                      <button className="primary" onClick={runTrackClosure}
                        disabled={busy || !closureSection || closureStart === '' || closureEnd === '' || Number(closureStart) < 0 || Number(closureEnd) <= Number(closureStart)}>
                        <Zap size={15} /> {busy ? 'Running scenario…' : 'Run track-closure scenario'}
                      </button>
                    </div>
                    {Number(closureEnd) <= Number(closureStart) && (
                      <p className="description" style={{ color: '#ff9b9b', marginTop: 10 }}>End minute must be greater than start minute.</p>
                    )}
                  </>
                )}
              </div>

              {error && (
                <div className="error" style={{ marginTop: 16 }}>
                  <AlertTriangle size={18} /><span>{error}</span>
                  <button onClick={() => setError('')}>Dismiss</button>
                </div>
              )}

              {disruptionMode === 'train-delay' && disruptionResult && (
                <>
                  <Heading eyebrow="SCENARIO RESULTS" title="Train-delay impact" tag={disruptionResult.optimization_status || 'COMPLETED'} />
                  <div className="stats-grid" style={{ marginTop: 16 }}>
                    <div className="stat"><span>Baseline conflicts</span><strong>{disruptionResult.baseline_conflicts ?? '—'}</strong></div>
                    <div className="stat"><span>After disruption</span><strong>{disruptionResult.disrupted_conflicts ?? '—'}</strong></div>
                    <div className="stat"><span>After optimization</span><strong>{disruptionResult.optimized_conflicts ?? '—'}</strong></div>
                    <div className="stat"><span>Optimizer-added delay</span><strong>{disruptionResult.total_added_departure_delay_minutes ?? '—'} min</strong></div>
                  </div>
                  <div className="insight" style={{ marginTop: 16 }}>
                    <div className="warn-icon"><AlertTriangle size={18} /></div>
                    <div><b>Disruption summary: {disruptionResult.disrupted_train_id || disruptionTrain}</b>
                      <p>A synthetic delay of {disruptionResult.disruption_delay_minutes ?? disruptionDelay} minutes was applied. The model reports {disruptionResult.disrupted_conflicts ?? '—'} conflicts after disruption and {disruptionResult.optimized_conflicts ?? '—'} after optimization.</p>
                    </div>
                  </div>
                  <div className={disruptionResult.validation?.passed ? 'success' : 'error'} style={{ marginTop: 16 }}>
                    {disruptionResult.validation?.passed ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
                    <span>{disruptionResult.validation?.passed ? 'Configured validation checks passed.' : 'Validation needs review or was not reported as passed.'}</span>
                  </div>
                  <Heading eyebrow="SCHEDULE COMPARISON" title="Disrupted vs optimized trains" tag={`${disruptionResult.optimized_trains?.length || 0} TRAINS`} />
                  <div className="table-scroll" style={{ marginTop: 12 }}>
                    <table><thead><tr><th>Train</th><th>Original departure</th><th>Disrupted departure</th><th>Optimized departure</th><th>Added optimizer delay</th></tr></thead>
                      <tbody>{(disruptionResult.disrupted_trains || []).map(train => {
                        const optimized = (disruptionResult.optimized_trains || []).find(item => item.train_id === train.train_id);
                        const original = (base?.trains || []).find(item => item.train_id === train.train_id);
                        return <tr key={train.train_id}><td><b>{train.train_id}</b></td><td>{original?.scheduled_departure ?? '—'} min</td><td>{train.scheduled_departure ?? '—'} min</td><td>{optimized?.scheduled_departure ?? '—'} min</td><td>{optimized?.added_departure_delay_minutes ?? '—'} min</td></tr>;
                      })}</tbody>
                    </table>
                  </div>
                  {disruptionResult.validation?.integrity_errors?.length > 0 && <div className="disclaimer"><b>Validation errors</b><ul>{disruptionResult.validation.integrity_errors.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
                </>
              )}

              {disruptionMode === 'track-closure' && closureResult && (() => {
                const validation = closureResult.validation || {};
                const closureTrains = arr(val(closureResult, ['optimized_trains', 'trains', 'disrupted_trains'], []));
                const closureConflicts = arr(val(closureResult, ['remaining_conflicts', 'conflicts'], []));
                const delayTotal = val(closureResult, ['total_added_departure_delay_minutes', 'total_added_delay_minutes'], '—');
                const validationPassed = val(validation, ['passed', 'is_valid'], false);
                return (
                  <>
                    <Heading eyebrow="SCENARIO RESULTS" title="Track-closure impact" tag={closureResult.status || 'COMPLETED'} />
                    <div className="insight" style={{ marginTop: 16 }}>
                      <div className="warn-icon"><AlertTriangle size={18} /></div>
                      <div><b>{closureResult.disruption?.section_id || closureSection} temporarily unavailable</b>
                        <p>Closure window: minute {closureResult.disruption?.start_minute ?? closureStart} to {closureResult.disruption?.end_minute ?? closureEnd}. The optimizer attempted to reschedule movements around this restriction.</p>
                      </div>
                    </div>
                    <div className="stats-grid" style={{ marginTop: 16 }}>
                      <div className="stat"><span>Remaining conflicts</span><strong>{closureConflicts.length}</strong></div>
                      <div className="stat"><span>Added departure delay</span><strong>{delayTotal}{typeof delayTotal === 'number' ? ' min' : ''}</strong></div>
                      <div className="stat"><span>Solver status</span><strong>{closureResult.status || '—'}</strong></div>
                      <div className="stat"><span>Validation</span><strong>{validationPassed ? 'Passed' : 'Review'}</strong></div>
                    </div>
                    <div className={validationPassed ? 'success' : 'error'} style={{ marginTop: 16 }}>
                      {validationPassed ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
                      <span>{validationPassed ? 'Configured validation checks passed.' : 'Validation did not report a passed result. Review the details below.'}</span>
                    </div>
                    {closureResult.final_response && <div className="panel" style={{ marginTop: 16 }}><Heading eyebrow="TRACKFLOW EXPLANATION" title="Scenario analysis" tag="AI / FALLBACK" /><div style={{ marginTop: 12, lineHeight: 1.7 }}><ReactMarkdown>{typeof closureResult.final_response === 'string' ? closureResult.final_response : displayText(closureResult.final_response)}</ReactMarkdown></div></div>}
                    {closureResult.explanation && <div className="panel" style={{ marginTop: 16 }}><Heading eyebrow="OPTIMIZER EXPLANATION" title="Why the schedule changed" /><p className="description">{typeof closureResult.explanation === 'string' ? closureResult.explanation : displayText(closureResult.explanation.summary, 'The API returned structured explanation data.')}</p></div>}
                    {validation.integrity_errors?.length > 0 && <div className="disclaimer" style={{ marginTop: 16 }}><b>Validation errors</b><ul>{validation.integrity_errors.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
                    <Heading eyebrow="OPTIMIZED MOVEMENTS" title="Train schedule after closure" tag={`${closureTrains.length} TRAINS`} />
                    {closureTrains.length ? (
                      <div className="table-scroll" style={{ marginTop: 12 }}><table><thead><tr><th>Train</th><th>Departure</th><th>Simulated arrival</th><th>Added departure delay</th></tr></thead><tbody>
                        {closureTrains.map((train, index) => <tr key={trainId(train, index)}><td><b>{trainId(train, index)}</b></td><td>{departure(train)} min</td><td>{arrival(train)} min</td><td>{addedDelay(train)} min</td></tr>)}
                      </tbody></table></div>
                    ) : <Empty title="No train schedule returned" text="The endpoint did not include an optimized train list in this response." />}
                    {closureConflicts.length > 0 && <><Heading eyebrow="VALIDATOR OUTPUT" title="Remaining model conflicts" tag={`${closureConflicts.length} RECORDS`} /><div className="conflict-list">{closureConflicts.map((conflict, index) => <ConflictCard key={`${conflict.section_id || 'section'}-${index}`} conflict={conflict} detailed />)}</div></>}
                    <div className="disclaimer" style={{ marginTop: 16 }}>Synthetic scenario only. Validation covers the project's configured model checks and does not establish real-world railway safety.</div>
                  </>
                );
              })()}

              {!disruptionResult && !closureResult && (
                <Empty
                  title="Ready to simulate"
                  text={disruptionMode === 'train-delay'
                    ? 'Select a train, enter a delay from 1 to 120 minutes, and run the scenario.'
                    : 'Select a track section and closure time window, then run the scenario.'}
                />
              )}
              <div className="disclaimer" style={{ marginTop: 18 }}>
                <b>Operational limitation:</b> TrackFlow is a synthetic decision-support prototype, not a certified railway signalling or dispatch system. Never use these outputs to control real train movements.
              </div>
            </section>
          )}


          <footer>TRACKFLOW <b>·</b> TRAFFIC THROUGHPUT CONTROL <span><i /> API-driven prototype · Synthetic dataset</span></footer>
        </div>
      </main>
    </div>
  );
}

function ConflictCard({ conflict, detailed = false }) {
  const first = val(conflict, ['train_1', 'train_a', 'train1', 'first_train'], 'Unknown train');
  const second = val(conflict, ['train_2', 'train_b', 'train2', 'second_train'], 'Unknown train');
  const section = val(conflict, ['section_id', 'section'], 'Unknown section');
  const type = val(conflict, ['conflict_type', 'type'], 'track_occupancy_overlap');
  const message = val(conflict, ['message', 'description'], '');
  const severity = val(conflict, ['severity'], 'Model-detected');
  return <article className={`conflict-card ${detailed ? 'detailed' : ''}`}>
    <div className="conflict-icon"><AlertTriangle size={16} /></div>
    <div className="conflict-content">
      <b>{formatConflictType(type)}</b>
      <small>{first} ↔ {second} · {section}</small>
      {detailed && <>
        <p>{displayText(message, 'The API did not provide a detailed explanation for this record.')}</p>
        <small className="conflict-measure">{conflictDetails(conflict)}</small>
        {(conflict.train_1_direction || conflict.train_2_direction) && <small>Directions: {val(conflict,['train_1_direction'],'—')} / {val(conflict,['train_2_direction'],'—')}</small>}
      </>}
    </div>
    <em>{displayText(severity, 'Model-detected')}</em>
  </article>;
}
function TrainTable({ trains, optimized }) {
  return <div className="table-scroll"><table><thead><tr><th>TRAIN</th><th>DEPARTURE</th><th>SIM. ARRIVAL</th><th>ARRIVAL DELAY</th><th>ADDED DEPARTURE</th><th>STATUS</th></tr></thead>
    <tbody>{trains.map((train, index) => <tr key={trainId(train,index)}>
      <td><div className="trainname"><span><TrainFront size={15} /></span><b>{trainId(train,index)}</b></div></td>
      <td>{departure(train)} <small>min</small></td><td>{arrival(train)} <small>min</small></td>
      <td><label className={arrivalDelay(train) ? 'late' : 'good'}>{arrivalDelay(train)} min</label></td>
      <td><label className={optimized && addedDelay(train) ? 'adjusted' : 'good'}>{optimized ? `+${addedDelay(train)} min` : '—'}</label></td>
      <td><span className="table-status"><i />{optimized && addedDelay(train) > 0 ? 'Adjusted' : optimized ? 'No added delay' : 'Baseline'}</span></td>
    </tr>)}</tbody></table></div>;
}
function Stat({ icon: Icon, label, value, sub, color }) {
  return <div className={`stat ${color}`}><div className="stat-icon"><Icon size={18} /></div><small>{label}</small><strong>{value}</strong><p>{sub}</p></div>;
}
function Heading({ eyebrow, title, tag }) {
  return <div className="heading"><div><small>{eyebrow}</small><h2>{title}</h2></div>{tag && <span>{tag}</span>}</div>;
}
function Explain({ number, title, children }) {
  return <div className="explain"><span>{number}</span><div><b>{title}</b><p>{children}</p></div></div>;
}
function Empty({ title, text }) {
  return <div className="empty"><CheckCircle2 size={22} /><b>{title}</b><span>{text}</span></div>;
}

const TrackFlowChatStyles = () => <style>{`
.tf-chat-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px;align-items:start;margin:4px 0 26px}.tf-chat-main{padding:0!important;overflow:hidden;min-height:720px;display:flex;flex-direction:column}.tf-chat-topbar{display:flex;align-items:center;gap:12px;padding:18px 22px;border-bottom:1px solid rgba(148,163,184,.16);background:linear-gradient(120deg,rgba(49,203,184,.08),rgba(113,136,255,.07))}.tf-chat-agent-mark{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,#31cbb8,#7188ff);color:#071827}.tf-chat-agent-title{display:grid;gap:4px;flex:1}.tf-chat-agent-title b{font-size:14px}.tf-chat-agent-title span{font-size:11px;color:#8fa4bb}.tf-chat-agent-title span i,.tf-chat-status span i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#31cbb8;margin-right:6px;box-shadow:0 0 0 4px rgba(49,203,184,.1)}.tf-icon-button{border:1px solid rgba(148,163,184,.2);background:rgba(148,163,184,.07);color:#9eb1c7;border-radius:10px;padding:9px;cursor:pointer}.tf-icon-button:disabled{opacity:.35;cursor:not-allowed}.tf-chat-messages{padding:24px;flex:1;min-height:480px;max-height:680px;overflow:auto;display:flex;flex-direction:column;gap:22px}.tf-chat-welcome{max-width:760px;margin:auto;width:100%;padding:14px 0 24px}.tf-welcome-orb{width:54px;height:54px;display:grid;place-items:center;border-radius:18px;background:linear-gradient(135deg,rgba(49,203,184,.2),rgba(113,136,255,.22));border:1px solid rgba(113,136,255,.22);color:#77e1d3;margin-bottom:20px}.tf-chat-eyebrow,.tf-side-kicker{font-size:10px;letter-spacing:1.5px;font-weight:800;color:#6fd8cc}.tf-chat-welcome h2{font-size:clamp(25px,3vw,36px);letter-spacing:-1px;margin:8px 0;color:#eef5ff}.tf-chat-welcome>p{color:#91a5bc;line-height:1.7;max-width:650px;font-size:13px}.tf-prompt-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:24px}.tf-prompt-card{position:relative;text-align:left;display:grid;gap:7px;padding:15px;border-radius:13px;border:1px solid rgba(148,163,184,.17);background:rgba(17,30,48,.65);color:#e8f0fb;cursor:pointer;transition:.2s}.tf-prompt-card:hover{transform:translateY(-2px);border-color:rgba(49,203,184,.55);background:rgba(31,55,72,.65)}.tf-prompt-card:disabled{opacity:.5;cursor:not-allowed}.tf-prompt-icon{color:#67d8cb}.tf-prompt-card b{font-size:12px}.tf-prompt-card small{font-size:10px;line-height:1.5;color:#8fa4bb;padding-right:8px}.tf-prompt-arrow{position:absolute;right:13px;top:15px;color:#6f89a4}.tf-message{display:flex;gap:12px;max-width:900px;width:100%;margin:0 auto}.tf-message-user{flex-direction:row-reverse}.tf-message-avatar{width:32px;height:32px;flex:0 0 32px;border-radius:11px;background:rgba(113,136,255,.16);color:#9eafff;display:grid;place-items:center;font-size:9px;font-weight:800}.tf-message-user .tf-message-avatar{background:rgba(49,203,184,.15);color:#6fe0d1}.tf-message-body{min-width:0;max-width:calc(100% - 44px);flex:1}.tf-message-user .tf-message-body{display:flex;align-items:flex-end;flex-direction:column}.tf-message-meta{display:flex;align-items:center;gap:10px;margin:0 0 7px;font-size:11px}.tf-message-meta b{color:#dce8f7}.tf-message-meta time{font-size:10px;color:#71869d}.tf-message-bubble{padding:13px 16px;border:1px solid rgba(148,163,184,.16);border-radius:4px 14px 14px 14px;background:rgba(17,30,48,.72);color:#d5e1ef;font-size:12px;line-height:1.75;overflow-wrap:anywhere}.tf-message-user .tf-message-bubble{border-radius:14px 4px 14px 14px;background:rgba(49,203,184,.1);border-color:rgba(49,203,184,.2);color:#e5fbf7}.tf-message-bubble p{margin:0 0 8px}.tf-message-bubble p:last-child{margin-bottom:0}.tf-message-bubble ul,.tf-message-bubble ol{padding-left:20px}.tf-message-bubble strong{color:#fff}.tf-message-failed{border-color:rgba(255,120,120,.35);color:#ffc1c1}.tf-result-panel{margin-top:9px;padding:12px;border-radius:12px;border:1px solid rgba(148,163,184,.15);background:rgba(8,18,31,.5)}.tf-result-heading{display:flex;align-items:center;justify-content:space-between;font-size:9px;letter-spacing:1px;color:#7fded2;font-weight:800}.tf-result-heading span,.tf-result-heading button{display:flex;align-items:center;gap:6px}.tf-result-heading button{background:none;border:0;color:#91a6bd;cursor:pointer;font-size:10px;letter-spacing:0}.tf-tool-chips{display:flex;gap:7px;flex-wrap:wrap;margin:11px 0}.tf-tool-chips span{display:flex;align-items:center;gap:5px;padding:5px 8px;border-radius:20px;background:rgba(49,203,184,.1);color:#8ce3d8;font-size:10px}.tf-result-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:11px}.tf-result-stats>div{padding:9px;border-radius:9px;background:rgba(148,163,184,.07);display:grid;gap:5px;min-width:0}.tf-result-stats small{font-size:8px;letter-spacing:.7px;color:#8297ad}.tf-result-stats b{font-size:12px;color:#e8f1fb;overflow-wrap:anywhere}.tf-good{color:#65d9b2!important}.tf-warn{color:#ffc17a!important}.tf-result-muted,.tf-result-error{font-size:10px;color:#91a5bb;margin:10px 0 0}.tf-result-error{color:#ffaaaa}.tf-safety-note{font-size:9px;line-height:1.5;color:#71869d;margin:10px 0 0}.tf-typing{display:flex;align-items:center;gap:11px;max-width:900px;width:100%;margin:0 auto;color:#a9bbcf;font-size:11px}.tf-typing p{display:flex;align-items:center;gap:4px;color:#71869d;margin:5px 0}.tf-typing p i{width:5px;height:5px;background:#6ed8ca;border-radius:50%;animation:tf-pulse 1s infinite}.tf-typing p i:nth-child(2){animation-delay:.15s}.tf-typing p i:nth-child(3){animation-delay:.3s}@keyframes tf-pulse{0%,80%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}.tf-chat-composer{padding:15px 20px 17px;border-top:1px solid rgba(148,163,184,.15);background:rgba(7,17,29,.55)}.tf-chat-composer textarea{width:100%;resize:vertical;min-height:58px;max-height:150px;background:rgba(17,30,48,.9);border:1px solid rgba(148,163,184,.2);border-radius:11px;padding:13px 14px;color:#e6effb;font:inherit;font-size:12px;outline:none}.tf-chat-composer textarea:focus{border-color:rgba(49,203,184,.6);box-shadow:0 0 0 3px rgba(49,203,184,.08)}.tf-composer-footer{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:10px}.tf-composer-footer>span{display:flex;align-items:center;gap:5px;color:#71869d;font-size:9px}.tf-composer-footer button{display:flex;align-items:center;gap:7px;border:0;border-radius:9px;padding:10px 15px;background:linear-gradient(135deg,#31cbb8,#7188ff);color:#071827;font-size:11px;font-weight:800;cursor:pointer}.tf-composer-footer button:disabled{opacity:.4;cursor:not-allowed}.tf-chat-error{margin:10px 20px 0;padding:10px 12px;border:1px solid rgba(255,120,120,.3);border-radius:9px;color:#ffb3b3;font-size:11px;display:flex;gap:8px;align-items:center}.tf-chat-error button{margin-left:auto;border:0;background:none;color:inherit;cursor:pointer}.tf-chat-sidebar{display:grid;gap:14px}.tf-capability-panel,.tf-tips-panel{padding:18px}.tf-capability-panel h3,.tf-tips-panel h3{font-size:16px;margin:8px 0 18px;color:#edf4ff}.tf-capability{display:flex;align-items:center;gap:10px;padding:11px 0;border-top:1px solid rgba(148,163,184,.12)}.tf-capability>span{width:32px;height:32px;display:grid;place-items:center;border-radius:9px;background:rgba(113,136,255,.12);color:#91a5ff}.tf-capability div{display:grid;gap:3px;flex:1}.tf-capability b{font-size:10px;color:#dce7f5}.tf-capability small{font-size:9px;color:#7f94aa}.tf-capability>i{width:6px;height:6px;border-radius:50%;background:#31cbb8}.tf-tips-panel ul{padding-left:17px;margin:0;color:#91a5bb;font-size:10px;line-height:1.9}.tf-chat-status{padding:13px 15px;border-radius:12px;border:1px solid rgba(49,203,184,.18);background:rgba(49,203,184,.05);display:grid;gap:7px}.tf-chat-status span{font-size:10px;color:#8fe1d6}.tf-chat-status b{font-size:11px;color:#dbe9f7}.tf-chat-status small{font-size:9px;color:#71869d;overflow-wrap:anywhere}
@media(max-width:1050px){.tf-chat-layout{grid-template-columns:1fr}.tf-chat-sidebar{grid-template-columns:repeat(2,minmax(0,1fr))}.tf-chat-status{grid-column:1/-1}}@media(max-width:650px){.tf-chat-messages{padding:16px;min-height:420px}.tf-chat-main{min-height:650px}.tf-prompt-grid{grid-template-columns:1fr}.tf-chat-sidebar{grid-template-columns:1fr}.tf-result-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.tf-composer-footer{align-items:flex-start;flex-direction:column}.tf-composer-footer button{align-self:flex-end}.tf-chat-topbar{padding:14px}.tf-chat-welcome h2{font-size:27px}}
`}</style>;

export default App;
