import {t,getLocale,canonicalText} from './i18n';
export type Row = Record<string, any>;
export type DemoData = {
    manifest: Row;
    tables: Record<string, Row[]>;
};
export type Persona = 'analyst' | 'manager' | 'engineer' | 'steward';
export const personas: Record<Persona, {
    name: string;
    en: string;
    initials: string;
    domains: string[];
    region?: string;
    export: boolean;
    execute: boolean;
    govern: boolean;
}> = {
    analyst: { name: '业务分析师', en: 'Alex Rivera', initials: 'AR', domains: ['Sales', 'Marketing', 'Supply Chain', 'Finance'], export: true, execute: false, govern: false },
    manager: { name: '区域销售经理', en: 'Morgan Cruz', initials: 'MC', domains: ['Sales'], region: 'Mexico City', export: false, execute: false, govern: false },
    engineer: { name: '数据工程师', en: 'Jordan Reed', initials: 'JR', domains: ['Sales', 'Marketing', 'Supply Chain', 'Finance'], export: true, execute: true, govern: false },
    steward: { name: '销售域管理员', en: 'Casey Lopez', initials: 'CL', domains: ['Sales'], export: false, execute: false, govern: true },
};
export const domainColors: Record<string, string> = { 'Sales': '#C43A1B', 'Marketing': '#7653B1', 'Supply Chain': '#94600F', 'Finance': '#365FAD', 'Platform': '#626A7D' };
export const domainNames: Record<string, string> = { 'Sales': '销售域', 'Marketing': '市场域', 'Supply Chain': '供应链域', 'Finance': '财务域', 'Platform': '平台域' };
export const assets: Row[] = [
    { name: 'orders', label: '订单主表', domain: 'Sales', source: 'Internal', desc: 'Order-level transactions, net revenue, channels and regional performance.', owner: 'Alex Rivera', quality: 100, tags: ['Core asset', 'PII-free'], grain: 'One row per order' },
    { name: 'order_items', label: '订单明细', domain: 'Sales', source: 'Internal', desc: 'Product-level order lines with quantity, price and discount.', owner: 'Alex Rivera', quality: 100, tags: ['Core asset'], grain: 'One row per order line' },
    { name: 'customers', label: '客户档案', domain: 'Sales', source: 'Internal', desc: 'Fictional customer profiles, segments and geography. Contact fields are restricted.', owner: 'Casey Lopez', quality: 98, tags: ['PII', 'Restricted'], grain: 'One row per customer' },
    { name: 'products', label: '商品目录', domain: 'Sales', source: 'Internal', desc: 'Product catalog, categories, brands and unit economics.', owner: 'Alex Rivera', quality: 100, tags: ['Shared dimension'], grain: 'One row per product' },
    { name: 'inventory', label: '库存快照', domain: 'Supply Chain', source: 'Internal', desc: 'Warehouse stock snapshots, reorder points and anomaly scenarios.', owner: 'Jordan Reed', quality: 97.5, tags: ['Quality check'], grain: 'One row per SKU and warehouse' },
    { name: 'shipments', label: '物流履约', domain: 'Supply Chain', source: 'Internal', desc: 'Delivered shipments, carrier performance and promised delivery windows.', owner: 'Jordan Reed', quality: 100, tags: ['Operations'], grain: 'One row per shipment' },
    { name: 'returns', label: '退款与退货', domain: 'Finance', source: 'Internal', desc: 'Return reasons, refund amounts and approval status.', owner: 'Taylor Chen', quality: 100, tags: ['Financial'], grain: 'One row per return' },
    { name: 'campaigns', label: '营销活动', domain: 'Marketing', source: 'Internal', desc: 'Paid media campaign definitions, budgets and channels.', owner: 'Riley Brooks', quality: 100, tags: ['Marketing'], grain: 'One row per campaign' },
    { name: 'ad_metrics', label: '广告投放表现', domain: 'Marketing', source: 'External', desc: 'Synthetic daily advertising impressions, clicks, spend and attributed revenue.', owner: 'Riley Brooks', quality: 100, tags: ['Synthetic feed'], grain: 'One row per campaign and day' },
    { name: 'competitor_prices', label: '竞品价格观察', domain: 'Marketing', source: 'External', desc: 'Fictional competitor prices for price positioning analysis.', owner: 'Riley Brooks', quality: 100, tags: ['Synthetic feed'], grain: 'One row per product and observation' },
    { name: 'reviews', label: '市场评论', domain: 'Marketing', source: 'External', desc: 'Synthetic English marketplace reviews, ratings and labeled sentiment.', owner: 'Riley Brooks', quality: 100, tags: ['Synthetic feed'], grain: 'One row per review' },
];
export function visibleAssets(persona: Persona) { return assets.filter(a => personas[persona].domains.includes(a.domain)); }
export function scopedRows(data: DemoData, table: string, tenant: string, persona: Persona): Row[] {
    const asset = assets.find(a => a.name === table);
    if (!asset || !personas[persona].domains.includes(asset.domain))
        return [];
    let rows = (data.tables[table] || []).filter(r => r.tenant_id === tenant);
    if (personas[persona].region) {
        const reg = personas[persona].region;
        if (table === 'orders' || table === 'customers')
            rows = rows.filter(r => r.region === reg);
        if (table === 'order_items') {
            const ids = new Set(data.tables.orders.filter(r => r.tenant_id === tenant && r.region === reg).map(r => r.order_id));
            rows = rows.filter(r => ids.has(r.order_id));
        }
    }
    if (table === 'customers' && persona !== 'engineer')
        return rows.map(({ email, phone, ...r }) => ({ ...r, email: '••••@example.test', phone: '••••••••' }));
    return rows;
}
export const money = (n: number, compact = false) => new Intl.NumberFormat(getLocale(), { style: 'currency', currency: 'USD', currencyDisplay: 'narrowSymbol', maximumFractionDigits: compact ? 1 : 0, notation: compact ? 'compact' : 'standard' }).format(n || 0);
export const number = (n: number) => new Intl.NumberFormat(getLocale(), { maximumFractionDigits: 0 }).format(n || 0);
export const sum = (rows: Row[], key: string) => rows.reduce((n, r) => n + (Number(r[key]) || 0), 0);
export const round = (n: number) => Math.round(n * 100) / 100;
export function grouped(rows: Row[], key: string, value: string) { const g: Record<string, number> = {}; for (const r of rows)
    g[String(r[key])] = (g[String(r[key])] || 0) + Number(r[value] || 0); return Object.entries(g).map(([name, value]) => ({ name, value: round(value) })).sort((a, b) => b.value - a.value); }
export function overview(data: DemoData, tenant: string, persona: Persona, month = 'all') {
    const all = scopedRows(data, 'orders', tenant, persona).filter(o => o.status !== 'Cancelled');
    const orders = all.filter(o => month === 'all' || o.order_date.startsWith(month));
    const ids = new Set(orders.map(o => o.order_id));
    const items = scopedRows(data, 'order_items', tenant, persona).filter(i => ids.has(i.order_id));
    const products = new Map(data.tables.products.filter(p => p.tenant_id === tenant).map(p => [p.product_id, p]));
    const byCategory = grouped(items.map(i => ({ ...i, category: products.get(i.product_id)?.category || 'Other' })), 'category', 'net_amount');
    const monthly = grouped(all.map(o => ({ ...o, month: o.order_date.slice(0, 7) })), 'month', 'net_amount').sort((a, b) => a.name.localeCompare(b.name));
    const cost = items.reduce((n, i) => n + Number(products.get(i.product_id)?.unit_cost || 0) * i.quantity, 0);
    const revenue = sum(orders, 'net_amount');
    const sparkCount = monthly.map(m => all.filter(o => o.order_date.startsWith(m.name)).length);
    const sparkAov = monthly.map((m, i) => m.value / (sparkCount[i] || 1));
    const allItems = scopedRows(data, 'order_items', tenant, persona);
    const orderDates = new Map(all.map(o => [o.order_id, o.order_date]));
    const sparkMargin = monthly.map(m => { const c = allItems.filter(i => orderDates.get(i.order_id)?.startsWith(m.name)).reduce((n, i) => n + Number(products.get(i.product_id)?.unit_cost || 0) * i.quantity, 0); return m.value ? (m.value - c) / m.value * 100 : 0; });
    return { orders, revenue, count: orders.length, aov: revenue / (orders.length || 1), margin: revenue ? (revenue - cost) / revenue * 100 : 0, monthly, sparkCount, sparkAov, sparkMargin, regions: grouped(orders, 'region', 'net_amount'), categories: byCategory, channels: grouped(orders, 'channel', 'net_amount') };
}
export type Plan = {
    metric: string;
    dimension: string;
    month: string;
    region?: string;
    title: string;
};
export type Analysis = {
    id: string;
    question: string;
    title: string;
    summary: string;
    data: Row[];
    metric: string;
    dimension: string;
    sql: string;
    steps: string[];
    sources: string[];
    mode: string;
    plan: Plan;
    createdAt: string;
};
/** Normalize Spanish business vocabulary only for the deterministic demo parser. */
export function normalizeQuestion(question: string): string {
    const canonical = canonicalText(question.trim());
    let text = canonical.normalize('NFD').replace(/\p{Diacritic}/gu, '');
    const words: [RegExp,string][] = [
        [/ciudad de mexico/gi,'Mexico City'],[/numero de pedidos|cantidad de pedidos/gi,'order count'],
        [/valor medio del pedido|valor promedio del pedido/gi,'aov'],[/todos los meses|todo el periodo/gi,'all months'],
        [/todas las regiones/gi,'all regions'],[/reembolsos?|devolucion(?:es)?/gi,'refund'],
        [/publicidad|publicitari[oa]s?|campanas?/gi,'advertising'],[/inventario|existencias|reposicion/gi,'inventory'],
        [/resenas?|comentarios?|sentimiento/gi,'review'],[/competencia|competidor(?:es)?/gi,'competitor'],
        [/ventas?|ingresos?/gi,'sales'],[/categorias?/gi,'category'],[/canal(?:es)?/gi,'channel'],
        [/regiones?|regional/gi,'region'],[/tendencias?|mensual|meses/gi,'trend'],
        [/octubre/gi,'october'],[/septiembre/gi,'september'],[/norte/gi,'north'],[/sur/gi,'south'],
    ];
    for (const [pattern,replacement] of words) text=text.replace(pattern,replacement);
    return text;
}
export function inferPlan(question: string, previous?: Plan): Plan {
    question = normalizeQuestion(question);
    let metric = previous?.metric || 'revenue';
    let dimension = previous?.dimension || 'region';
    let month = previous?.month || '2026-10';
    let region = previous?.region;
    if (/退款|退货|refund|return/i.test(question))
        metric = 'refund';
    else if (/广告|投放|roas|advertis|campaign/i.test(question))
        metric = 'roas';
    else if (/库存|补货|stock|inventory/i.test(question))
        metric = 'stock';
    else if (/评论|情感|review|sentiment/i.test(question))
        metric = 'sentiment';
    else if (/竞品|定价|competitor|pricing/i.test(question))
        metric = 'pricing';
    else if (/订单量|订单数|order count/i.test(question))
        metric = 'orders';
    else if (/客单价|aov/i.test(question))
        metric = 'aov';
    else if (/销售|收入|revenue|sales/i.test(question))
        metric = 'revenue';
    if (/趋势|每月|月份|month|trend/i.test(question))
        dimension = 'month';
    else if (/品类|类别|category|product/i.test(question))
        dimension = 'category';
    else if (/渠道|channel/i.test(question))
        dimension = 'channel';
    else if (/地区|区域|region/i.test(question))
        dimension = 'region';
    if (/全部|所有月份|all time|all months/i.test(question) || dimension === 'month')
        month = 'all';
    else if (/九月|9月|september/i.test(question))
        month = '2026-09';
    else if (/十月|10月|上月|october|last month/i.test(question))
        month = '2026-10';
    if (/墨西哥城|mexico city/i.test(question))
        region = 'Mexico City';
    else if (/北部|north/i.test(question))
        region = 'North';
    else if (/南部|south/i.test(question))
        region = 'South';
    else if (/所有地区|全部地区|all regions/i.test(question))
        region = undefined;
    const labels: Record<string, string> = { revenue: t("销售额"), orders: t("订单量"), aov: t("客单价"), refund: t("退款分析"), roas: t("广告投放回报"), stock: t("库存补货分析"), sentiment: t("市场评论分析"), pricing: t("竞品价格分析") };
    const dims: Record<string, string> = { region: t("地区"), category: t("品类"), channel: t("渠道"), month: t("月份") };
    const period=month === 'all' ? t('各月') : month === '2026-09' ? t('9 月') : t('10 月');
    return {metric, dimension, month, region, title: ['revenue','orders','aov'].includes(metric) ? `${labels[metric]} · ${dims[dimension]} · ${period}` : labels[metric]};
}
export function analyze(data: DemoData, tenant: string, persona: Persona, question: string, previous?: Plan): Analysis {
    const originalQuestion=question; question=normalizeQuestion(question);
    if (!/销售|收入|订单|地区|区域|品类|类别|渠道|趋势|月份|九月|十月|[0-9]月|客单价|退款|退货|广告|投放|库存|补货|评论|情感|竞品|定价|墨西哥|北部|南部|sales|revenue|order|region|category|channel|month|refund|return|roas|advertis|campaign|stock|inventory|review|sentiment|competitor|pricing|mexico|north|south|aov/i.test(question))
        throw Error(t("当前规则演示支持销售、退款、广告、库存、评论和竞品分析。更开放的自然语言理解需接通 GLM5.3。"));
    const plan = inferPlan(question, previous);
    const { metric, dimension, month } = plan;
    const needed = metric === 'refund' ? 'Finance' : ['roas', 'sentiment', 'pricing'].includes(metric) ? 'Marketing' : metric === 'stock' ? 'Supply Chain' : 'Sales';
    if (!personas[persona].domains.includes(needed))
        throw new Error(t("当前角色没有{0}的数据访问权限。可以切换演示身份，或在分权分域中查看授权范围。", [t(domainNames[needed])]));
    if (plan.region && personas[persona].region && plan.region !== personas[persona].region)
        throw new Error(t("请求的地区超出当前角色授权范围。当前仅可访问 Mexico City。"));
    let result: Row[] = [], sources = ['orders'];
    let sql = '';
    let summary = '';
    const tenantWhere = `tenant_id = :tenant_id`;
    const region = personas[persona].region || plan.region;
    const regionWhere = region ? ' AND region = :allowed_region' : '';
    let orders = scopedRows(data, 'orders', tenant, persona).filter(o => o.status !== 'Cancelled' && (month === 'all' || o.order_date.startsWith(month)) && (!plan.region || o.region === plan.region));
    if (['revenue', 'orders', 'aov'].includes(metric)) {
        const orderIds = new Set(orders.map(o => o.order_id));
        const products = new Map(data.tables.products.map(p => [p.product_id, p]));
        const rows: Row[] = dimension === 'category' ? scopedRows(data, 'order_items', tenant, persona).filter(i => orderIds.has(i.order_id)).map(i => ({ ...i, category: products.get(i.product_id)?.category })) : orders.map(o => ({ ...o, month: o.order_date.slice(0, 7) }));
        const groups: Record<string, Row[]> = {};
        for (const r of rows)
            (groups[r[dimension]] ??= []).push(r);
        result = Object.entries(groups).map(([name, rs]) => ({ name, value: round(metric === 'orders' ? new Set(rs.map(r => r.order_id)).size : metric === 'aov' ? sum(rs, 'net_amount') / new Set(rs.map(r => r.order_id)).size : sum(rs, 'net_amount')) }));
        result.sort(dimension === 'month' ? (a, b) => a.name.localeCompare(b.name) : (a, b) => b.value - a.value);
        if (dimension === 'category')
            sources.push('order_items', 'products');
        const dim = dimension === 'month' ? "SUBSTRING(o.order_date, 1, 7)" : dimension === 'category' ? 'p.category' : `o.${dimension}`;
        const expr = metric === 'orders' ? 'COUNT(DISTINCT o.order_id)' : metric === 'aov' ? `SUM(${dimension === 'category' ? 'i' : 'o'}.net_amount) / NULLIF(COUNT(DISTINCT o.order_id), 0)` : `SUM(${dimension === 'category' ? 'i' : 'o'}.net_amount)`;
        sql = `SELECT ${dim} AS dimension,\n       ${expr} AS ${metric}\nFROM internal.orders o${dimension === 'category' ? '\nJOIN internal.order_items i ON o.order_id = i.order_id AND o.tenant_id = i.tenant_id\nJOIN internal.products p ON i.product_id = p.product_id AND i.tenant_id = p.tenant_id' : ''}\nWHERE o.${tenantWhere}${regionWhere.replace('region', 'o.region')}\n  AND o.status <> 'Cancelled'${month === 'all' ? '' : "\n  AND o.order_date >= :start_date AND o.order_date < :end_date"}\nGROUP BY ${dim}\nORDER BY ${metric} DESC;`;
        const total = sum(orders, 'net_amount');
        const top = result[0];
        summary = t("当前授权范围内共有 {0} 笔非取消订单，净销售额为 {1}。{2}金额统一为 USD；此结果来自合成数据的实际聚合。", [number(orders.length), money(total), top ? t("{0} 的{1}最高，为 {2}。", [top.name, metric === 'orders' ? t("订单量") : metric === 'aov' ? t("客单价") : t("销售额"), metric === 'orders' ? number(top.value) : money(top.value)]) : '']);
    }
    else if (metric === 'refund') {
        sources = ['returns', 'orders'];
        const rows = scopedRows(data, 'returns', tenant, persona).filter(r => month === 'all' || r.return_date.startsWith(month));
        result = grouped(rows, 'reason', 'refund_amount');
        summary = t("当前范围内有 {0} 条退货记录，涉及退款 {1}。最高退款原因是 {2}；金额包含不同审批状态，不能直接等同已支付退款。", [number(rows.length), money(sum(rows, 'refund_amount')), result[0]?.name || t("暂无")]);
        sql = `SELECT reason, SUM(refund_amount) AS refund_amount\nFROM internal.returns\nWHERE ${tenantWhere}\n  AND return_date >= :start_date AND return_date < :end_date\nGROUP BY reason ORDER BY refund_amount DESC;`;
    }
    else if (metric === 'roas') {
        sources = ['ad_metrics', 'campaigns'];
        const rows = scopedRows(data, 'ad_metrics', tenant, persona).filter(r => month === 'all' || r.metric_date.startsWith(month));
        const campaigns = new Map(data.tables.campaigns.map(c => [c.campaign_id, c]));
        const groups: Record<string, Row[]> = {};
        for (const r of rows)
            (groups[campaigns.get(r.campaign_id)?.platform || 'Other'] ??= []).push(r);
        result = Object.entries(groups).map(([name, rs]) => ({ name, value: round(sum(rs, 'attributed_revenue_usd') / (sum(rs, 'spend_usd') || 1)), spend: round(sum(rs, 'spend_usd')), revenue: round(sum(rs, 'attributed_revenue_usd')) })).sort((a, b) => b.value - a.value);
        summary = t("{0} 广告支出 {1}，归因收入 {2}，整体 ROAS 为 {3}×。归因收入来自演示广告口径，不与订单净销售额直接相加。", [month === 'all' ? t("当前时间范围") : month, money(sum(rows, 'spend_usd')), money(sum(rows, 'attributed_revenue_usd')), (sum(rows, 'attributed_revenue_usd') / (sum(rows, 'spend_usd') || 1)).toFixed(2)]);
        sql = `SELECT c.platform,\n       SUM(a.attributed_revenue_usd) / NULLIF(SUM(a.spend_usd), 0) AS roas\nFROM external.ad_metrics a\nJOIN internal.campaigns c ON a.campaign_id = c.campaign_id AND a.tenant_id = c.tenant_id\nWHERE a.${tenantWhere}\nGROUP BY c.platform ORDER BY roas DESC;`;
    }
    else if (metric === 'stock') {
        sources = ['inventory', 'products'];
        const rows = scopedRows(data, 'inventory', tenant, persona).filter(r => month === 'all' || r.snapshot_date.startsWith(month));
        const ps = new Map(data.tables.products.map(p => [p.product_id, p]));
        result = rows.filter(r => r.stock_on_hand < r.reorder_point).map(r => ({ name: ps.get(r.product_id)?.product_name, value: r.stock_on_hand, warehouse: r.warehouse, reorder: r.reorder_point })).sort((a, b) => a.value - b.value).slice(0, 10);
        summary = t("当前租户共有 {0} 条低于补货阈值的库存记录，其中 {1} 条为预置的负库存质量异常。应先核验异常，再生成补货计划。", [rows.filter(r => r.stock_on_hand < r.reorder_point).length, rows.filter(r => r.stock_on_hand < 0).length]);
        sql = `SELECT p.product_name, i.warehouse, i.stock_on_hand\nFROM internal.inventory i\nJOIN internal.products p ON i.product_id=p.product_id AND i.tenant_id=p.tenant_id\nWHERE i.${tenantWhere} AND i.stock_on_hand < i.reorder_point\nORDER BY i.stock_on_hand LIMIT 10;`;
    }
    else if (metric === 'sentiment') {
        sources = ['reviews'];
        const rows = scopedRows(data, 'reviews', tenant, persona).filter(r => month === 'all' || r.review_date.startsWith(month));
        const counts: Record<string, number> = {};
        rows.forEach(r => counts[r.sentiment] = (counts[r.sentiment] || 0) + 1);
        result = Object.entries(counts).map(([name, value]) => ({ name, value }));
        summary = t("共 {0} 条英文合成评论，正面评论占比 {1}%。情感标签由数据生成器预置；当前未调用 GLM5.3 进行情感推理。", [rows.length, ((counts.Positive || 0) / (rows.length || 1) * 100).toFixed(1)]);
        sql = `SELECT sentiment, COUNT(*) AS review_count\nFROM external.reviews\nWHERE ${tenantWhere}\nGROUP BY sentiment;`;
    }
    else {
        sources = ['competitor_prices', 'products'];
        const rows = scopedRows(data, 'competitor_prices', tenant, persona).filter(r => month === 'all' || r.observed_date.startsWith(month));
        const ps = new Map(data.tables.products.map(p => [p.product_id, p]));
        const g: Record<string, number[]> = {};
        rows.forEach(r => (g[r.competitor] ??= []).push((r.price_usd / (ps.get(r.product_id)?.unit_price || 1) - 1) * 100));
        result = Object.entries(g).map(([name, vs]) => ({ name, value: round(vs.reduce((a, b) => a + b, 0) / vs.length) }));
        summary = t("比较 {0} 条合成竞品观察记录。图中数值为竞品相对本方标价的平均差异百分比，负值表示竞品更便宜；这些品牌与报价均为虚构。", [rows.length]);
        sql = `SELECT c.competitor,\n       AVG((c.price_usd / NULLIF(p.unit_price,0)-1)*100) AS price_gap_pct\nFROM external.competitor_prices c\nJOIN internal.products p ON c.product_id=p.product_id AND c.tenant_id=p.tenant_id\nWHERE c.${tenantWhere}\nGROUP BY c.competitor;`;
    }
    if (month !== 'all' && ['roas', 'stock', 'sentiment', 'pricing'].includes(metric)) {
        const dates: Record<string, string> = { roas: 'a.metric_date', stock: 'i.snapshot_date', sentiment: 'review_date', pricing: 'c.observed_date' };
        sql = sql.replace(/\n(GROUP BY|ORDER BY)/, `\n  AND ${dates[metric]} >= :start_date AND ${dates[metric]} < :end_date\n$1`);
    }
    return { id: crypto.randomUUID(), question: originalQuestion, title: plan.title, summary, data: result, metric, dimension, sql, steps: [t("识别当前租户与角色"), t("检索统一指标与资产"), t("解析粒度、筛选与关联"), t("应用域及地区访问范围"), t("聚合演示数据并生成图表")], sources, mode: 'browser_demo', plan, createdAt: new Date().toISOString() };
}
export type WorkflowNode = {
    id: string;
    type: string;
    label: string;
    description: string;
    config: Record<string, string>;
};
export type WorkflowDef = {
    id: string;
    name: string;
    version: number;
    nodes: WorkflowNode[];
    edges: {
        id: string;
        source: string;
        target: string;
    }[];
    schedule: string;
    timezone: string;
    tenant: string;
    domain: string;
};
export function defaultWorkflow(tenant: string): WorkflowDef {
    const nodes: WorkflowNode[] = [
        { id: 'source', type: 'source', label: t("读取订单"), description: 'internal.orders', config: { asset: 'orders', range: '2026-10', status: 'Exclude Cancelled' } },
        { id: 'clean', type: 'transform', label: t("过滤与标准化"), description: t("有效订单 · 金额校验"), config: { operation: 'filter_valid', rule: 'net_amount >= 0' } },
        { id: 'aggregate', type: 'aggregate', label: t("按地区汇总"), description: 'SUM(net_amount)', config: { dimension: 'region', metric: 'revenue' } },
        { id: 'quality', type: 'quality', label: t("数据质量检查"), description: t("结果非空 · 销售额非负"), config: { rule: 'non_empty_non_negative', on_failure: 'stop' } },
        { id: 'publish', type: 'publish', label: t("发布数据集"), description: 'sandbox.regional_sales', config: { target: 'regional_sales', mode: 'replace_partition' } },
    ];
    return { id: 'regional-sales', name: t("地区销售汇总流程"), version: 1, nodes, edges: nodes.slice(0, -1).map((n, i) => ({ id: `e-${i}`, source: n.id, target: nodes[i + 1].id })), schedule: 'manual', timezone: 'America/Mexico_City', tenant, domain: 'Sales' };
}
export type Job = {
    id: string;
    tenant: string;
    name: string;
    version: number;
    status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
    createdAt: string;
    endedAt?: string;
    progress: number;
    currentNode: string;
    nodes: WorkflowNode[];
    logs: {
        time: string;
        message: string;
    }[];
    result?: Row[];
    mode: string;
    error?: string;
    workflow: WorkflowDef;
};
export function validateFlow(flow: WorkflowDef) {
    const ids = new Set(flow.nodes.map(n => n.id));
    if (ids.size !== flow.nodes.length)
        throw new Error(t("节点 ID 重复"));
    if (flow.nodes.length < 2)
        throw new Error(t("流程至少需要输入和输出节点"));
    if (flow.nodes.filter(n => n.type === 'source').length !== 1)
        throw new Error(t("当前演示流程需要且仅支持一个输入节点"));
    if (flow.nodes.filter(n => n.type === 'publish').length !== 1)
        throw new Error(t("流程需要且仅支持一个发布节点"));
    const indegree: Record<string, number> = Object.fromEntries([...ids].map(id => [id, 0]));
    for (const e of flow.edges) {
        if (!ids.has(e.source) || !ids.has(e.target))
            throw new Error(t("连线引用了不存在的节点"));
        indegree[e.target]++;
    }
    const queue = Object.keys(indegree).filter(k => indegree[k] === 0);
    if (queue.length !== 1 || flow.nodes.find(n => n.id === queue[0])?.type !== 'source')
        throw new Error(t("存在未连接的节点，请连接到输入流程"));
    let visited = 0;
    const sorted: string[] = [];
    while (queue.length) {
        const id = queue.shift()!;
        visited++;
        sorted.push(id);
        for (const e of flow.edges.filter(e => e.source === id))
            if (--indegree[e.target] === 0)
                queue.push(e.target);
    }
    if (visited !== ids.size)
        throw new Error(t("流程包含循环依赖"));
    if (flow.nodes.find(n => n.id === sorted.at(-1))?.type !== 'publish')
        throw new Error(t("发布数据集必须是最后一个节点"));
    if (flow.edges.length !== flow.nodes.length - 1 || flow.edges.some(e => flow.edges.filter(f => f.source === e.source).length > 1))
        throw new Error(t("首版执行器支持顺序流程，请保持单链路"));
    const ordered = sorted.map(id => flow.nodes.find(n => n.id === id)!);
    if (ordered.filter(n => n.type === 'aggregate').length !== 1)
        throw new Error(t("首版流程需要且仅支持一个聚合节点"));
    const aggregateIndex = ordered.findIndex(n => n.type === 'aggregate');
    if (ordered.some((n, i) => n.type === 'transform' && i > aggregateIndex || n.type === 'quality' && i < aggregateIndex))
        throw new Error(t("过滤节点必须位于聚合前，质量检查必须位于聚合后"));
    if (ordered[0].config.asset !== 'orders')
        throw new Error(t("当前流程执行器仅支持 orders 输入资产"));
    if (!/^[a-zA-Z][a-zA-Z0-9_]{0,60}$/.test(ordered.at(-1)!.config.target || ''))
        throw new Error(t("请填写有效的输出数据集名称"));
    return sorted.map(id => flow.nodes.find(n => n.id === id)!);
}
export function executeDemoFlow(data: DemoData, flow: WorkflowDef): Row[] {
    const nodes = validateFlow(flow);
    let rows: Row[] = [];
    for (const node of nodes) {
        if (node.type === 'source')
            rows = data.tables.orders.filter(r => r.tenant_id === flow.tenant && r.status !== 'Cancelled' && r.order_date.startsWith(node.config.range));
        else if (node.type === 'transform')
            rows = rows.filter(r => r.net_amount >= 0 && (node.config.operation !== 'completed_only' || r.status === 'Completed'));
        else if (node.type === 'aggregate') {
            if (!['region', 'category', 'channel'].includes(node.config.dimension) || !['revenue', 'orders'].includes(node.config.metric))
                throw Error(t("不支持的聚合配置"));
            const dim = node.config.dimension;
            const ids = new Set(rows.map(r => r.order_id));
            const ps = new Map(data.tables.products.filter(p => p.tenant_id === flow.tenant).map(p => [p.product_id, p]));
            const source: Row[] = dim === 'category' ? data.tables.order_items.filter(i => i.tenant_id === flow.tenant && ids.has(i.order_id)).map(i => ({ ...i, category: ps.get(i.product_id)?.category })) : rows;
            const groups: Record<string, Row[]> = {};
            for (const r of source)
                (groups[r[dim]] ??= []).push(r);
            rows = Object.entries(groups).map(([name, rs]) => ({ name, value: node.config.metric === 'orders' ? new Set(rs.map(r => r.order_id)).size : round(sum(rs, 'net_amount')) }));
        }
        else if (node.type === 'quality' && (node.config.rule === 'force_fail' || !rows.length || rows.some(r => r.value < 0)))
            throw Error(t("质量检查未通过，已停止发布。"));
    }
    return rows.sort((a, b) => b.value - a.value);
}
export function download(name: string, content: string, type = 'text/plain;charset=utf-8') { const u = URL.createObjectURL(new Blob([content], { type })); const a = document.createElement('a'); a.href = u; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(u), 1000); }
export function csv(rows: Row[]) { if (!rows.length)
    return ''; const keys = Object.keys(rows[0]); return '\ufeff' + [keys, ...rows.map(r => keys.map(k => r[k]))].map(row => row.map(v => '"' + String(v ?? '').replaceAll('"', '""') + '"').join(',')).join('\r\n'); }
export function useStoredInitial<T>(key: string, fallback: T): T { try {
    const s = localStorage.getItem(key);
    return s ? JSON.parse(s) : fallback;
}
catch {
    return fallback;
} }
