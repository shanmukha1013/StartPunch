const REPORTS_KEY = 'punchstart_reports';

document.addEventListener('DOMContentLoaded', () => {
    const reports = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
    const search = document.getElementById('dashboard-search');

    renderStats(reports);
    renderPortfolio(reports);
    renderBars(reports);
    renderCharts(reports);
    renderNotifications(reports);
    renderComparisonControls(reports);
    renderFounderInsights(reports);
    renderRecommendations(reports);

    search.addEventListener('input', () => {
        const query = search.value.toLowerCase();
        renderPortfolio(reports.filter(report =>
            `${report.startup_name || ''} ${report.industry || ''}`.toLowerCase().includes(query)
        ));
    });

    document.getElementById('logout-link')?.addEventListener('click', (event) => {
        event.preventDefault();
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        window.location.href = '../index.html';
    });
});

function renderStats(reports) {
    const scores = reports.map(report => Number(report.startup_score || 0)).filter(Boolean);
    const avg = scores.length ? Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length) : 0;
    countUp('total-analyses', reports.length);
    countUp('saved-reports', reports.length);
    countUp('avg-score', avg);
    countUp('ready-count', scores.filter(score => score >= 75).length);
}

function renderPortfolio(reports) {
    const list = document.getElementById('portfolio-list');
    const empty = document.getElementById('empty-recent');
    if (!reports.length) {
        list.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');
    list.innerHTML = reports.map(report => {
        const score = Number(report.startup_score || 0);
        return `
            <article class="portfolio-row">
                <div>
                    <h3>${escapeHtml(report.startup_name || 'Startup')}</h3>
                    <p>${escapeHtml(report.industry || 'Validation report')} - ${formatDate(report.created_at)}</p>
                </div>
                <div class="portfolio-score">${score}<span>/100</span></div>
                <a class="btn btn-text" href="results.html?id=${encodeURIComponent(report.id)}">Open</a>
            </article>
        `;
    }).join('');
}

function renderBars(reports) {
    const scores = reports.slice(0, 8).map(report => Number(report.startup_score || 0));
    const values = scores.length ? scores : [0];
    document.getElementById('score-bars').innerHTML = values.map((score, index) => `
        <div class="score-bar">
            <span style="height:${Math.max(score, 8)}%"></span>
            <small>${scores.length ? score : '0'}</small>
            <em>${scores.length ? `R${index + 1}` : 'Start'}</em>
        </div>
    `).join('');
}

function renderCharts(reports) {
    let chartScores = [];
    let chartLabels = [];
    let isMock = false;

    if (reports.length === 0) {
        chartLabels = ['Idea Phase', 'Problem Discovery', 'Solution Map', 'Target Verification', 'Beta Launch'];
        chartScores = [45, 58, 68, 74, 82];
        isMock = true;
    } else if (reports.length === 1) {
        const single = reports[0];
        chartLabels = ['Idea Concept', 'Problem Discovery', 'Solution Map', (single.startup_name || 'Current').slice(0, 12)];
        const baseScore = Math.max(40, Number(single.startup_score || 0) - 25);
        chartScores = [
            baseScore,
            Math.min(100, Math.round(baseScore + 8)),
            Math.min(100, Math.round(baseScore + 17)),
            Number(single.startup_score || 0)
        ];
    } else {
        chartScores = reports.slice(0, 8).reverse().map(report => Number(report.startup_score || 0));
        chartLabels = reports.slice(0, 8).reverse().map(report => (report.startup_name || 'Report').slice(0, 12));
    }

    const industries = reports.reduce((acc, report) => {
        const key = report.industry || 'Uncategorized';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
    }, {});

    if (window.Chart) {
        const grid = 'rgba(255,255,255,.05)';
        const text = '#94A3B8';
        const canvas = document.getElementById('score-trend-chart');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            const gradient = ctx.createLinearGradient(0, 0, 0, 280);
            gradient.addColorStop(0, 'rgba(234, 179, 8, 0.08)');
            gradient.addColorStop(1, 'rgba(15, 12, 27, 0)');

            // Clean up existing chart instance if any
            const existingChart = Chart.getChart(canvas);
            if (existingChart) existingChart.destroy();

            // Highlight only the final score point
            const pointRadii = chartScores.map((_, i) => i === chartScores.length - 1 ? 6 : 0);
            const pointHoverRadii = chartScores.map((_, i) => i === chartScores.length - 1 ? 8 : 4);
            const pointBackgrounds = chartScores.map((_, i) => i === chartScores.length - 1 ? '#EAB308' : 'rgba(234, 179, 8, 0.3)');
            const pointBorderColors = chartScores.map((_, i) => i === chartScores.length - 1 ? '#FFFFFF' : 'rgba(234, 179, 8, 0.3)');
            const pointBorderWidths = chartScores.map((_, i) => i === chartScores.length - 1 ? 2 : 1);

            new Chart(canvas, {
                type: 'line',
                plugins: [{
                    id: 'lineShadow',
                    beforeDatasetDraw: (chart, args) => {
                        if (args.index === 0) {
                            const chartCtx = chart.ctx;
                            chartCtx.save();
                            chartCtx.shadowColor = 'rgba(234, 179, 8, 0.35)';
                            chartCtx.shadowBlur = 8;
                            chartCtx.shadowOffsetX = 0;
                            chartCtx.shadowOffsetY = 3;
                        }
                    },
                    afterDatasetDraw: (chart, args) => {
                        if (args.index === 0) {
                            chart.ctx.restore();
                        }
                    }
                }],
                data: {
                    labels: chartLabels,
                    datasets: [{
                        label: 'Validation Score',
                        data: chartScores,
                        borderColor: '#EAB308',
                        borderWidth: 3,
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: pointBackgrounds,
                        pointBorderColor: pointBorderColors,
                        pointBorderWidth: pointBorderWidths,
                        pointRadius: pointRadii,
                        pointHoverRadius: pointHoverRadii,
                        pointHoverBackgroundColor: '#EAB308',
                        pointHoverBorderColor: '#FFFFFF',
                        pointHoverBorderWidth: 2,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 1200, easing: 'easeOutQuart' },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#1E1B2E',
                            titleColor: '#EAB308',
                            bodyColor: '#FFFFFF',
                            borderColor: 'rgba(234, 179, 8, 0.3)',
                            borderWidth: 1,
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: false,
                            callbacks: {
                                label: function(context) {
                                    return `Score: ${context.parsed.y}/100${isMock ? ' (Demo)' : ''}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: { grid: { color: grid }, ticks: { color: text } },
                        y: { min: 0, max: 100, grid: { color: grid }, ticks: { color: text } }
                    }
                }
            });
        }

        const indCanvas = document.getElementById('industry-chart');
        if (indCanvas) {
            const indCtx = indCanvas.getContext('2d');
            const existingIndChart = Chart.getChart(indCanvas);
            if (existingIndChart) existingIndChart.destroy();

            const indKeys = Object.keys(industries);
            const indVals = Object.values(industries);

            new Chart(indCanvas, {
                type: 'doughnut',
                data: {
                    labels: indKeys.length ? indKeys : ['Validate Idea'],
                    datasets: [{
                        data: indVals.length ? indVals : [1],
                        backgroundColor: indVals.length ? ['#EAB308', '#3B82F6', '#F59E0B', '#8B5CF6', '#EF4444'] : ['rgba(255,255,255,0.08)'],
                        borderColor: 'rgba(15, 12, 27, 0.8)',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '72%',
                    animation: { animateRotate: true, duration: 1000 },
                    plugins: { 
                        legend: { 
                            position: 'bottom',
                            labels: { color: text, boxWidth: 10, padding: 15 } 
                        } 
                    }
                }
            });
        }
        document.getElementById('score-bars').classList.add('hidden');
        return;
    }

    document.getElementById('industry-fallback').innerHTML = Object.entries(industries).length
        ? Object.entries(industries).map(([name, count]) => `<p><span>${escapeHtml(name)}</span><strong>${count}</strong></p>`).join('')
        : '<p><span>Run analyses to build distribution charts.</span><strong>0</strong></p>';
}

function renderComparisonControls(reports) {
    const a = document.getElementById('compare-a');
    const b = document.getElementById('compare-b');
    if (!a || !b) return;
    const options = reports.length
        ? reports.map(report => `<option value="${escapeHtml(report.id)}">${escapeHtml(report.startup_name || 'Startup')}</option>`).join('')
        : '<option value="">Run analyses to compare</option>';
    a.innerHTML = options;
    b.innerHTML = options;
    if (reports[1]) b.value = reports[1].id;
    const update = () => renderComparison(reports);
    a.addEventListener('change', update);
    b.addEventListener('change', update);
    update();
}

function renderComparison(reports) {
    const output = document.getElementById('comparison-output');
    if (!output) return;

    if (reports.length < 2) {
        output.innerHTML = `
            <div class="compare-empty-state">
                <div class="compare-icon">⇄</div>
                <h3>Comparative Analysis Locked</h3>
                <p>Ideas deserve evidence. Validate at least two startup ideas to view comparative score sheets, market sizing, risk weightings, and funding pipelines side-by-side.</p>
                <a href="analyze.html" class="btn btn-secondary btn-text" style="border: 1px solid var(--line); padding: 8px 14px;">Analyze Another Idea</a>
            </div>
        `;
        return;
    }

    const idA = document.getElementById('compare-a')?.value;
    const idB = document.getElementById('compare-b')?.value;
    const left = reports.find(report => report.id === idA);
    const right = reports.find(report => report.id === idB);

    if (!left || !right) {
        output.innerHTML = '<p>Select two startups from the dropdowns above to compare.</p>';
        return;
    }

    const getTAMVal = (r) => r.tam_sam_som?.tam || r.marketSize?.tam || 'Not specified';
    const getSAMVal = (r) => r.tam_sam_som?.sam || r.marketSize?.sam || 'Not specified';
    const getSOMVal = (r) => r.tam_sam_som?.som || r.marketSize?.som || 'Not specified';
    const getRiskText = (r) => {
        const risks = r.risk_matrix || r.risks || [];
        return risks[0]?.risk || 'Standard market risk';
    };
    const getFundingVal = (r) => r.funding_recommendation || r.funding || 'Not specified';

    const scoreA = Number(left.startup_score || 0);
    const scoreB = Number(right.startup_score || 0);
    const readinessA = Number(left.investor_readiness_score || left.investor_readiness || 0);
    const readinessB = Number(right.investor_readiness_score || right.investor_readiness || 0);

    const scoreDiff = scoreA - scoreB;
    const readinessDiff = readinessA - readinessB;

    let winnerHtml = '';
    if (scoreDiff > 0) {
        winnerHtml = `<strong>${escapeHtml(left.startup_name)} wins on viability</strong>. It exhibits a stronger overall validation rating (+${Math.abs(scoreDiff)} pts) and presents a more aligned beachhead model.`;
    } else if (scoreDiff < 0) {
        winnerHtml = `<strong>${escapeHtml(right.startup_name)} wins on viability</strong>. It shows higher product/market scoring (+${Math.abs(scoreDiff)} pts) with stronger customer signals.`;
    } else {
        winnerHtml = `Both ideas share equal viability ratings. Compare TAM scale and funding needs to make a final resource allocation decision.`;
    }

    output.innerHTML = `
        <div class="comparison-grid">
            <div class="comparison-header-row">
                <div class="metric-label">Dimension</div>
                <div class="compare-col-a">${escapeHtml(left.startup_name)}</div>
                <div class="compare-col-b">${escapeHtml(right.startup_name)}</div>
            </div>
            <div class="comparison-row">
                <div class="metric-label">Score</div>
                <div class="val-a ${scoreDiff >= 0 ? 'winner' : ''}">${scoreA}/100</div>
                <div class="val-b ${scoreDiff <= 0 ? 'winner' : ''}">${scoreB}/100</div>
            </div>
            <div class="comparison-row">
                <div class="metric-label">Readiness</div>
                <div class="val-a ${readinessDiff >= 0 ? 'winner' : ''}">${readinessA}%</div>
                <div class="val-b ${readinessDiff <= 0 ? 'winner' : ''}">${readinessB}%</div>
            </div>
            <div class="comparison-row">
                <div class="metric-label">TAM</div>
                <div class="val-a">${escapeHtml(getTAMVal(left))}</div>
                <div class="val-b">${escapeHtml(getTAMVal(right))}</div>
            </div>
            <div class="comparison-row">
                <div class="metric-label">SAM / SOM</div>
                <div class="val-a">${escapeHtml(getSAMVal(left))} / ${escapeHtml(getSOMVal(left))}</div>
                <div class="val-b">${escapeHtml(getSAMVal(right))} / ${escapeHtml(getSOMVal(right))}</div>
            </div>
            <div class="comparison-row">
                <div class="metric-label">Primary Risk</div>
                <div class="val-a">${escapeHtml(getRiskText(left))}</div>
                <div class="val-b">${escapeHtml(getRiskText(right))}</div>
            </div>
            <div class="comparison-row">
                <div class="metric-label">Funding</div>
                <div class="val-a">${escapeHtml(getFundingVal(left))}</div>
                <div class="val-b">${escapeHtml(getFundingVal(right))}</div>
            </div>
        </div>
        <div class="winner-analysis-card">
            <h4>Winner Analysis</h4>
            <p>${winnerHtml}</p>
        </div>
    `;
}

function renderFounderInsights(reports) {
    const container = document.getElementById('founder-insights');
    if (!container) return;

    if (!reports.length) {
        container.innerHTML = `
            <div class="compare-empty-state">
                <p>Validate your first startup to unlock tactical founder insights.</p>
            </div>
        `;
        return;
    }

    const latest = reports[0];
    const swot = latest.swot || latest.swot_analysis || {};
    const strengths = Array.isArray(swot.strengths) ? swot.strengths.slice(0, 3) : ['Viable problem clarity', 'Beachhead sector opportunity', 'Digital distribution advantage'];
    const weaknesses = Array.isArray(swot.weaknesses) ? swot.weaknesses.slice(0, 3) : ['Verification proof required', 'No early pilot agreements', 'Initial model onboarding friction'];
    const recs = latest.founderRecommendations || latest.founder_recommendations || [];
    const nextAction = recs[0] || 'Conduct 15 target customer discovery interviews to confirm willingness to pay.';

    container.innerHTML = `
        <div class="founder-insights">
            <div class="insight-meta">
                <strong>Focus: ${escapeHtml(latest.startup_name)}</strong>
            </div>
            <div class="insight-swot-summary">
                <div class="insight-swot-block strength">
                    <h5>Strengths</h5>
                    <ul>
                        ${strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                    </ul>
                </div>
                <div class="insight-swot-block weakness">
                    <h5>Weaknesses</h5>
                    <ul>
                        ${weaknesses.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                    </ul>
                </div>
            </div>
            <div class="insight-action-card">
                <h5>Next Best Action</h5>
                <p>${escapeHtml(nextAction)}</p>
            </div>
        </div>
    `;
}

function renderRecommendations(reports) {
    const latest = reports[0];
    const recommendations = latest ? [
        `Prioritize the highest-risk assumption in ${latest.startup_name || 'your latest report'}.`,
        'Convert validation findings into a paid pilot or signed letter of intent.',
        'Refresh the report after customer interviews to track readiness movement.'
    ] : [
        'Validate your first startup idea to unlock personalized recommendations.',
        'Start with a narrow customer segment and a painful workflow.',
        'Use the funding recommendation only after customer evidence exists.'
    ];
    document.getElementById('recommendations').innerHTML = recommendations.map(item => `<p>${escapeHtml(item)}</p>`).join('');
}

function countUp(id, target) {
    const element = document.getElementById(id);
    if (!element) return;
    const end = Number(target) || 0;
    const start = performance.now();
    const duration = 520;
    const tick = now => {
        const progress = Math.min(1, (now - start) / duration);
        element.textContent = Math.round(end * progress);
        if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
}

function renderNotifications(reports) {
    const latest = reports[0];
    const notes = latest ? [
        `Latest report: ${latest.startup_name || 'Startup'} scored ${latest.startup_score || 0}/100.`,
        `Investor readiness: ${latest.investor_readiness_score || latest.investor_readiness || latest.startup_score || 0}/100.`,
        'Next best move: run customer discovery against the highest-risk assumption.'
    ] : [
        'No report activity yet.',
        'Create a validation report to unlock portfolio analytics.',
        'Dashboard data updates automatically after each analysis.'
    ];
    document.getElementById('notifications').innerHTML = notes.map(note => `<p>${escapeHtml(note)}</p>`).join('');
}

function formatDate(value) {
    return value ? new Date(value).toLocaleDateString() : 'Recent';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
