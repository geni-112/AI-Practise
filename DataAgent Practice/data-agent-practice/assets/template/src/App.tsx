import LanguageSwitcher, {useLocale} from './Locale';
import {t,getLocale} from './i18n';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDown, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, BarChart3, Bell, BookOpen, Braces, Check, CheckCheck, CheckCircle2, ChevronDown, ChevronRight, Clock3, Code2, Copy, Database, Download, ExternalLink, FileCheck2, FileText, Filter, Folder, GitBranch, Globe2, GripVertical, HelpCircle, History, Layers3, LayoutDashboard, Link2, ListChecks, Loader2, LockKeyhole, Maximize2, MessageSquare, MoreHorizontal, Network, Pause, Play, Plus, RefreshCw, Search, Send, Settings2, ShieldCheck, Sparkles, Square, Table2, Terminal, Trash2, Users, X, Zap } from 'lucide-react';
import { ReactFlow, Background, Controls, Handle, Position, addEdge, applyNodeChanges, applyEdgeChanges, type Node, type Edge, type Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import Chart from './Chart';
import { type DemoData, type Persona, type Row, type Analysis, type WorkflowDef, type WorkflowNode, type Job, personas, assets, domainNames, domainColors, visibleAssets, scopedRows, overview, money, number, sum, analyze, normalizeQuestion, defaultWorkflow, validateFlow, executeDemoFlow, download, csv, useStoredInitial } from './lib';
type Page = 'bi' | 'catalog' | 'flows' | 'jobs' | 'governance' | 'connections';
const nav = [{ id: 'bi', label: 'ChatBI 分析', icon: MessageSquare }, { id: 'catalog', label: '数据目录', icon: Database }, { id: 'flows', label: '流程编排', icon: GitBranch }, { id: 'jobs', label: '任务中心', icon: ListChecks }, { id: 'governance', label: '分权分域', icon: ShieldCheck }, { id: 'connections', label: '连接与模型', icon: Link2 }];
const prompts = [{ title: '地区销售表现', text: '分析 10 月各地区销售额', description: '销售额、订单量与地区贡献', icon: BarChart3, color: 'success' }, { title: '广告投放回报', text: '分析 10 月各广告平台的 ROAS', description: '连接业务表现与投放数据', icon: Globe2, color: 'purple' }, { title: '库存健康检查', text: '检查低于补货阈值的库存', description: '识别短缺与数据质量异常', icon: Layers3, color: 'gold' }];
const stageIcons: Record<string, any> = { source: Database, transform: Filter, aggregate: BarChart3, quality: ShieldCheck, publish: ArrowUpRight };
const time = (s: string) => new Date(s).toLocaleTimeString(getLocale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const statusLabels: Record<string, string> = { queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' };
function Badge({ children, tone = 'neutral' }: {
    children: React.ReactNode;
    tone?: string;
}) { return <span className={`badge ${tone}`}><i />{children}</span>; }
function Empty({ title, description, children }: {
    title: string;
    description: string;
    children?: React.ReactNode;
}) { return <div className="empty"><Layers3 size={32}/><h3>{t(title)}</h3><p>{t(description)}</p>{children}</div>; }
function Table({ rows, limit = 8 }: {
    rows: Row[];
    limit?: number;
}) { if (!rows.length)
    return <Empty title={t("暂无记录")} description={t("当前筛选或授权范围内没有匹配的数据。")}/>; const keys = Object.keys(rows[0]); return <div className="table-scroll"><table><thead><tr>{keys.map(k => <th key={k}>{k}</th>)}</tr></thead><tbody>{rows.slice(0, limit).map((r, i) => <tr key={i}>{keys.map(k => <td key={k} title={String(r[k] ?? 'NULL')}>{r[k] == null ? <span className="muted">{t("NULL")}</span> : typeof r[k] === 'number' ? numberValue(r[k]) : String(r[k])}</td>)}</tr>)}</tbody></table></div>; }
function numberValue(v: number) { return Number.isInteger(v) ? number(v) : v.toLocaleString(getLocale(), { maximumFractionDigits: 2 }); }
function Sparkline({ values }: {
    values: number[];
}) { const min = Math.min(...values), range = Math.max(...values) - min || 1; const d = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${i * 65 / Math.max(values.length - 1, 1)} ${24 - (v - min) / range * 20}`).join(' '); return <svg width="68" height="28" viewBox="0 0 68 28" aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>; }
export default function App() {
    const locale = useLocale();
    const [data, setData] = useState<DemoData | null>(null);
    const [loadError, setLoadError] = useState('');
    const [page, setPage] = useState<Page>('bi');
    const [tenant, setTenant] = useState('luma');
    const [persona, setPersona] = useState<Persona>('analyst');
    const current = personas[persona];
    const [health, setHealth] = useState<Row | null>(null);
    const [apiReady, setApiReady] = useState(false);
    const [registeredAssets, setRegisteredAssets] = useState<Row[] | null>(null);
    const [question, setQuestion] = useState('');
    const [history, setHistory] = useState<Analysis[]>([]);
    const [active, setActive] = useState<Analysis | null>(null);
    const [busy, setBusy] = useState(false);
    const scopeRef = useRef(0);
    const [month, setMonth] = useState('2026-10');
    const [resultTab, setResultTab] = useState('chart');
    const [chartType, setChartType] = useState('bar');
    const [saved, setSaved] = useState<Analysis[]>(() => useStoredInitial('nexo-boards', []));
    const [showBoards, setShowBoards] = useState(false);
    const [workflow, setWorkflow] = useState<WorkflowDef>(() => useStoredInitial('nexo-flow-luma', defaultWorkflow('luma')));
    const [jobs, setJobs] = useState<Job[]>(() => useStoredInitial('nexo-jobs', []));
    const [selectedJob, setSelectedJob] = useState<Job | null>(null);
    const [selectedAsset, setSelectedAsset] = useState<Row | null>(null);
    const [assetTab, setAssetTab] = useState('columns');
    const [search, setSearch] = useState('');
    const [catalogDomain, setCatalogDomain] = useState('all');
    const [catalogSource, setCatalogSource] = useState('all');
    const [toast, setToast] = useState('');
    const [modal, setModal] = useState('');
    const [audit, setAudit] = useState<Row[]>(() => useStoredInitial('nexo-audit', []));
    const [policies, setPolicies] = useState<Record<string, boolean>>(() => useStoredInitial('nexo-policies', {}));
    const [policyRole, setPolicyRole] = useState<Persona>('manager');
    const [draftModel, setDraftModel] = useState(() => useStoredInitial('nexo-model', { provider: 'Huawei Cloud MaaS', model: 'glm-5.3', baseUrl: '' }));
    const [jobFilter, setJobFilter] = useState('all');
    const [activeDomain, setActiveDomain] = useState('Sales');
    const showToast = (message: string) => { setToast(message); };
    const record = (action: string, target: string, outcome = 'Allowed') => setAudit(old => [{ id: crypto.randomUUID(), tenant, actor: current.en, role: current.name, action, target, outcome, at: new Date().toISOString() }, ...old].slice(0, 100));
    useEffect(() => { fetch('/demo-data.json').then(r => { if (!r.ok)
        throw Error(t("演示数据加载失败")); return r.json(); }).then(setData).catch(e => setLoadError(e.message)); fetch('/api/health').then(r => r.json()).then(async (h) => { if (h.service === 'nexo-api' && scopeRef.current === 0) {
        setHealth(h);
        const r = await fetch('/api/demo/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tenant: 'luma', persona: 'analyst' }) });
        if (scopeRef.current === 0)
            setApiReady(r.ok);
    } }).catch(() => { }); }, []);
    useEffect(() => { if (!toast)
        return; const localT = setTimeout(() => setToast(''), 4200); return () => clearTimeout(localT); }, [toast]);
    useEffect(() => { localStorage.setItem('nexo-jobs', JSON.stringify(jobs)); }, [jobs]);
    useEffect(() => { localStorage.setItem('nexo-audit', JSON.stringify(audit)); }, [audit]);
    useEffect(() => { localStorage.setItem('nexo-boards', JSON.stringify(saved)); }, [saved]);
    useEffect(() => { localStorage.setItem('nexo-policies', JSON.stringify(policies)); }, [policies]);
    const switchScope = async (nextTenant: string, nextPersona: Persona) => {
        scopeRef.current++;
        setRegisteredAssets(null);
        setBusy(false);
        setTenant(nextTenant);
        setPersona(nextPersona);
        setHistory([]);
        setActive(null);
        setQuestion('');
        setSelectedAsset(null);
        setSelectedJob(null);
        setCatalogDomain('all');
        setWorkflow(useStoredInitial(`nexo-flow-${nextTenant}`, defaultWorkflow(nextTenant)));
        if (apiReady) {
            setApiReady(false);
            const r = await fetch('/api/demo/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tenant: nextTenant, persona: nextPersona }) });
            if (!r.ok) {
                setApiReady(false);
                showToast(t("后端会话切换失败，已明确切换至浏览器演示。"));
            }
            else
                setApiReady(true);
        }
    };
    const submit = async (text = question) => {
        if (!text.trim() || !data || busy)
            return;
        const epoch = scopeRef.current;
        setQuestion('');
        setBusy(true);
        setPage('bi');
        setShowBoards(false);
        try {
            let answer: Analysis;
            if (apiReady) {
                const r = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text, previous: active?.plan, locale }) });
                const body = await r.json();
                if (!r.ok)
                    throw Error(body.detail || t("分析失败"));
                answer = body;
            }
            else {
                await new Promise(r => setTimeout(r, 600));
                answer = analyze(data, tenant, persona, text, active?.plan);
            }
            if (epoch !== scopeRef.current)
                return;
            setActive(answer);
            setHistory(old => [...old, answer]);
            setResultTab('chart');
            setChartType(answer.plan.dimension === 'month' ? 'line' : 'bar');
            record('Analyze', answer.title);
        }
        catch (e: any) {
            if (epoch !== scopeRef.current)
                return;
            showToast(e.message);
            record('Analyze', text, 'Denied');
        }
        finally {
            if (epoch === scopeRef.current)
                setBusy(false);
        }
    };
    const saveAnalysis = () => { if (!active)
        return; if (saved.some(s => s.id === active.id)) {
        showToast(t("这份分析已经在看板中。"));
        return;
    } setSaved(old => [...old, { ...active, tenant, persona } as Analysis]); showToast(t("已保存到当前租户的分析看板。")); record('Save dashboard', active.title); };
    const canExport = policies[`${tenant}:${persona}:export`] ?? current.export;
    const exportRows = async (rows: Row[], name: string) => { if (!canExport) {
        showToast(t("当前角色没有导出权限。"));
        record('Export', name, 'Denied');
        return;
    } if (apiReady) {
        const r = await fetch('/api/authorize/export', { method: 'POST' });
        if (!r.ok) {
            showToast(t("服务器拒绝导出：当前身份没有导出权限。"));
            record('Export', name, 'Denied');
            return;
        }
    } download(name, csv(rows), 'text/csv;charset=utf-8'); record('Export', name); };
    const saveWorkflow = (next = workflow) => { try {
        validateFlow(next);
        const version = next.version + 1;
        const updated = { ...next, version };
        setWorkflow(updated);
        localStorage.setItem(`nexo-flow-${tenant}`, JSON.stringify(updated));
        showToast(t("流程已保存为 v{0}。", [version]));
        record('Save workflow', next.name);
    }
    catch (e: any) {
        showToast(e.message);
    } };
    const runWorkflow = async () => {
        if (!current.execute) {
            showToast(t("当前角色没有数据处理执行权限。可切换“数据工程师”演示身份。"));
            record('Run workflow', workflow.name, 'Denied');
            return;
        }
        try {
            validateFlow(workflow);
            if (apiReady) {
                const r = await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(workflow) });
                const body = await r.json();
                if (!r.ok)
                    throw Error(body.detail || t("任务下发失败"));
                setJobs(old => [body, ...old]);
                setSelectedJob(body);
            }
            else {
                if (workflow.schedule !== 'manual')
                    throw Error(t("浏览器演示不执行后台定时任务，请选择“手动运行”。真实调度需要启动后端与 Temporal。"));
                const job: Job = { id: `RUN-${Date.now().toString(36).toUpperCase()}`, tenant, name: workflow.name, version: workflow.version, status: 'queued', createdAt: new Date().toISOString(), progress: 0, currentNode: workflow.nodes[0].id, nodes: structuredClone(workflow.nodes), logs: [{ time: new Date().toISOString(), message: t("浏览器演示任务已排队；关闭页面后不承诺后台执行。") }], mode: 'browser_demo', workflow: structuredClone(workflow) };
                setJobs(old => [job, ...old]);
                setSelectedJob(job);
            }
            record('Run workflow', workflow.name);
            setPage('jobs');
            showToast(apiReady ? t("处理任务已提交至后端。") : t("已创建浏览器演示任务。"));
        }
        catch (e: any) {
            showToast(e.message);
        }
    };
    useEffect(() => {
        if (!data)
            return;
        const timer = setInterval(() => {
            setJobs(old => old.map(job => {
                if (job.mode !== 'browser_demo' || !['queued', 'running'].includes(job.status))
                    return job;
                const index = Math.min(Math.floor((Date.now() - new Date(job.createdAt).getTime()) / 1600), job.nodes.length);
                if (index >= job.nodes.length) {
                    try {
                        const result = executeDemoFlow(data, job.workflow);
                        const published = { ...job, status: 'completed' as const, progress: 100, endedAt: new Date().toISOString(), currentNode: job.nodes.at(-1)!.id, result, logs: [...job.logs, { time: new Date().toISOString(), message: t("演示处理完成：生成 {0} 行汇总结果；仅保存于本浏览器，未写入 DWS。", [result.length]) }] };
                        localStorage.setItem(`nexo-output-${job.tenant}-${job.workflow.nodes.find(n => n.type === 'publish')?.config.target}`, JSON.stringify(result));
                        return published;
                    }
                    catch (e: any) {
                        return { ...job, status: 'failed' as const, error: e.message, endedAt: new Date().toISOString(), logs: [...job.logs, { time: new Date().toISOString(), message: e.message }] };
                    }
                }
                const progress = Math.min(95, Math.round(index / job.nodes.length * 100));
                if (progress === job.progress && job.status === 'running')
                    return job;
                return { ...job, status: 'running' as const, progress, currentNode: job.nodes[index].id, logs: [...job.logs, { time: new Date().toISOString(), message: t("执行节点：{0}（演示）", [t(job.nodes[index].label)]) }] };
            }));
        }, 700);
        return () => clearInterval(timer);
    }, [data]);
    useEffect(() => { if (!apiReady || !jobs.some(j => j.mode !== 'browser_demo' && ['queued', 'running'].includes(j.status)))
        return; const timer = setInterval(async () => { try {
        const r = await fetch('/api/jobs');
        if (r.ok) {
            const all: Job[] = await r.json();
            setJobs(old => [...all, ...old.filter(j => j.mode === 'browser_demo')]);
        }
    }
    catch { } }, 1500); return () => clearInterval(timer); }, [apiReady, jobs]);
    const cancelJob = async (job: Job) => { if (!current.execute) {
        showToast(t("当前角色没有取消任务的权限。"));
        return;
    } if (job.mode !== 'browser_demo') {
        const r = await fetch(`/api/jobs/${job.id}/cancel`, { method: 'POST' });
        if (!r.ok) {
            showToast(t("任务取消失败。"));
            return;
        }
    } setJobs(old => old.map(j => j.id === job.id ? { ...j, status: 'cancelled', endedAt: new Date().toISOString(), logs: [...j.logs, { time: new Date().toISOString(), message: t("用户请求取消任务。") }] } : j)); record('Cancel job', job.id); showToast(t("已提交取消请求。")); };
    useEffect(() => { if (!apiReady)
        return; const epoch = scopeRef.current; fetch('/api/catalog').then(r => r.ok ? r.json() : Promise.reject()).then(rows => { if (epoch === scopeRef.current && Array.isArray(rows))
        setRegisteredAssets(rows); }).catch(() => { }); }, [apiReady, tenant, persona]);
    const ctx = useMemo(() => data ? overview(data, tenant, persona, month) : null, [data, tenant, persona, month]);
    const available: Row[] = registeredAssets ? registeredAssets.map((r): Row => ({ ...assets.find(a => a.name === r.name), ...r, _fromOM: true })).filter(a => a.label) : visibleAssets(persona);
    const scopedJobs = jobs.filter(j => j.tenant === tenant && !current.region);
    const running = scopedJobs.filter(j => ['running', 'queued'].includes(j.status)).length;
    const displayedJob = selectedJob ? jobs.find(j => j.id === selectedJob.id) || selectedJob : null;
    const boards = saved.filter((s: any) => s.tenant === tenant && s.persona === persona);
    const filteredAssets = available.filter(a => (catalogDomain === 'all' || a.domain === catalogDomain) && (catalogSource === 'all' || a.source === catalogSource) && (`${a.name} ${t(a.label)} ${a.desc}`.toLowerCase().includes(search.toLowerCase())));
    if (!data || !ctx)
        return <div className="boot"><div className="brand-mark">{t("N")}</div>{loadError ? <><h2>{t("数据未能加载")}</h2><p>{t(loadError)}</p><button onClick={() => location.reload()}>{t("重新加载")}</button></> : <><Loader2 className="spin"/><p>{t("正在准备你的数据工作空间…")}</p></>}</div>;
    return <div className="app-shell">
  <aside className="sidebar">
   <a className="brand" aria-label={t("NEXO 首页")} href="#" onClick={e => { e.preventDefault(); setPage('bi'); }}><span className="brand-mark"><Network size={25}/></span><span>{t("NEXO")}<span className="brand-caption">{t("DATA AGENT")}</span></span></a>
   <div className="workspace-label"><span className="workspace-avatar">{t(tenant === 'luma' ? 'LC' : 'NR')}</span><div><strong>{t(tenant === 'luma' ? 'Luma Commerce' : 'Northstar Retail')}</strong><small>{t("Commerce workspace")}</small></div></div>
   <p className="nav-label">{t("工作空间")}</p>
   <nav>{nav.slice(0, 4).map(n => <button className={`nav-item ${page === n.id ? 'active' : ''}`} key={n.id} aria-label={t(n.label)} title={t(n.label)} aria-current={page === n.id ? 'page' : undefined} onClick={() => { setPage(n.id as Page); setSearch(''); }}><n.icon size={18}/><span>{t(n.label)}</span>{n.id === 'bi' ? <span className="nav-new">{t("AI")}</span> : n.id === 'jobs' && running > 0 ? <span className="nav-count">{running}</span> : null}{page === n.id && <i />}</button>)}</nav>
   <p className="nav-label governance-label">{t("管理与治理")}</p>
   <nav>{nav.slice(4).map(n => <button className={`nav-item ${page === n.id ? 'active' : ''}`} key={n.id} aria-label={t(n.label)} title={t(n.label)} aria-current={page === n.id ? 'page' : undefined} onClick={() => setPage(n.id as Page)}><n.icon size={18}/><span>{t(n.label)}</span>{page === n.id && <i />}</button>)}</nav>
   <div className="sidebar-bottom"><div className="sandbox-card"><span className="sandbox-icon"><Sparkles size={17}/></span><strong>{t("探索你的数据可能")}</strong><p>{t("从业务问题出发，")}<br />{t("连接数据与行动。")}</p><button onClick={() => setModal('guide')}>{t("快速上手 ")}<ArrowUpRight size={14}/></button></div><button className="sidebar-help" onClick={() => setModal('guide')}><HelpCircle size={17}/><span>{t("使用指南")}</span><ArrowUpRight size={14}/></button><div className="sidebar-user"><span className="avatar">{t(current.initials)}</span><div><strong>{t(current.en)}</strong><small>{t(current.name)}</small></div><button aria-label={t("身份设置")} onClick={() => setModal('identity')}><Settings2 size={16}/></button></div></div>
  </aside>
  <div className="workspace-main">
   <header className="topbar"><div className="breadcrumb"><span>{t("工作空间")}</span><ChevronRight size={13}/><strong>{t(nav.find(n => n.id === page)?.label)}</strong></div><div className="top-actions"><span className="demo-label"><span />{t("合成数据演示")}</span><button className="icon-button" aria-label={t("搜索资产")} onClick={() => { setPage('catalog'); setTimeout(() => document.getElementById('asset-search')?.focus(), 30); }}><Search size={17}/></button><span className="top-divider"/><select aria-label={t("切换租户")} value={tenant} onChange={e => switchScope(e.target.value, persona)}><option value="luma">{t("Luma Commerce")}</option><option value="northstar">{t("Northstar Retail")}</option></select><button className="identity-button" onClick={() => setModal('identity')}><span className="avatar small">{t(current.initials)}</span><span>{t(current.name)}</span><ChevronDown size={13}/></button><LanguageSwitcher/></div></header>
   <main className={`page-content page-${page}`}>
    {page === 'bi' && <>
     <section className="page-heading bi-heading"><div><div className="eyebrow"><span />{t(" YOUR DATA, IN CONTEXT")}</div><h1>{t("从洞察，到行动")}<span className="heading-dot">{t(".")}</span></h1><p>{t("探索业务数据，让每一个问题都有清晰的下一步。")}</p></div><button className={`button secondary ${showBoards ? 'selected' : ''}`} onClick={() => setShowBoards(!showBoards)}><LayoutDashboard size={16}/>{t("我的看板 ")}<span className="count-light">{boards.length}</span></button></section>
     <div className="bi-layout"><div className="bi-main">
      {showBoards ? <section className="panel"><div className="panel-head"><h3>{t("我的分析看板")}</h3><span className="muted">{t("当前租户 · 当前演示身份")}</span></div>{boards.length ? boards.map(b => <button className="saved-item" key={b.id} onClick={() => { setActive(b); setShowBoards(false); setResultTab('chart'); }}><span className="square-icon success"><BarChart3 size={18}/></span><div><strong>{t(b.title)}</strong><small>{t(new Date(b.createdAt).toLocaleString(getLocale()))}{t(" · ")}{t(b.sources.join(', '))}</small></div><ArrowUpRight size={17}/><span className="delete-saved" role="button" tabIndex={0} aria-label={t("删除看板")} onClick={e => { e.stopPropagation(); setSaved(old => old.filter(s => s.id !== b.id)); }} onKeyDown={e => { if (e.key === 'Enter') {
                e.stopPropagation();
                setSaved(old => old.filter(s => s.id !== b.id));
            } }}><Trash2 size={14}/></span></button>) : <Empty title={t("把有价值的分析留在这里")} description={t("完成一次问数后，点击“保存到看板”，随时继续探索。")}><button className="button primary" onClick={() => { setShowBoards(false); submit(t("分析 10 月各地区销售额")); }}>{t("开始第一次分析 ")}<ArrowRight size={15}/></button></Empty>}</section> : <>
      <div className="section-label"><h2>{t(active ? t("分析结果") : t("业务表现概览"))}</h2><div><span className="currency-label">{t("USD")}</span><select aria-label={t("分析时间范围")} value={month} onChange={e => { setMonth(e.target.value); setActive(null); }}><option value="2026-10">{t("2026 年 10 月")}</option><option value="2026-09">{t("2026 年 9 月")}</option><option value="all">{t("全部时间")}</option></select></div></div>
      <div className="metrics-grid">{[{ label: t("净销售额"), value: money(ctx.revenue), note: t("排除已取消订单"), icon: Activity, values: ctx.monthly.map(d => d.value) }, { label: t("有效订单"), value: number(ctx.count), note: t("按订单粒度去重统计"), icon: FileCheck2, values: ctx.sparkCount }, { label: t("平均客单价"), value: money(ctx.aov), note: t("净销售额 / 有效订单"), icon: BarChart3, values: ctx.sparkAov }, { label: t("商品毛利率"), value: ctx.margin.toFixed(1) + '%', note: t("未扣物流与广告费用"), icon: Layers3, values: ctx.sparkMargin }].map(m => <article className="metric-card" key={m.label}><div className="metric-label">{t(m.label)}<m.icon size={15}/></div><div className="metric-value">{t(m.value)}<Sparkline values={m.values}/></div><small>{t(m.note)}</small></article>)}</div>
      {active ? <section className="panel analysis-panel"><div className="panel-head"><div><div className="mini-eyebrow">{t("ANALYSIS RESULT")}</div><h3>{t(active.title)}</h3></div><div className="inline-actions"><button className="icon-button" title={t("导出结果")} aria-label={t("导出分析结果")} onClick={() => exportRows(active.data, 'analysis.csv')}><Download size={16}/></button><button className="button small secondary" onClick={saveAnalysis}><Plus size={14}/>{t("保存到看板")}</button></div></div><div className="result-tabs">{[['chart', t("可视化")], ['table', t("结果数据")], ['plan', t("查询计划")], ['sql', 'SQL']].map(([key, label]) => <button key={key} onClick={() => setResultTab(key)} className={resultTab === key ? 'active' : ''}>{t(label)}</button>)}<span className="result-mode">{t(active.mode === 'browser_demo' ? t("浏览器聚合") : active.mode === 'demo_rules' ? t("openJiuwen · 规则演示") : 'openJiuwen · GLM5.3')}</span></div>
       {resultTab === 'chart' ? <><div className="chart-toolbar"><span>{active.data.length}{t(" 个结果 · ")}{t(personas[persona].region || t("授权地区"))}</span><div className="segmented">{['bar', 'line', 'pie'].map(localT => <button key={localT} title={localT === 'bar' ? t("柱状图") : localT === 'line' ? t("折线图") : t("环形图")} className={chartType === localT ? 'active' : ''} onClick={() => setChartType(localT)}>{localT === 'bar' ? <BarChart3 size={14}/> : localT === 'line' ? <Activity size={14}/> : <span className="donut-icon"/>}</button>)}</div></div><Chart data={active.data} type={chartType} height={270} valueType={active.metric === 'roas' ? 'ratio' : active.metric === 'pricing' ? 'percent' : ['orders', 'stock', 'sentiment'].includes(active.metric) ? 'number' : 'money'} onSelect={name => { if (['Mexico City', 'North', 'South', 'Pacific', 'Central'].includes(name))
                    submit(t("只看 {0}，按品类分析销售额", [name])); }}/><div className="insight-strip"><Sparkles size={16}/><p>{t(active.summary)}</p></div></> : resultTab === 'table' ? <Table rows={active.data} limit={30}/> : resultTab === 'sql' ? <div className="sql-view"><div className="sql-caption"><span>{t("参数化执行计划 · 浏览器演示中 SQL 仅供查看")}</span><button onClick={() => { navigator.clipboard?.writeText(active.sql); showToast(t("SQL 已复制。")); }}><Copy size={14}/>{t("复制")}</button></div><pre>{active.sql}</pre><div className="sql-params"><span>{t("tenant_id = ")}{tenant}</span>{current.region && <span>{t("allowed_region = ")}{t(current.region)}</span>}<span>{t("currency = USD")}</span></div></div> : <div className="plan-list">{active.steps.map((s, i) => <div key={s}><span>{i + 1}</span><div><strong>{t(s)}</strong><small>{t(i === 1 ? active.sources.join(' · ') : i === 3 ? `${t(current.name)} · ${current.region || t("授权地区")}` : t("已完成"))}</small></div><CheckCircle2 size={17}/></div>)}</div>}
       <div className="panel-foot"><span><Database size={13}/>{active.sources.join(' · ')}</span><button onClick={() => { setWorkflow({ ...defaultWorkflow(tenant), name: active.title + t("处理流程"), nodes: defaultWorkflow(tenant).nodes.map(n => n.type === 'aggregate' ? { ...n, config: { dimension: active.plan.dimension, metric: active.plan.metric } } : n) }); setPage('flows'); showToast(t("已创建流程草稿，执行前可调整节点与输出。")); }}><GitBranch size={14}/>{t("转为处理流程 ")}<ArrowRight size={13}/></button></div></section> : <>
      <section className="panel trend-panel"><div className="panel-head"><div><h3>{t("销售额趋势")}</h3><p>{t("Apr – Oct 2026 · 净销售额")}</p></div><Badge tone="success">{t("统一业务口径")}</Badge></div><Chart data={ctx.monthly.map(d => ({ ...d, name: new Date(d.name + '-02').toLocaleDateString('en-US', { month: 'short' }) }))} type="line" height={245}/><div className="chart-footnote"><span className="legend-dot"/>{t("Net revenue ")}<span className="muted">{t("· 含当前租户授权地区")}</span><button onClick={() => submit(t("分析所有月份的销售额趋势"))}>{t("探索趋势 ")}<ArrowUpRight size={13}/></button></div></section>
      <div className="two-col"><section className="panel"><div className="panel-head compact"><h3>{t("品类贡献")}</h3><button className="icon-button" aria-label={t("探索品类")} onClick={() => submit(t("10 月按品类分析销售额"))}><ArrowUpRight size={17}/></button></div><Chart data={ctx.categories} horizontal height={235}/></section><section className="panel region-panel"><div className="panel-head compact"><h3>{t("地区表现")}</h3><span className="muted">{ctx.regions.length}{t(" 个地区")}</span></div><div className="region-list">{ctx.regions.map((r, i) => <button key={r.name} onClick={() => submit(t("只看 {0}，按品类分析销售额", [r.name]))}><span className="region-index">{t("0")}{i + 1}</span><div><strong>{t(r.name)}</strong><div className="region-track"><i style={{ width: `${r.value / (ctx.regions[0]?.value || 1) * 100}%` }}/></div></div><span>{t(money(r.value, true))}<ArrowUpRight size={12}/></span></button>)}</div></section></div>
      </>}
      <div className="section-label scenario-label"><h2>{t("从一个问题开始")}</h2><span>{t("探索更多业务场景")}</span></div><div className="prompt-cards">{prompts.map(p => <button key={p.title} onClick={() => submit(p.text)}><span className={`square-icon ${p.color}`}><p.icon size={19}/></span><strong>{t(p.title)}</strong><small>{t(p.description)}</small><ArrowUpRight size={16}/></button>)}</div>
      <div className="data-note"><ShieldCheck size={13}/><span>{t("全部为虚构英文数据 · 当前租户 ")}{t(tenant === 'luma' ? 'Luma Commerce' : 'Northstar Retail')}{t(" · ")}{t(current.region ? t("仅 {0}", [current.region]) : t("按角色授权范围显示"))}{t(" · ")}{t(apiReady ? t("服务端执行模式") : t("浏览器交互演示，非生产权限隔离"))}</span></div>
      </>}
     </div><aside className="agent-panel"><div className="agent-panel-head"><span className="agent-glyph"><Sparkles size={19}/></span><div><strong>{t("NEXO Agent")}</strong><small><span />{t(apiReady && health?.model_connected ? t("GLM5.3 已配置") : t("规则演示 · GLM5.3 待连接"))}</small></div><button className="icon-button" aria-label={t("新建对话")} onClick={() => { scopeRef.current++; setHistory([]); setActive(null); setBusy(false); showToast(t("已开启新的分析对话。")); }}><Plus size={17}/></button></div><div className="agent-messages"><div className="agent-welcome"><span className="tiny-label">{t("YOUR ANALYTICAL PARTNER")}</span><h3>{t("今天，想了解什么？")}</h3><p>{t("告诉我你的业务问题。我会结合数据目录和指标口径，帮助你探索、分析，并规划下一步。")}</p><div className="context-tags"><span><Database size={12}/>{available.length}{t(" 个可见资产")}</span><span><ShieldCheck size={12}/>{t(current.region || t("授权业务域"))}</span></div></div>{history.length === 0 ? <div className="agent-starters"><p>{t("你可以试着问")}</p>{[t("10 月哪个地区销售额最高？"), t("按品类进一步拆解销售额"), t("分析广告投放的 ROAS")].map(q => <button key={q} onClick={() => submit(q)}>{t(q)}<ArrowUpRight size={13}/></button>)}</div> : history.map(a => <div className="chat-pair" key={a.id}><div className="user-message">{t(a.question)}</div><div className="agent-answer"><span className="answer-icon"><Sparkles size={13}/></span><div><strong>{t(a.title)}</strong><p>{t(a.summary)}</p><button onClick={() => { setActive(a); setResultTab('chart'); }}>{t("查看分析结果 ")}<ArrowUpRight size={13}/></button></div></div></div>)}{busy && <div className="thinking"><Loader2 size={15} className="spin"/>{t("正在检索上下文并生成分析…")}</div>}</div><div className="agent-compose"><div className="compose-context"><span><LockKeyhole size={11}/>{t(current.name)}</span><button onClick={() => { setPage('catalog'); showToast(t("可在数据目录中选择资产并发起分析。")); }}><Plus size={12}/>{t("引用资产")}</button></div><textarea aria-label={t("向 Agent 提问")} value={question} onChange={e => setQuestion(e.target.value)} placeholder={t("用自然语言探索你的数据…")} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
        } }}/><div className="compose-bottom"><button onClick={() => setPage('connections')}><Sparkles size={12}/>{t(draftModel.model)}<ChevronDown size={12}/></button><button className="send-button" aria-label={t("发送问题")} disabled={!question.trim() || busy} onClick={() => submit()}>{busy ? <Loader2 size={15} className="spin"/> : <ArrowUpRight size={18}/>}</button></div><small>{t("Enter 发送 · Shift + Enter 换行")}</small></div></aside></div>
    </>}

    {page === 'catalog' && <><PageHeading eyebrow={t("KNOW YOUR DATA")} title={t("数据目录")} description={t("在统一业务上下文中发现、理解和复用数据资产。")} action={<a className="button secondary" href="/downloads/commerce-data-10000.zip"><Download size={15}/>{t("下载合成数据")}</a>}/><div className="catalog-stats"><div><Database size={19}/><strong>{available.length}</strong><span>{t("可见数据资产")}</span></div><div><Layers3 size={19}/><strong>{current.domains.length}</strong><span>{t("授权业务域")}</span></div><div><Globe2 size={19}/><strong>{available.filter(a => a.source === 'External').length}</strong><span>{t("外部场景数据集")}</span></div><div><ShieldCheck size={19}/><strong>{t("100%")}</strong><span>{t("合成数据 · English")}</span></div></div><div className="catalog-layout"><aside className="catalog-tree"><h4>{t("业务目录 ")}<Folder size={14}/></h4><button className={catalogDomain === 'all' ? 'active' : ''} onClick={() => setCatalogDomain('all')}><Layers3 size={15}/>{t("全部可见资产 ")}<span>{available.length}</span></button>{Object.entries(domainNames).filter(([k]) => k !== 'Platform').map(([key, label]) => <div className="tree-group" key={key}><button disabled={!current.domains.includes(key)} onClick={() => setCatalogDomain(catalogDomain === key ? 'all' : key)} className={catalogDomain === key ? 'active' : ''}>{catalogDomain === key ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}<span className="domain-dot" style={{ background: domainColors[key] }}/>{t(label)}{current.domains.includes(key) ? <span>{available.filter(a => a.domain === key).length}</span> : <LockKeyhole size={12}/>}</button>{catalogDomain === key && available.filter(a => a.domain === key).map(a => <button className="tree-asset" key={a.name} onClick={() => { setSelectedAsset(a); setAssetTab('columns'); }}><Table2 size={13}/>{a.name}</button>)}</div>)}<div className="tree-note"><BookOpen size={15}/><p>{t("物理位置可以不同，")}<br />{t("业务上下文始终一致。")}</p></div></aside><section className="panel catalog-panel"><div className="catalog-toolbar"><div className="search-box"><Search size={16}/><input id="asset-search" placeholder={t("搜索资产、字段或业务含义…")} value={search} onChange={e => setSearch(e.target.value)}/>{search && <button aria-label={t("清除搜索")} onClick={() => setSearch('')}><X size={13}/></button>}</div><select aria-label={t("数据来源筛选")} value={catalogSource} onChange={e => setCatalogSource(e.target.value)}><option value="all">{t("全部来源")}</option><option value="Internal">{t("内部数据")}</option><option value="External">{t("外部场景")}</option></select></div><table className="asset-table"><thead><tr><th>{t("资产名称")}</th><th>{t("业务域")}</th><th>{t("记录数")}</th><th>{t("质量")}</th><th>{t("负责人")}</th><th /></tr></thead><tbody>{filteredAssets.map(a => <tr key={a.name} onClick={() => { setSelectedAsset(a); setAssetTab('columns'); }} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter')
        setSelectedAsset(a); }}><td><span className={`asset-icon ${a.source === 'External' ? 'external' : ''}`}>{a.source === 'External' ? <Globe2 size={18}/> : <Table2 size={18}/>}</span><span><strong>{a.name}</strong><small>{t(a.label)}{t(" · ")}{t(a.source === 'External' ? 'External scenario' : 'Internal commerce')}</small></span></td><td><span className="domain-tag" style={{ color: domainColors[a.domain] }}>{t(domainNames[a.domain])}</span></td><td>{t(number(scopedRows(data, a.name, tenant, persona).length))}</td><td><span className={`quality ${a.quality === 100 ? 'good' : 'warn'}`}><i />{a.quality}{t("%")}</span></td><td>{a.owner}</td><td><ChevronRight size={15}/></td></tr>)}</tbody></table>{!filteredAssets.length && <Empty title={t("没有找到匹配资产")} description={t("尝试其他关键词，或调整业务域和来源筛选。")}/>}<div className="panel-foot"><span>{filteredAssets.length}{t(" 个可见资产 · ")}{t(registeredAssets ? t("OpenMetadata 实时目录") : t("合成数据目录镜像"))}</span><button onClick={() => setPage('connections')}>{t("OpenMetadata 接入状态 ")}<ArrowUpRight size={13}/></button></div></section></div></>}

    {page === 'flows' && <><PageHeading eyebrow={t("DESIGN THE NEXT STEP")} title={t("流程编排")} description={t("用自然语言定义处理过程，让每一步都可见、可改、可追踪。")} action={<div className="inline-actions"><button className="button secondary" onClick={() => saveWorkflow()}><Check size={15}/>{t("保存 v")}{workflow.version}</button><button className="button primary" onClick={runWorkflow}><Play size={15}/>{t("下发任务")}</button></div>}/><FlowEditor flow={workflow} onChange={setWorkflow} onNotify={showToast}/><div className="flow-bottom-grid"><section className="panel"><div className="panel-head compact"><h3>{t("让 Agent 帮你定义过程")}</h3><Sparkles size={17}/></div><FlowPrompt onApply={text => { const f = defaultWorkflow(tenant); f.name = /库存|stock/i.test(normalizeQuestion(text)) ? t("库存质量检查流程") : t("地区销售汇总流程"); if (/品类|category/i.test(normalizeQuestion(text))) {
        f.nodes = f.nodes.map(n => n.type === 'aggregate' ? { ...n, label: t("按品类汇总"), config: { ...n.config, dimension: 'category' } } : n);
    } if (/9月|九月|september/i.test(normalizeQuestion(text)))
        f.nodes = f.nodes.map(n => n.type === 'source' ? { ...n, config: { ...n.config, range: '2026-09' } } : n); if (/库存|stock/i.test(normalizeQuestion(text))) {
        showToast(t("首版流程模板支持订单处理。库存场景可在 ChatBI 中分析，尚未生成库存执行流程。"));
        return;
    } setWorkflow(f); showToast(t("已根据模板规则生成流程草稿，尚未调用模型。")); }}/></section><section className="panel execution-settings"><div className="panel-head compact"><h3>{t("执行设置")}</h3><Clock3 size={17}/></div><label>{t("触发方式")}<select value={workflow.schedule} onChange={e => setWorkflow({ ...workflow, schedule: e.target.value })}><option value="manual">{t("手动运行")}</option><option value="daily">{t("每天 08:00（需后端调度）")}</option></select></label><label>{t("执行时区")}<span>{t("America/Mexico_City")}</span></label><label>{t("输出策略")}<span>{t("按时间分区替换 · 幂等写入")}</span></label><p><ShieldCheck size={13}/>{t(current.execute ? t("当前角色允许执行，后端仍会逐节点校验。") : t("当前角色可编辑草稿；执行需数据工程师权限。"))}</p><button onClick={() => download('workflow.json', JSON.stringify(workflow, null, 2), 'application/json')}>{t("导出流程定义 ")}<ArrowDownToLine size={13}/></button></section></div></>}

    {page === 'jobs' && <><PageHeading eyebrow={t("FROM PLAN TO DELIVERY")} title={t("任务中心")} description={t("跟踪处理过程、检查运行结果，保持每一次交付可追溯。")} action={<button className="button primary" onClick={() => setPage('flows')}><Plus size={15}/>{t("创建处理任务")}</button>}/><div className="job-stats">{[[t("全部任务"), scopedJobs.length, Layers3], [t("运行中"), running, Activity], [t("已完成"), scopedJobs.filter(j => j.status === 'completed').length, CheckCheck], [t("失败 / 取消"), scopedJobs.filter(j => ['failed', 'cancelled'].includes(j.status)).length, History]].map(([label, count, Icon]: any) => <div className="panel" key={label}><span><Icon size={18}/>{label}</span><strong>{count}</strong></div>)}</div><section className="panel"><div className="jobs-toolbar"><div className="tabs">{[['all', t("全部")], ['running', t("进行中")], ['completed', t("已完成")], ['failed', t("异常")]].map(([key, label]) => <button className={jobFilter === key ? 'active' : ''} key={key} onClick={() => setJobFilter(key)}>{t(label)}</button>)}</div><span className="muted">{t(apiReady ? t("后端任务状态自动刷新") : t("浏览器演示 · 非后台调度"))}</span></div>{scopedJobs.length ? <table className="jobs-table"><thead><tr><th>{t("任务 / 运行 ID")}</th><th>{t("状态")}</th><th>{t("进度")}</th><th>{t("流程版本")}</th><th>{t("提交时间")}</th><th /></tr></thead><tbody>{scopedJobs.filter(j => jobFilter === 'all' || jobFilter === 'running' && ['running', 'queued'].includes(j.status) || jobFilter === 'completed' && j.status === 'completed' || jobFilter === 'failed' && ['failed', 'cancelled'].includes(j.status)).map(j => <tr key={j.id} onClick={() => setSelectedJob(j)}><td><strong>{t(j.name)}</strong><small>{t(j.id)}</small></td><td><Badge tone={j.status === 'completed' ? 'success' : j.status === 'failed' ? 'red' : j.status === 'running' ? 'blue' : 'neutral'}>{t(statusLabels[j.status])}</Badge></td><td><div className="job-progress"><span><i style={{ width: j.progress + '%' }}/></span><small>{j.progress}{t("%")}</small></div></td><td>{t("v")}{j.version}</td><td>{t(time(j.createdAt))}</td><td><ChevronRight size={15}/></td></tr>)}</tbody></table> : <Empty title={t("你的下一次数据交付，从这里开始")} description={t("在流程编排中定义处理过程，下发后即可查看每个节点的运行状态。")}><button className="button secondary" onClick={() => setPage('flows')}>{t("打开流程编排 ")}<ArrowRight size={15}/></button></Empty>}</section><div className="info-strip"><Clock3 size={17}/><p>{t("每次执行绑定一个确定的流程版本。真实环境中由 Temporal 管理持久化调度，浏览器演示只在页面打开时推进任务。")}</p></div></>}

    {page === 'governance' && <><PageHeading eyebrow={t("TRUST AT EVERY STEP")} title={t("分权分域")} description={t("以业务域组织资产，以明确的权限连接人员、数据和行动。")} action={<button className="button secondary" onClick={() => setModal('identity')}><Users size={15}/>{t("切换演示身份")}</button>}/><div className="governance-context"><span className="square-icon success"><ShieldCheck size={21}/></span><div><strong>{t(current.en)}{t(" · ")}{t(current.name)}</strong><p>{t("当前租户：")}{t(tenant === 'luma' ? 'Luma Commerce' : 'Northstar Retail')}{t(" · 地区范围：")}{t(current.region || t("已授权地区"))}{t(" · ")}{t(current.govern ? t("可管理销售域演示策略") : t("管理权限与数据访问权分别授予"))}</p></div><Badge tone="success">{t("已应用演示范围")}</Badge></div><div className="domain-cards">{Object.entries(domainNames).filter(([k]) => k !== 'Platform').map(([key, label]) => <button className={`domain-card ${activeDomain === key ? 'selected' : ''}`} onClick={() => setActiveDomain(key)} key={key}><span style={{ background: domainColors[key] + '15', color: domainColors[key] }}><Layers3 size={20}/></span><div><strong>{t(label)}</strong><small>{t(key)}</small></div>{current.domains.includes(key) ? <Badge tone="success">{t("已授权")}</Badge> : <LockKeyhole size={16}/>}</button>)}</div><section className="panel"><div className="panel-head"><div><h3>{t(domainNames[activeDomain])}{t(" · 权限矩阵")}</h3><p>{t("发现、查询、导出与执行是不同的权限。")}</p></div><button className="button small secondary" disabled={!current.govern || activeDomain !== 'Sales'} onClick={() => setModal('policy')}><Settings2 size={14}/>{t("配置演示策略")}</button></div><table className="permission-table"><thead><tr><th>{t("角色")}</th><th>{t("目录发现")}</th><th>{t("查询分析")}</th><th>{t("数据导出")}</th><th>{t("处理执行")}</th><th>{t("域治理")}</th><th>{t("数据范围")}</th></tr></thead><tbody>{Object.entries(personas).map(([key, p]) => { const access = p.domains.includes(activeDomain); return <tr className={key === persona ? 'current-role' : ''} key={key}><td><span className="avatar tiny">{t(p.initials)}</span><strong>{t(p.name)}</strong>{key === persona && <span className="you-tag">{t("当前")}</span>}</td>{[access, access, access && (policies[`${tenant}:${key}:export`] ?? p.export), access && p.execute, activeDomain === 'Sales' && p.govern].map((yes, i) => <td key={i}>{yes ? <CheckCircle2 size={17} className="allowed"/> : <span className="denied">{t("—")}</span>}</td>)}<td>{t(access ? p.region || t("授权域内全部地区") : t("未授权"))}</td></tr>; })}</tbody></table><div className="panel-foot"><span><LockKeyhole size={13}/>{t("客户联系方式对非工程师身份脱敏；浏览器数据为合成样本。")}</span></div></section><section className="panel audit-panel"><div className="panel-head compact"><h3>{t("操作审计")}</h3><Badge>{t("演示记录")}</Badge></div>{audit.filter(a => a.tenant === tenant).length ? <table><thead><tr><th>{t("时间")}</th><th>{t("操作人")}</th><th>{t("操作")}</th><th>{t("目标")}</th><th>{t("结果")}</th></tr></thead><tbody>{audit.filter(a => a.tenant === tenant).slice(0, 8).map(a => <tr key={a.id}><td>{t(time(a.at))}</td><td>{a.actor}</td><td>{t(a.action)}</td><td>{t(a.target)}</td><td><Badge tone={a.outcome === 'Allowed' ? 'success' : 'red'}>{t(a.outcome === 'Allowed' ? t("允许") : t("拒绝"))}</Badge></td></tr>)}</tbody></table> : <Empty title={t("操作会留下清晰的记录")} description={t("发起分析、导出数据或下发任务后，可在这里查看演示审计记录。")}/>}</section></>}

    {page === 'connections' && <><PageHeading eyebrow={t("CONNECTED BY DESIGN")} title={t("连接与模型")} description={t("统一接入数据与智能能力，清楚呈现每一个组件的真实状态。")} action={<button className="button secondary" onClick={() => { fetch('/api/health').then(r => r.json()).then(h => { if (h.service === 'nexo-api') {
            setHealth(h);
            showToast(t("已刷新后端连接状态。"));
        }
        else
            showToast(t("当前为浏览器演示，后端未连接。")); }).catch(() => showToast(t("当前为浏览器演示，后端未连接。"))); }}><RefreshCw size={15}/>{t("刷新状态")}</button>}/><section className="connection-banner"><div className="square-icon gold"><Globe2 size={23}/></div><div><strong>{t("目标部署区域：LA-Mexico City2")}</strong><p>{t(health?.deployment === 'huawei_cloud' ? t("la-north-2 · 云端应用已部署，DWS 通过私网访问。全部业务数据均为合成样本。") : t("la-north-2 · 此页面尚未连接墨西哥云端后端。"))}</p></div><Badge tone={health?.deployment === 'huawei_cloud' ? 'success' : 'gold'}>{t(health?.deployment === 'huawei_cloud' ? t("云端已部署") : t("等待云端连接"))}</Badge></section><div className="section-label"><h2>{t("模型服务")}</h2><span>{t("供应商、地址与模型 ID 可独立配置")}</span></div><section className="panel model-panel"><span className="model-logo">{t("GLM")}</span><div><div className="model-title"><h3>{t(draftModel.model)}</h3><Badge tone={health?.model_connected ? 'success' : 'gold'}>{t(health?.model_connected ? t("已配置") : t("待配置凭据"))}</Badge></div><p>{t(draftModel.provider)}{t(" · OpenAI-compatible API")}</p><small>{t(draftModel.baseUrl || t("API 地址由后端环境配置；没有在浏览器保存密钥。"))}</small></div><button className="button secondary" onClick={() => setModal('model')}><Settings2 size={15}/>{t("配置模型")}</button></section><div className="section-label"><h2>{t("数据与平台组件")}</h2><span>{t("演示状态与真实服务状态分开展示")}</span></div><div className="integration-grid">{[
                { name: 'Huawei Cloud DWS', type: t("数据执行"), icon: Database, status: health?.dws_connected ? t("已连接") : t("未连接"), desc: health?.dws_connected ? t("经 MCP 在 DWS 中执行受控查询，使用 10,000 条合成样本。") : t("通过 MCP 访问 DWS；浏览器模式使用合成数据镜像。"), tone: health?.dws_connected ? 'success' : 'gold' },
                { name: 'openJiuwen', type: t("Agent 框架"), icon: Network, status: health?.openjiuwen ? t("已运行") : t("源码已提供"), desc: t("规划与执行代码包含真实 openJiuwen Workflow 和 MCP 客户端。"), tone: health?.openjiuwen ? 'success' : 'neutral' },
                { name: 'OpenMetadata', type: t("统一目录"), icon: BookOpen, status: health?.openmetadata ? t("已连接") : t("待接入"), desc: health?.openmetadata ? t("开源资产目录已连接，资产发现受服务端业务域权限约束。") : t("开源资产目录；浏览器模式使用目录镜像。"), tone: health?.openmetadata ? 'success' : 'neutral' },
                { name: 'Temporal', type: t("持久化任务"), icon: Clock3, status: health?.temporal ? t("已连接") : t("待接入"), desc: t("负责后台调度与重试；浏览器演示不执行真实定时任务。"), tone: health?.temporal ? 'success' : 'neutral' },
                { name: t("Iceberg 历史表"), type: t("历史与湖表目录"), icon: Layers3, status: health?.iceberg ? t("历史表可用") : t("待接入"), desc: t("Iceberg 保存元数据历史快照；当前使用单机目录，Polaris 服务待接入。"), tone: 'neutral' },
                { name: 'Keycloak / OPA', type: t("身份与权限"), icon: ShieldCheck, status: t("待生产集成"), desc: t("当前提供显式演示身份与服务端范围校验，不等同完整 IAM。"), tone: 'neutral' },
            ].map(c => <section className="panel integration-card" key={c.name}><div className="integration-card-head"><span className="square-icon neutral"><c.icon size={21}/></span><Badge tone={c.tone}>{t(c.status)}</Badge></div><h3>{t(c.name)}</h3><span className="mini-eyebrow">{t(c.type)}</span><p>{t(c.desc)}</p></section>)}</div><div className="download-panel"><div><strong>{t("把 demo 带到你的环境")}</strong><p>{t("源码、后端启动配置、10,000 条英文数据与接入说明。")}</p></div><a className="button secondary" href="/downloads/nexo-demo-source.zip"><Download size={15}/>{t("下载源码")}</a><a className="button primary" href="/downloads/commerce-data-10000.zip"><Download size={15}/>{t("下载数据集")}</a></div></>}
   </main>
   <footer className="app-footer"><span><span className="footer-dot"/>{t(apiReady ? (health?.deployment === 'huawei_cloud' ? t("云端后端已连接") : t("本地后端已连接")) : 'INTERACTIVE DEMO')}<i />{t("NEXO Data Agent")}</span><span>{t("10,000 synthetic records · English data · v0.1")}</span></footer>
  </div>

  {selectedAsset && <div className="drawer-overlay" onClick={() => setSelectedAsset(null)}><aside className="detail-drawer" onClick={e => e.stopPropagation()}><div className="drawer-top"><span className="mini-eyebrow">{t("DATA ASSET")}</span><button className="icon-button" aria-label={t("关闭资产详情")} onClick={() => setSelectedAsset(null)}><X size={19}/></button></div><span className="square-icon success large"><Table2 size={25}/></span><h2>{selectedAsset.name}</h2><p className="drawer-subtitle">{t(selectedAsset.label)}</p><p>{t(selectedAsset.desc)}</p><div className="asset-detail-tags"><Badge tone="success">{t(domainNames[selectedAsset.domain])}</Badge><Badge>{t(selectedAsset.source)}</Badge>{selectedAsset.tags.map((localT: string) => <span className="plain-tag" key={localT}>{t(localT)}</span>)}</div><div className="detail-grid"><div><small>{t("记录数 · 当前范围")}</small><strong>{t(number(scopedRows(data, selectedAsset.name, tenant, persona).length))}</strong></div><div><small>{t("负责人")}</small><strong>{selectedAsset.owner}</strong></div><div><small>{t("数据粒度")}</small><strong>{t(selectedAsset.grain)}</strong></div><div><small>{t("物理执行状态")}</small><strong>{t(health?.dws_connected ? t("问数连接 DWS · 预览为合成镜像") : t("演示镜像 · DWS 未连接"))}</strong></div></div><div className="tabs drawer-tabs">{[['columns', t("字段")], ['preview', t("数据预览")], ['lineage', t("血缘")], ['quality', t("质量")]].map(([key, label]) => <button className={assetTab === key ? 'active' : ''} key={key} onClick={() => setAssetTab(key)}>{t(label)}</button>)}</div>{assetTab === 'columns' ? <div className="column-list">{Object.keys(data.tables[selectedAsset.name][0]).map(key => <div key={key}><span><Braces size={14}/>{t(key)}</span><small>{key === 'email' || key === 'phone' ? <><LockKeyhole size={11}/>{t("受限字段")}</> : typeof data.tables[selectedAsset.name][0][key] === 'number' ? 'NUMBER' : 'STRING'}</small></div>)}</div> : assetTab === 'preview' ? <><p className="muted">{t("最多展示 8 条 · 应用演示租户及角色范围")}</p><Table rows={scopedRows(data, selectedAsset.name, tenant, persona)}/></> : assetTab === 'quality' ? <div className="quality-detail"><strong>{selectedAsset.quality}{t("%")}</strong><p>{t("演示质量规则通过率")}</p>{selectedAsset.name === 'inventory' ? <p>{t("全量数据包含 6 条负库存异常，用于测试质量检查和失败处理。")}</p> : selectedAsset.name === 'customers' ? <p>{t("全量数据包含 18 条缺失联系方式记录。非工程师身份的联系方式已脱敏。")}</p> : <p>{t("主键、租户绑定和关联完整性通过生成器校验。")}</p>}</div> : <div className="lineage-preview"><span><Database size={16}/>{t("Synthetic commerce generator")}</span><ArrowDown size={18}/><span><Table2 size={16}/>{selectedAsset.name}</span><ArrowDown size={18}/><span><BarChart3 size={16}/>{t("ChatBI / Processing workflow")}</span><p className="muted">{t("此处为演示来源关系；真实执行血缘由后端登记到 OpenMetadata。")}</p></div>}<div className="drawer-actions"><button className="button secondary" onClick={() => exportRows(scopedRows(data, selectedAsset.name, tenant, persona), selectedAsset.name + '.csv')}><Download size={15}/>{t("导出样本")}</button><button className="button primary" onClick={() => { const q = selectedAsset.name === 'inventory' ? t("检查库存健康") : selectedAsset.name === 'reviews' ? t("分析评论情感") : selectedAsset.name === 'ad_metrics' ? t("分析广告ROAS") : selectedAsset.name === 'returns' ? t("分析退款原因") : selectedAsset.name === 'competitor_prices' ? t("分析竞品价格") : t("分析10月各地区销售额"); setSelectedAsset(null); submit(q); }}><Sparkles size={15}/>{t("用 Agent 分析")}</button></div></aside></div>}
  {displayedJob && <div className="drawer-overlay" onClick={() => setSelectedJob(null)}><aside className="detail-drawer job-drawer" onClick={e => e.stopPropagation()}><div className="drawer-top"><span className="mini-eyebrow">{t("WORKFLOW EXECUTION")}</span><button className="icon-button" aria-label={t("关闭任务详情")} onClick={() => setSelectedJob(null)}><X size={19}/></button></div><h2>{t(displayedJob.name)}</h2><p>{t(displayedJob.id)}{t(" · v")}{displayedJob.version}</p><Badge tone={displayedJob.status === 'completed' ? 'success' : displayedJob.status === 'failed' ? 'red' : 'blue'}>{t(statusLabels[displayedJob.status])}</Badge><div className="execution-timeline">{displayedJob.nodes.map((n, i) => { const activeIndex = displayedJob.nodes.findIndex(x => x.id === displayedJob.currentNode); const done = displayedJob.status === 'completed' || i < activeIndex; return <div key={n.id}><span className={done ? 'done' : i === activeIndex ? 'current' : ''}>{done ? <Check size={14}/> : i + 1}</span><div><strong>{t(n.label)}</strong><small>{t(n.description)}</small></div>{done ? <CheckCircle2 size={15}/> : i === activeIndex && displayedJob.status === 'running' ? <Loader2 size={15} className="spin"/> : null}</div>; })}</div><h4>{t("执行日志")}</h4><div className="job-logs">{displayedJob.logs.map((l, i) => <div key={i}><time>{t(time(l.time))}</time><span>{t(l.message)}</span></div>)}{displayedJob.error && <p className="error-text">{t(displayedJob.error)}</p>}</div>{displayedJob.result && <><h4>{t("产出结果 · ")}{displayedJob.result.length}{t(" 行")}</h4><Table rows={displayedJob.result}/></>}<div className="drawer-actions">{['queued', 'running'].includes(displayedJob.status) ? <button className="button secondary" onClick={() => cancelJob(displayedJob)}><Square size={14}/>{t("取消任务")}</button> : <button className="button secondary" onClick={() => { setWorkflow(displayedJob.workflow); setSelectedJob(null); setPage('flows'); }}><GitBranch size={14}/>{t("打开流程")}</button>}{displayedJob.result && <button className="button primary" onClick={() => exportRows(displayedJob.result!, displayedJob.id + '.csv')}><Download size={15}/>{t("导出结果")}</button>}</div></aside></div>}
  {modal && <div className="modal-overlay" onClick={() => setModal('')}><section className="modal" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}><button className="modal-close icon-button" aria-label={t("关闭窗口")} onClick={() => setModal('')}><X size={19}/></button>{modal === 'identity' ? <><span className="square-icon success large"><Users size={25}/></span><h2>{t("选择一个视角，探索数据")}</h2><p>{t("这是演示身份切换器，不是生产登录或真实租户认证。")}</p><div className="persona-options">{Object.entries(personas).map(([key, p]) => <button className={persona === key ? 'selected' : ''} key={key} onClick={() => { switchScope(tenant, key as Persona); setModal(''); }}><span className="avatar">{t(p.initials)}</span><div><strong>{t(p.name)}</strong><small>{t(p.region ? `Sales · ${p.region}` : p.govern ? t("Sales · 目录治理") : p.execute ? t("授权域查询与处理执行") : t("授权域分析与导出"))}</small></div>{persona === key ? <CheckCircle2 size={19}/> : <ArrowRight size={16}/>}</button>)}</div></> : modal === 'model' ? <><span className="square-icon purple large"><Sparkles size={25}/></span><h2>{t("模型接入配置")}</h2><p>{t("此处保存非敏感的接入草稿。真实调用配置通过后端环境变量管理；不在浏览器输入密钥。")}</p><label className="form-field">{t("供应商")}<select value={draftModel.provider} onChange={e => setDraftModel({ ...draftModel, provider: e.target.value })}><option value="Huawei Cloud MaaS">{t("Huawei Cloud MaaS")}</option><option value="Other OpenAI-compatible">{t("Other OpenAI-compatible")}</option></select></label><label className="form-field">{t("模型 ID")}<input value={draftModel.model} onChange={e => setDraftModel({ ...draftModel, model: e.target.value })}/></label><label className="form-field">{t("API Base URL（可选草稿）")}<input type="url" placeholder={t("以账号中的实际调用地址为准")} value={draftModel.baseUrl} onChange={e => setDraftModel({ ...draftModel, baseUrl: e.target.value })}/></label><div className="env-hint"><code>{t("MODEL_PROVIDER=huawei_maas")}<br />{t("MODEL_NAME=glm-5.3")}<br />{t("MODEL_BASE_URL=…")}<br />{t("MODEL_API_KEY=…")}</code></div><button className="button primary full" onClick={() => { if (!draftModel.model.trim()) {
        showToast(t("请填写模型 ID。"));
        return;
    } if (draftModel.baseUrl && (!draftModel.baseUrl.startsWith('https://') || /[?#@]/.test(draftModel.baseUrl))) {
        showToast(t("请填写 HTTPS 基础地址，不要包含账号、密钥或查询参数。"));
        return;
    } localStorage.setItem('nexo-model', JSON.stringify(draftModel)); setModal(''); showToast(t("模型接入草稿已保存；尚未修改后端或发起模型调用。")); }}>{t("保存接入草稿")}</button></> : modal === 'policy' ? <><span className="square-icon success large"><ShieldCheck size={25}/></span><h2>{t("销售域演示策略")}</h2><p>{t("销售域管理员可调整本租户销售经理的演示导出权限。其他域及生产权限不会改变。")}</p><label className="form-field">{t("目标角色")}<select value={policyRole} onChange={e => setPolicyRole(e.target.value as Persona)}><option value="manager">{t("区域销售经理")}</option></select></label><label className="toggle-field">{t("允许导出已授权的销售数据")}<input type="checkbox" checked={policies[`${tenant}:${policyRole}:export`] ?? personas[policyRole].export} onChange={e => setPolicies({ ...policies, [`${tenant}:${policyRole}:export`]: e.target.checked })}/></label><div className="info-strip"><LockKeyhole size={15}/><p>{t("地区范围仍为 Mexico City；联系方式继续脱敏。此设置在浏览器演示中生效，后端模式以服务器授权为准。")}</p></div><button className="button primary full" onClick={() => { record('Update demo policy', `${policyRole}:export`); setModal(''); showToast(t("本租户演示策略已更新。")); }}>{t("完成配置")}</button></> : <><span className="square-icon success large"><Network size={25}/></span><h2>{t("欢迎来到 NEXO")}</h2><p>{t("用同一个工作空间，体验从数据发现到任务交付的完整过程。")}</p><div className="guide-steps">{[['01', t("提出问题"), t("在 ChatBI 输入中文、英文或西班牙文问题，查看实际聚合的合成数据。")], ['02', t("理解数据"), t("展开业务目录，检查字段、来源、粒度和访问范围。")], ['03', t("定义过程"), t("在流程画布中配置节点，切换数据工程师身份后下发任务。")], ['04', t("验证治理"), t("切换区域经理、分析师和域管理员，比较可见资产与操作权限。")]].map(([i, localT, d]) => <div key={i}><span>{t(i)}</span><div><strong>{t(localT)}</strong><p>{t(d)}</p></div></div>)}</div><div className="guide-note">{t("当前为合成数据交互演示。云资源、GLM5.3 及开源服务的实际连接状态请查看“连接与模型”。")}</div><button className="button primary full" onClick={() => setModal('')}>{t("开始探索 ")}<ArrowRight size={15}/></button></>}</section></div>}
  {toast && <div className="toast" role="status"><span><CheckCircle2 size={17}/></span>{t(toast)}<button aria-label={t("关闭提示")} onClick={() => setToast('')}><X size={14}/></button></div>}
 </div>;
}
function PageHeading({ eyebrow, title, description, action }: {
    eyebrow: string;
    title: string;
    description: string;
    action?: React.ReactNode;
}) { return <section className="page-heading"><div><div className="eyebrow"><span />{t(eyebrow)}</div><h1>{t(title)}<span className="heading-dot">{t(".")}</span></h1><p>{t(description)}</p></div>{action}</section>; }
function ProcessNode({ data, selected }: {
    data: any;
    selected?: boolean;
}) { useLocale(); const Icon = stageIcons[data.node.type] || Settings2; return <div className={`process-node ${selected ? 'selected' : ''}`}><Handle type="target" position={Position.Left}/><span className={`process-icon ${data.node.type}`}><Icon size={20}/></span><div className="process-label"><small>{data.index.toString().padStart(2, '0')}{t(" · ")}{t(data.node.type.toUpperCase())}</small><strong>{t(data.node.label)}</strong><p>{t(data.node.description)}</p></div><Handle type="source" position={Position.Right}/></div>; }
const nodeTypes = { process: ProcessNode };
function FlowEditor({ flow, onChange, onNotify }: {
    flow: WorkflowDef;
    onChange: (f: WorkflowDef) => void;
    onNotify: (s: string) => void;
}) {
    const [selected, setSelected] = useState<string>('aggregate');
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [newType, setNewType] = useState('transform');
    useEffect(() => { setNodes(old => flow.nodes.map((n, i) => ({ id: n.id, type: 'process', position: old.find(o => o.id === n.id)?.position || { x: ((i % 4 === 1 || i % 4 === 2) ? 296 : 0), y: Math.floor(i / 2) * 158 }, data: { node: n, index: i + 1 }, selected: n.id === selected }))); setEdges(flow.edges.map(e => ({ ...e, type: 'smoothstep', style: { stroke: '#B5AABF', strokeWidth: 2 }, animated: false }))); }, [flow, selected]);
    const current = flow.nodes.find(n => n.id === selected);
    const updateConfig = (key: string, value: string) => onChange({ ...flow, nodes: flow.nodes.map(n => n.id === selected ? { ...n, config: { ...n.config, [key]: value } } : n) });
    const connect = (c: Connection) => { const next = addEdge(c, edges); setEdges(next); onChange({ ...flow, edges: next.map(e => ({ id: e.id, source: e.source, target: e.target })) }); };
    const addNode = () => { const id = 'node-' + Date.now().toString(36); const newNode: WorkflowNode = { id, type: newType, label: newType === 'quality' ? t("质量检查") : newType === 'aggregate' ? t("聚合计算") : t("过滤与标准化"), description: t("点击配置处理规则"), config: newType === 'quality' ? { rule: 'non_empty_non_negative', on_failure: 'stop' } : newType === 'aggregate' ? { dimension: 'region', metric: 'revenue' } : { operation: 'filter_valid', rule: 'net_amount >= 0' } }; const pub = flow.nodes.find(n => n.type === 'publish'); const incoming = flow.edges.find(e => e.target === pub?.id); let nextEdges = flow.edges; if (pub && incoming)
        nextEdges = [...flow.edges.filter(e => e.id !== incoming.id), { id: 'e-' + id, source: incoming.source, target: id }, { id: 'e-' + id + '-out', source: id, target: pub.id }]; onChange({ ...flow, nodes: [...flow.nodes.filter(n => n.id !== pub?.id), newNode, ...(pub ? [pub] : [])], edges: nextEdges }); setSelected(id); onNotify(t("已插入处理节点，可在右侧修改配置。")); };
    return <section className="flow-editor panel"><div className="flow-toolbar"><div className="flow-name"><GitBranch size={17}/><input aria-label={t("流程名称")} value={t(flow.name)} onChange={e => onChange({ ...flow, name: e.target.value })}/><span className="version-tag">{t("v")}{flow.version}</span></div><div className="inline-actions"><select aria-label={t("新增节点类型")} value={newType} onChange={e => setNewType(e.target.value)}><option value="transform">{t("过滤处理")}</option><option value="aggregate">{t("聚合计算")}</option><option value="quality">{t("质量检查")}</option></select><button className="button small secondary" onClick={addNode}><Plus size={14}/>{t("添加节点")}</button><button className="icon-button" aria-label={t("校验流程")} onClick={() => { try {
        validateFlow(flow);
        onNotify(t("流程校验通过：节点连通，依赖无循环。"));
    }
    catch (e: any) {
        onNotify(e.message);
    } }}><FileCheck2 size={17}/></button></div></div><div className="flow-editor-body"><div className="flow-canvas"><div className="canvas-caption"><span />{t(" PROCESS DESIGNER ")}<span className="muted">{t("原始字号 · 拖动画布浏览")}</span></div><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={changes => setNodes(old => applyNodeChanges(changes, old))} onEdgesChange={changes => { const next = applyEdgeChanges(changes, edges); setEdges(next); if (changes.some(c => c.type === 'remove'))
        onChange({ ...flow, edges: next.map(e => ({ id: e.id, source: e.source, target: e.target })) }); }} onConnect={connect} onNodeClick={(_, n) => setSelected(n.id)} ariaLabelConfig={{'controls.zoomIn.ariaLabel':t('放大'),'controls.zoomOut.ariaLabel':t('缩小'),'controls.fitView.ariaLabel':t('适应画布')}} defaultViewport={{ x: 28, y: 76, zoom: 1 }} fitViewOptions={{ padding: .18, minZoom: .85, maxZoom: 1 }} minZoom={.85} maxZoom={1.5} proOptions={{ hideAttribution: true }}><Background color="#DDD9E3" gap={22} size={1}/><Controls showInteractive={false} position="top-right"/></ReactFlow><div className="canvas-legend"><span><i />{t("元数据驱动")}</span><span><i />{t("计算下推")}</span><span><i />{t("版本化流程")}</span></div></div><aside className="node-inspector"><div className="inspector-heading"><Settings2 size={15}/><strong>{t("节点配置")}</strong></div>{current ? <><label className="form-field">{t("节点名称")}<input value={t(current.label)} onChange={e => onChange({ ...flow, nodes: flow.nodes.map(n => n.id === selected ? { ...n, label: e.target.value } : n) })}/></label><p className="inspector-type">{t(current.type.toUpperCase())}{t(" · ")}{current.id}</p>{current.type === 'source' ? <><label className="form-field">{t("输入资产")}<select value={current.config.asset} onChange={e => updateConfig('asset', e.target.value)}><option value="orders">{t("internal.orders")}</option></select></label><label className="form-field">{t("处理日期范围")}<select value={current.config.range} onChange={e => updateConfig('range', e.target.value)}><option value="2026-10">{t("October 2026")}</option><option value="2026-09">{t("September 2026")}</option></select></label></> : current.type === 'aggregate' ? <><label className="form-field">{t("分组维度")}<select value={current.config.dimension} onChange={e => updateConfig('dimension', e.target.value)}><option value="region">{t("region · 地区")}</option><option value="category">{t("category · 品类")}</option><option value="channel">{t("channel · 渠道")}</option></select></label><label className="form-field">{t("计算指标")}<select value={current.config.metric} onChange={e => updateConfig('metric', e.target.value)}><option value="revenue">{t("SUM(net_amount)")}</option><option value="orders">{t("COUNT(DISTINCT order_id)")}</option></select></label></> : current.type === 'publish' ? <><label className="form-field">{t("输出数据集")}<input value={current.config.target} onChange={e => updateConfig('target', e.target.value.replace(/[^a-zA-Z0-9_]/g, ''))}/></label><label className="form-field">{t("写入方式")}<select value={current.config.mode} onChange={e => updateConfig('mode', e.target.value)}><option value="replace_partition">{t("Replace partition")}</option></select></label></> : current.type === 'quality' ? <><label className="form-field">{t("检查规则")}<select value={current.config.rule} onChange={e => updateConfig('rule', e.target.value)}><option value="non_empty_non_negative">{t("结果非空且值非负")}</option><option value="force_fail">{t("强制失败（测试）")}</option></select></label><label className="form-field">{t("失败处理")}<select value={current.config.on_failure} onChange={e => updateConfig('on_failure', e.target.value)}><option value="stop">{t("停止发布")}</option></select></label></> : <label className="form-field">{t("处理规则")}<select value={current.config.operation} onChange={e => updateConfig('operation', e.target.value)}><option value="filter_valid">{t("排除取消及无效金额")}</option><option value="completed_only">{t("只保留 Completed 订单")}</option></select></label>}<div className="inspector-note"><ShieldCheck size={14}/><p>{t("执行身份与租户范围由后端解析，不能在节点参数中扩大权限。")}</p></div>{!['source', 'publish'].includes(current.type) && <button className="danger-link" onClick={() => { const before = flow.edges.find(e => e.target === current.id); const after = flow.edges.find(e => e.source === current.id); onChange({ ...flow, nodes: flow.nodes.filter(n => n.id !== current.id), edges: [...flow.edges.filter(e => e.source !== current.id && e.target !== current.id), ...(before && after ? [{ id: 'e-reconnect-' + Date.now(), source: before.source, target: after.target }] : [])] }); setSelected('source'); }}><Trash2 size={13}/>{t("移除节点")}</button>}</> : <p className="muted">{t("选择画布中的节点查看配置。")}</p>}</aside></div><div className="panel-foot"><span><Database size={13}/>{t("输入数据保留原位 · ")}{flow.nodes.length}{t(" 个节点 · ")}{flow.edges.length}{t(" 条依赖")}</span><span>{t("流程定义、展示与执行共用一个版本")}</span></div></section>;
}
function FlowPrompt({ onApply }: {
    onApply: (s: string) => void;
}) { const [text, setText] = useState(t("处理 10 月订单，排除取消订单，按地区汇总销售额，检查后发布数据集。")); return <div className="flow-prompt"><textarea aria-label={t("描述数据处理过程")} value={t(text)} onChange={e => setText(e.target.value)}/><div><span>{t("当前使用可解释的模板规则")}</span><button className="button small primary" disabled={!text.trim()} onClick={() => onApply(text)}><Sparkles size={14}/>{t("生成流程草稿")}</button></div></div>; }
