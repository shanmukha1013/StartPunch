const REPORTS_KEY = 'punchstart_reports';
const BOOKMARKS_KEY = 'punchstart_bookmarks';
const NOTES_KEY = 'punchstart_notes';

let activeReport = null;

document.addEventListener('DOMContentLoaded', () => {
    const emptyState = document.querySelector('.report-empty-state');
    const report = loadReport();

    if (!report) {
        emptyState?.classList.remove('hidden');
        return;
    }

    activeReport = normalizeReport(report);
    renderReport(activeReport);
    bindReportActions(activeReport);
    animateCounters();
    animateGauges();
    revealOnScroll();

    document.getElementById('logout-link')?.addEventListener('click', (event) => {
        event.preventDefault();
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        window.location.href = '../index.html';
    });
});

function loadReport() {
    const params = new URLSearchParams(window.location.search);
    const reportId = params.get('id');
    if (params.get('demo') === '1') return demoReport();
    const reports = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
    if (reportId) {
        const found = reports.find(report => report.id === reportId);
        if (found) return found;
    }
    const raw = sessionStorage.getItem('currentReport');
    if (raw) return JSON.parse(raw);
    return reports[0] || null;
}

function demoReport() {
    return {
        id: 'demo-report',
        startup_name: 'Atlas Ledger',
        industry: 'Fintech',
        created_at: new Date().toISOString(),
        executive_summary: 'Atlas Ledger helps independent exporters reconcile invoices, FX exposure, and working-capital needs in one operating dashboard. The opportunity is attractive if the company proves repeatable acquisition through export associations and converts early pilots into paid finance workflows.',
        startup_score: 84,
        investor_readiness_score: 78,
        tam_sam_som: {
            tam: 'INR 75,000 Cr',
            sam: 'INR 18,000 Cr',
            som: 'INR 900 Cr',
            rationale: 'Market sizing narrows from Indian SME financial operations to digitally reachable exporters with recurring reconciliation and credit needs.'
        },
        market_analysis: 'The market is pulled by exporter digitization, embedded finance adoption, and pressure to manage cash conversion cycles. A narrow beachhead in high-frequency exporters gives Atlas Ledger a credible route to workflow ownership before expanding into financing products.',
        industry_trends: ['SMEs are moving finance workflows from spreadsheets into vertical platforms.', 'Embedded credit is becoming easier to distribute when transaction data is trusted.', 'Export volatility increases demand for real-time cash and FX visibility.'],
        competitor_landscape: [
            { name: 'Bank portals', positioning: 'Trusted financial access points', advantage: 'Existing relationships and compliance rails', gap_to_exploit: 'Weak workflow UX and limited multi-bank visibility' },
            { name: 'Accounting suites', positioning: 'Systems of record for invoices and books', advantage: 'Installed base and accountant familiarity', gap_to_exploit: 'Limited export-specific financing intelligence' },
            { name: 'Trade finance platforms', positioning: 'Capital providers for exporters', advantage: 'Funding access and underwriting experience', gap_to_exploit: 'Less ownership of daily operating workflow' }
        ],
        customer_persona: 'Owner-operators and finance managers at Indian SME exporters handling 50+ monthly invoices, multi-currency payments, and inconsistent working-capital visibility.',
        revenue_strategy: 'Start with a subscription for reconciliation and cash visibility, then add usage-based revenue from financing referrals and premium analytics.',
        business_model_analysis: 'The model is strongest if workflow retention precedes monetization from financial products. Gross margins should remain software-like while partner revenue expands ARPU.',
        swot: {
            strengths: ['Clear pain in export finance workflows', 'Data-rich workflow can improve underwriting', 'Focused customer wedge supports efficient sales'],
            weaknesses: ['Trust must be earned before financial recommendations matter', 'Bank integrations can slow onboarding', 'Exporter segments may require localized support'],
            opportunities: ['Partner with export councils and accountants', 'Create benchmark reports for exporter cash cycles', 'Expand into credit and FX products'],
            threats: ['Banks can bundle similar tools', 'Compliance complexity may increase', 'Accounting suites may move upstream']
        },
        porters_five_forces: [
            { force: 'Competitive rivalry', rating: 'Medium', insight: 'Multiple financial tools exist, but few own exporter-specific daily workflows.' },
            { force: 'Threat of new entrants', rating: 'Medium', insight: 'Workflow insight and integrations create moderate barriers over time.' },
            { force: 'Buyer power', rating: 'Medium', insight: 'SMEs are price-sensitive but pay for clear cash-flow impact.' },
            { force: 'Supplier power', rating: 'Medium', insight: 'Bank and data integrations create dependency risk.' },
            { force: 'Threat of substitutes', rating: 'High', insight: 'Spreadsheets and accountants remain common until ROI is proven.' }
        ],
        go_to_market_strategy: 'Launch with 20 design partners from two export clusters, publish cash-cycle benchmarks, and convert pilots through accountant and association referrals.',
        risk_matrix: [
            { risk: 'Slow integrations', severity: 'High', likelihood: 'Medium', mitigation: 'Start with upload-based workflows while priority integrations are built.' },
            { risk: 'Low willingness to pay', severity: 'Medium', likelihood: 'Medium', mitigation: 'Tie pricing to hours saved and financing outcomes.' },
            { risk: 'Trust barrier', severity: 'High', likelihood: 'Medium', mitigation: 'Add transparent calculations, audit logs, and partner credibility.' }
        ],
        funding_recommendation: 'Raise INR 75,00,000 after 5 paid pilots, with funds allocated to integrations, compliance review, and one focused sales motion.',
        mvp_roadmap: [
            { phase: 'Discovery', timeline: 'Weeks 1-2', focus: 'Map exporter finance workflows', success_metric: '20 interviews and 5 design partners' },
            { phase: 'Concierge MVP', timeline: 'Weeks 3-6', focus: 'Manual reconciliation plus dashboard prototype', success_metric: '3 paid pilots' },
            { phase: 'Beta', timeline: 'Weeks 7-12', focus: 'Automated imports, cash alerts, and finance recommendations', success_metric: 'Weekly use by 60 percent of pilot users' }
        ],
        growth_strategy: 'Expand from exporter finance teams into accountant channels, lender partnerships, and adjacent import/export compliance workflows.',
        pitch_deck_outline: [
            { title: 'Vision', content: 'The operating finance layer for SME exporters.' },
            { title: 'Problem', content: 'Exporters lack real-time cash, invoice, and FX clarity.' },
            { title: 'Solution', content: 'A unified reconciliation and financing intelligence workspace.' },
            { title: 'Market', content: 'Large SME finance opportunity with a focused exporter wedge.' },
            { title: 'Product', content: 'Dashboard, alerts, reconciliation, and financing recommendations.' },
            { title: 'Business Model', content: 'Subscription plus partner revenue.' },
            { title: 'GTM', content: 'Export clusters, accountants, associations, and lender partners.' },
            { title: 'Ask', content: 'INR 75,00,000 to prove paid pilots and integrations.' }
        ],
        market_timing_analysis: 'Digital finance adoption and volatile export conditions create urgency now, while investors still require proof of paid workflow retention.',
        founder_recommendations: ['Interview exporters in one cluster before expanding.', 'Charge for pilots to test urgency.', 'Instrument time saved and financing conversion.', 'Prioritize trust-building UX over feature breadth.'],
        monetization_strategy: 'Use a starter subscription for workflow visibility, then grow through premium alerts, team seats, and partner revenue from financing outcomes.',
        investor_attractiveness_analysis: 'Atlas Ledger becomes fundable when it proves paid exporter retention, repeatable channel acquisition, and differentiated transaction data.'
    };
}

function normalizeReport(data) {
    return {
        id: data.id || 'current',
        startupName: data.startup_name || data.startupName || 'Startup',
        industry: data.industry || 'Startup',
        executiveSummary: clean(data.executive_summary || data.executiveSummary),
        startupScore: number(data.startup_score || data.startupScore),
        investorReadiness: number(data.investor_readiness_score || data.investor_readiness || data.investorReadiness),
        marketSize: data.tam_sam_som || {},
        marketAnalysis: clean(data.market_analysis || data.marketAnalysis),
        industryTrends: array(data.industry_trends),
        competitors: array(data.competitor_landscape || data.competitor_analysis),
        customerPersona: clean(data.customer_persona || data.customerPersona),
        revenueStrategy: clean(data.revenue_strategy || data.revenue_model || data.revenueModel),
        businessModel: clean(data.business_model_analysis),
        swot: data.swot || data.swot_analysis || {},
        forces: array(data.porters_five_forces || data.portersFiveForces),
        gtm: clean(data.go_to_market_strategy || data.goToMarketStrategy),
        risks: array(data.risk_matrix || data.risk_assessment),
        funding: clean(data.funding_recommendation || data.funding_analysis),
        roadmap: array(data.mvp_roadmap || data.mvpRoadmap),
        growth: clean(data.growth_strategy),
        pitchDeck: array(data.pitch_deck_outline || data.investor_pitch_deck),
        timing: clean(data.market_timing_analysis),
        founderRecommendations: array(data.founder_recommendations),
        monetization: clean(data.monetization_strategy),
        investorAttractiveness: clean(data.investor_attractiveness_analysis),
        createdAt: data.created_at
    };
}

function renderReport(report) {
    const container = document.getElementById('report-content');
    const score = clamp(report.startupScore || 72);
    const readiness = clamp(report.investorReadiness || score);
    const bookmarked = getBookmarks().includes(report.id);

    container.innerHTML = `
        <section class="report-hero reveal">
            <div>
                <span class="eyebrow">Investor validation report</span>
                <h1>${escapeHtml(report.startupName)}</h1>
                <p style="font-size: 1.05rem; color: var(--gold); font-weight: 700; margin: 10px 0 16px; text-transform: uppercase; letter-spacing: 0.05em;">Ideas deserve evidence.</p>
                <p>${escapeHtml(report.executiveSummary)}</p>
                <div class="hero-meta">
                    <span>${escapeHtml(report.industry)}</span>
                    <span>${report.createdAt ? new Date(report.createdAt).toLocaleDateString() : 'Latest analysis'}</span>
                    <span>Investor match ${Math.round((score + readiness) / 2)}/100</span>
                </div>
                <div class="report-actions">
                    <button class="btn btn-primary" id="download-report">Download Report</button>
                    <button class="btn btn-secondary" id="share-report">Share Report</button>
                    <button class="btn btn-secondary" id="print-report">Export PDF</button>
                    <button class="btn btn-secondary" id="bookmark-report">${bookmarked ? 'Bookmarked' : 'Bookmark'}</button>
                </div>
            </div>
            <div class="score-cluster">
                ${scoreCircle('Startup Score', score, 'startup')}
                ${scoreCircle('Investor Readiness', readiness, 'readiness')}
            </div>
        </section>

        <section class="metric-grid reveal">
            ${renderMarketProportions(report)}
        </section>

        ${section('Executive Summary', `<p>${escapeHtml(report.executiveSummary)}</p>`)}
        ${section('Market Opportunity Analysis', `<p>${escapeHtml(report.marketAnalysis)}</p>${list(report.industryTrends, 'trend-list')}`)}
        ${section('Competitor Positioning Matrix', `<div class="competitor-grid">${report.competitors.map(renderCompetitor).join('')}</div>`)}
        ${section('Customer Persona Definition', `<div class="persona-card"><strong>Primary Buyer Profile</strong><p>${escapeHtml(report.customerPersona)}</p></div>`)}
        ${section('Revenue Strategy & Business Model', `<p>${escapeHtml(report.revenueStrategy)}</p><p>${escapeHtml(report.businessModel)}</p><p>${escapeHtml(report.monetization)}</p>`)}
        ${section('SWOT Matrix Analysis', renderSwot(report.swot))}
        ${section("Porter's Five Forces Industry Competitiveness", `<div class="force-grid">${report.forces.map(renderForce).join('')}</div>`)}
        ${section('Vulnerability Heatmap Matrix', renderRiskHeatmap(report.risks))}
        ${section('Funding Strategy Roadmap', `<div class="funding-panel">${escapeHtml(report.funding)}</div>`)}
        ${section('Startup Readiness Execution Timeline', renderRoadmapTimeline(report.roadmap))}
        ${section('Go-To-Market & Growth Strategy', `<p><strong>Launch Plan:</strong> ${escapeHtml(report.gtm)}</p><p><strong>Expansion Plan:</strong> ${escapeHtml(report.growth)}</p><p><strong>Timing Indicators:</strong> ${escapeHtml(report.timing)}</p>`)}
        ${section('Investor Pitch Deck Framework', `<div class="pitch-grid">${report.pitchDeck.map(renderSlide).join('')}</div>`)}
        ${section('Founder Recommendations Checklist', renderFounderRecommendations(report.founderRecommendations))}
        <section class="report-section notes-section reveal">
            <h2>Founder Workspace Notes</h2>
            ${renderNotes(report)}
        </section>
        ${section('Investor Venture Feasibility Summary', `
            <div class="investor-conclusion-card">
                <div class="conclusion-icon">⚡</div>
                <div class="conclusion-body">
                    <h3>Feasibility Assessment Summary</h3>
                    <p>${escapeHtml(report.investorAttractiveness)}</p>
                </div>
            </div>
        `)}
    `;
}

function bindReportActions(report) {
    document.getElementById('download-report')?.addEventListener('click', () => {
        const blob = new Blob([buildMarkdownReport(report)], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${report.startupName.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}-punchstart-report.md`;
        link.click();
        URL.revokeObjectURL(url);
        showToast('Report downloaded as Markdown!');
    });
    document.getElementById('print-report')?.addEventListener('click', () => window.print());
    document.getElementById('share-report')?.addEventListener('click', async () => {
        const shareText = `${report.startupName} scored ${report.startupScore}/100 on PunchStart.`;
        if (navigator.share) {
            try {
                await navigator.share({ title: `${report.startupName} report`, text: shareText, url: window.location.href });
                showToast('Report shared successfully!');
            } catch (err) {
                // Cancelled or unsupported
            }
        } else {
            await navigator.clipboard.writeText(`${shareText} ${window.location.href}`);
            showToast('Share link copied to clipboard!');
            const btn = document.getElementById('share-report');
            if (btn) {
                const oldText = btn.textContent;
                btn.textContent = 'Link Copied';
                setTimeout(() => btn.textContent = oldText, 2000);
            }
        }
    });
    document.getElementById('bookmark-report')?.addEventListener('click', event => {
        const bookmarks = getBookmarks();
        const next = bookmarks.includes(report.id)
            ? bookmarks.filter(id => id !== report.id)
            : [...bookmarks, report.id];
        localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(next));
        const isBookmarked = next.includes(report.id);
        event.currentTarget.textContent = isBookmarked ? 'Bookmarked' : 'Bookmark';
        showToast(isBookmarked ? 'Report added to bookmarks!' : 'Report removed from bookmarks!');
    });
    document.getElementById('founder-notes')?.addEventListener('input', event => {
        const notes = JSON.parse(localStorage.getItem(NOTES_KEY) || '{}');
        notes[report.id] = event.target.value;
        localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
    });
}

function scoreCircle(label, score, type) {
    const color = score <= 40 ? 'var(--danger)' : score <= 70 ? 'var(--warning)' : 'var(--lime)';
    return `
        <article class="score-card">
            <div class="svg-gauge-wrapper" style="--score:${score}; --ring-color:${color}">
                <svg class="svg-gauge" viewBox="0 0 100 100">
                    <defs>
                        <linearGradient id="score-grad-${type}" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="${type === 'startup' ? '#EAB308' : '#3B82F6'}" />
                            <stop offset="100%" stop-color="${type === 'startup' ? '#EF4444' : '#10B981'}" />
                        </linearGradient>
                    </defs>
                    <circle class="gauge-track" cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="8"></circle>
                    <circle class="gauge-fill" data-gauge-score="${score}" cx="50" cy="50" r="40" fill="none" stroke="url(#score-grad-${type})" stroke-width="8" 
                            stroke-dasharray="251.2" stroke-dashoffset="251.2"
                            stroke-linecap="round" transform="rotate(-90 50 50)"></circle>
                </svg>
                <div class="gauge-overlay">
                    <strong data-count="${score}">0</strong>
                    <small>/100</small>
                </div>
            </div>
            <p class="gauge-label">${escapeHtml(label)}</p>
        </article>
    `;
}

function renderMarketProportions(report) {
    const tamVal = report.marketSize.tam || 'INR 50,000 Cr';
    const samVal = report.marketSize.sam || 'INR 10,000 Cr';
    const somVal = report.marketSize.som || 'INR 500 Cr';

    return `
        <article class="metric-card wide" style="min-height: auto; width: 100%; display: block; border-color: var(--line);">
            <span style="font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 18px; display: block;">Market Segmentation Map (TAM / SAM / SOM)</span>
            
            <div class="market-proportions-container">
                <div class="market-proportion-card tam-card">
                    <span class="market-badge">TAM</span>
                    <h3 class="market-value">${escapeHtml(tamVal)}</h3>
                    <p class="market-label">Total Addressable Market</p>
                    <p class="market-description">Maximum market size opportunity if 100% market share is achieved.</p>
                </div>
                <div class="market-proportion-card sam-card">
                    <span class="market-badge">SAM</span>
                    <h3 class="market-value">${escapeHtml(samVal)}</h3>
                    <p class="market-label">Serviceable Addressable Market</p>
                    <p class="market-description">The portion of the market targeted by your product within your reach.</p>
                </div>
                <div class="market-proportion-card som-card">
                    <span class="market-badge">SOM</span>
                    <h3 class="market-value">${escapeHtml(somVal)}</h3>
                    <p class="market-label">Serviceable Obtainable Market</p>
                    <p class="market-description">The share of the market you can realistically capture in the short to medium term.</p>
                </div>
            </div>
            
            <p class="market-rationale-text" style="margin-top: 18px;"><strong>Estimation assumptions:</strong> ${escapeHtml(report.marketSize.rationale || 'Sizing is narrowed from category demand limits.')}</p>
        </article>
    `;
}

function section(title, content) {
    return `<section class="report-section reveal"><h2>${escapeHtml(title)}</h2>${content}</section>`;
}

function renderCompetitor(item) {
    if (typeof item === 'string') return `<article class="competitor-card"><h3>${escapeHtml(item)}</h3></article>`;
    return `
        <article class="competitor-card">
            <h3>${escapeHtml(item.name)}</h3>
            <p>${escapeHtml(item.positioning)}</p>
            <dl style="margin-top: 10px; display: grid; gap: 6px;">
                <dt style="color: var(--gold); font-size: 0.76rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em;">Core Advantage</dt>
                <dd style="margin: 0; color: #c5cfdd; font-size: 0.86rem;">${escapeHtml(item.advantage)}</dd>
                <dt style="color: var(--blue); font-size: 0.76rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em;">Vulnerability to Exploit</dt>
                <dd style="margin: 0; color: #c5cfdd; font-size: 0.86rem;">${escapeHtml(item.gap_to_exploit)}</dd>
            </dl>
        </article>
    `;
}

function renderSwot(swot) {
    const blocks = [
        ['Strengths', swot.strengths, 'strengths'],
        ['Weaknesses', swot.weaknesses, 'weaknesses'],
        ['Opportunities', swot.opportunities, 'opportunities'],
        ['Threats', swot.threats, 'threats']
    ];
    return `<div class="swot-grid">${blocks.map(([title, values, cssClass]) => `
        <article class="swot-card ${cssClass}">
            <h3>${escapeHtml(title)}</h3>
            ${list(array(values).slice(0, 3), '')}
        </article>
    `).join('')}</div>`;
}

function renderForce(item) {
    return `<article class="force-card"><span>${escapeHtml(item.rating || 'Medium')}</span><h3>${escapeHtml(item.force)}</h3><p>${escapeHtml(item.insight)}</p></article>`;
}

function renderRiskHeatmap(risks) {
    const matrix = {
        'high-low': [], 'high-medium': [], 'high-high': [],
        'medium-low': [], 'medium-medium': [], 'medium-high': [],
        'low-low': [], 'low-medium': [], 'low-high': []
    };
    
    const validRisks = array(risks);
    validRisks.forEach((item, index) => {
        if (!item || typeof item !== 'object') return;
        const sev = String(item.severity || 'Medium').toLowerCase().trim();
        const lik = String(item.likelihood || 'Medium').toLowerCase().trim();
        const key = `${sev}-${lik}`;
        if (matrix[key]) {
            matrix[key].push({ ...item, index: index + 1 });
        } else {
            matrix['medium-medium'].push({ ...item, index: index + 1 });
        }
    });

    const getMarkers = (key) => {
        return (matrix[key] || []).map(r => `
            <span class="risk-marker" title="${escapeHtml(r.risk)}">R${r.index}</span>
        `).join('');
    };

    return `
        <div class="risk-heatmap-layout">
            <div class="heatmap-grid">
                <div class="heatmap-corner">Severity ↓ / Likelihood →</div>
                <div class="heatmap-header">Low</div>
                <div class="heatmap-header">Medium</div>
                <div class="heatmap-header">High</div>

                <div class="heatmap-label-row">High</div>
                <div class="heatmap-cell low-high">${getMarkers('high-low')}</div>
                <div class="heatmap-cell med-high">${getMarkers('high-medium')}</div>
                <div class="heatmap-cell high-high">${getMarkers('high-high')}</div>

                <div class="heatmap-label-row">Medium</div>
                <div class="heatmap-cell low-med">${getMarkers('medium-low')}</div>
                <div class="heatmap-cell med-med">${getMarkers('medium-medium')}</div>
                <div class="heatmap-cell high-med">${getMarkers('medium-high')}</div>

                <div class="heatmap-label-row">Low</div>
                <div class="heatmap-cell low-low">${getMarkers('low-low')}</div>
                <div class="heatmap-cell med-low">${getMarkers('low-medium')}</div>
                <div class="heatmap-cell high-low">${getMarkers('low-high')}</div>
            </div>
            
            <div class="risk-details-list">
                ${validRisks.map((item, index) => {
                    if (!item || typeof item !== 'object') return '';
                    const sev = String(item.severity || 'Medium').toLowerCase();
                    return `
                        <div class="risk-detail-row ${sev}">
                            <div class="risk-detail-number">R${index + 1}</div>
                            <div class="risk-detail-body">
                                <strong>${escapeHtml(item.risk)}</strong>
                                <p>Mitigation: ${escapeHtml(item.mitigation)}</p>
                            </div>
                            <span class="risk-tag ${sev}">${escapeHtml(item.severity)} Severity / ${escapeHtml(item.likelihood)} Likelihood</span>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

function renderRoadmapTimeline(roadmap) {
    const list = array(roadmap);
    return `
        <div class="timeline-container">
            ${list.map((item, index) => {
                if (typeof item === 'string') {
                    return `
                        <div class="timeline-step-row reveal">
                            <div class="timeline-badge">${index + 1}</div>
                            <div class="timeline-content-card">
                                <div class="timeline-card-header">
                                    <h3>Phase ${index + 1}</h3>
                                </div>
                                <p>${escapeHtml(item)}</p>
                            </div>
                        </div>
                    `;
                }
                const phaseTitle = item.phase || `Phase ${index + 1}`;
                const focusText = item.focus || '';
                const timeline = item.timeline || 'TBD';
                const metric = item.success_metric || 'Completion';
                return `
                    <div class="timeline-step-row reveal">
                        <div class="timeline-badge">${index + 1}</div>
                        <div class="timeline-content-card">
                            <div class="timeline-card-header">
                                <h3>${escapeHtml(phaseTitle)}</h3>
                                <span class="timeline-badge-date">${escapeHtml(timeline)}</span>
                            </div>
                            <p>${escapeHtml(focusText)}</p>
                            <div class="timeline-metric-row">
                                <strong>Success Metric</strong>
                                <span>${escapeHtml(metric)}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderFounderRecommendations(recs) {
    const list = array(recs);
    return `
        <div class="interactive-checklist">
            ${list.map((item, index) => `
                <div class="checklist-item">
                    <label class="checkbox-container">
                        <input type="checkbox" id="rec-check-${index}">
                        <span class="custom-checkbox"></span>
                        <span class="checklist-text">${escapeHtml(item)}</span>
                    </label>
                </div>
            `).join('')}
        </div>
    `;
}

function renderSlide(item, index) {
    if (typeof item === 'string') return `<article class="pitch-card"><span>${index + 1}</span><h3>${escapeHtml(item)}</h3></article>`;
    return `<article class="pitch-card"><span>${index + 1}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.content)}</p></article>`;
}

function renderNotes(report) {
    const notes = JSON.parse(localStorage.getItem(NOTES_KEY) || '{}');
    return `<textarea id="founder-notes" class="form-control founder-notes" placeholder="Capture investor questions, customer evidence, or next validation steps.">${escapeHtml(notes[report.id] || '')}</textarea>`;
}

function animateCounters() {
    document.querySelectorAll('[data-count]').forEach(element => {
        const target = Number(element.dataset.count || 0);
        const start = performance.now();
        const tick = now => {
            const progress = Math.min(1, (now - start) / 760);
            element.textContent = Math.round(target * progress);
            if (progress < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    });
}

function animateGauges() {
    setTimeout(() => {
        document.querySelectorAll('.gauge-fill').forEach(circle => {
            const score = Number(circle.dataset.gaugeScore || 0);
            circle.style.strokeDashoffset = 251.2 - (251.2 * score) / 100;
        });
    }, 100);
}

function revealOnScroll() {
    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12 });
    document.querySelectorAll('.reveal').forEach(section => observer.observe(section));
}

function getBookmarks() {
    return JSON.parse(localStorage.getItem(BOOKMARKS_KEY) || '[]');
}

function buildMarkdownReport(report) {
    return `# ${report.startupName} PunchStart Report

*Ideas deserve evidence.*

Score: ${report.startupScore}/100
Investor Readiness: ${report.investorReadiness}/100

## Executive Summary
${report.executiveSummary}

## Market
TAM: ${report.marketSize.tam}
SAM: ${report.marketSize.sam}
SOM: ${report.marketSize.som}

## Funding Strategy
${report.funding}

## Founder Recommendations
${array(report.founderRecommendations).map(item => `- ${typeof item === 'string' ? item : JSON.stringify(item)}`).join('\n')}
`;
}

function list(items, className) {
    const values = array(items);
    return `<ul class="${className}">${values.map(item => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
}

function array(value) {
    if (Array.isArray(value) && value.length) return value;
    if (value) return [value];
    return ['Specific insight generated from founder inputs'];
}

function clean(value) {
    const text = String(value || '').trim();
    if (!text || ['n/a', 'unknown', 'not available'].includes(text.toLowerCase())) {
        return 'PunchStart generated this section from the submitted founder inputs and market assumptions.';
    }
    return text;
}

function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 72;
}

function clamp(value) {
    return Math.max(0, Math.min(100, Math.round(value)));
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : 'ℹ'}</span>
        <span class="toast-text">${escapeHtml(message)}</span>
    `;
    container.appendChild(toast);
    
    // Animate entrance
    setTimeout(() => toast.classList.add('visible'), 10);
    
    // Auto-remove
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}
