const DRAFT_KEY = 'punchstart_analysis_draft';
const REPORTS_KEY = 'punchstart_reports';

const fields = [
    'startup-name',
    'industry',
    'problem',
    'solution',
    'target-customers',
    'revenue-model',
    'team-size',
    'funding-requirement',
    'business-stage'
];

const requiredByStep = {
    0: ['startup-name', 'industry'],
    1: ['problem'],
    2: ['solution'],
    3: ['target-customers']
};

document.addEventListener('DOMContentLoaded', () => {
    const steps = Array.from(document.querySelectorAll('.wizard-step'));
    const prevBtn = document.getElementById('prev-step');
    const nextBtn = document.getElementById('next-step');
    const runBtn = document.getElementById('run-analysis-btn');
    const progress = document.getElementById('wizard-progress');
    const stepCount = document.getElementById('step-count');
    const stepLabel = document.getElementById('step-label');
    const errorEl = document.getElementById('form-error');
    const loadingOverlay = document.getElementById('analysis-loading');
    const loadingCopy = document.getElementById('loading-copy');
    let currentStep = 0;
    let loadingIndex = 0;

    restoreDraft();
    updateStep();
    fields.forEach(id => document.getElementById(id)?.addEventListener('input', saveDraft));
    fields.forEach(id => document.getElementById(id)?.addEventListener('change', saveDraft));

    prevBtn.addEventListener('click', () => {
        currentStep = Math.max(0, currentStep - 1);
        updateStep();
    });

    nextBtn.addEventListener('click', () => {
        if (!validateStep(currentStep)) return;
        currentStep = Math.min(steps.length - 1, currentStep + 1);
        updateStep();
    });

    runBtn.addEventListener('click', async () => {
        if (!validateAll()) return;
        const startupData = collectStartupData();
        const pipelineSteps = Array.from(document.querySelectorAll('.pipeline-step'));
        const progressBar = document.getElementById('loading-progress-bar');
        
        const updatePipeline = (idx) => {
            pipelineSteps.forEach((step, sIdx) => {
                if (sIdx < idx) {
                    step.className = 'pipeline-step completed';
                } else if (sIdx === idx) {
                    step.className = 'pipeline-step active';
                } else {
                    step.className = 'pipeline-step';
                }
            });
            if (progressBar) {
                progressBar.style.width = `${((idx + 1) / pipelineSteps.length) * 100}%`;
            }
        };

        loadingOverlay.classList.remove('hidden');
        document.querySelector('.loading-card')?.classList.remove('complete');
        let currentPipelineStep = 0;
        updatePipeline(0);
        loadingCopy.textContent = 'Initializing validation pipeline...';

        const timer = setInterval(() => {
            if (currentPipelineStep < 4) {
                currentPipelineStep++;
                updatePipeline(currentPipelineStep);
                loadingCopy.textContent = pipelineSteps[currentPipelineStep]?.querySelector('.step-text')?.textContent || '';
            }
        }, 2200);

        try {
            const result = await runAnalysis(startupData);
            
            clearInterval(timer);
            // Move to step 5: Building investor report
            updatePipeline(5);
            loadingCopy.textContent = 'Building investor report...';
            await new Promise(resolve => setTimeout(resolve, 900));

            const report = {
                ...result,
                startup_name: startupData.startup_name,
                industry: startupData.industry,
                created_at: new Date().toISOString()
            };
            persistReport(report);
            sessionStorage.setItem('currentReport', JSON.stringify(report));
            localStorage.removeItem(DRAFT_KEY);
            
            // Mark all completed
            pipelineSteps.forEach(step => step.className = 'pipeline-step completed');
            if (progressBar) progressBar.style.width = '100%';
            loadingCopy.textContent = 'Validation Complete';
            document.querySelector('.loading-card')?.classList.add('complete');
            await new Promise(resolve => setTimeout(resolve, 900));
            window.location.href = 'results.html';
        } catch (error) {
            console.error('Analysis failed:', error);
            let msg = error.message;
            if (msg === 'Failed to fetch') {
                msg = 'Failed to connect to the server. Please ensure the backend is running, or try disabling adblockers that might block the request.';
            }
            errorEl.textContent = `Analysis failed: ${msg}`;
        } finally {
            clearInterval(timer);
            loadingOverlay.classList.add('hidden');
        }
    });

    document.getElementById('logout-link')?.addEventListener('click', (event) => {
        event.preventDefault();
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        window.location.href = '../index.html';
    });

    function updateStep() {
        steps.forEach((step, index) => step.classList.toggle('active', index === currentStep));
        const active = steps[currentStep];
        stepCount.textContent = `Step ${currentStep + 1} of ${steps.length}`;
        stepLabel.textContent = active.dataset.title;
        progress.style.width = `${((currentStep + 1) / steps.length) * 100}%`;
        prevBtn.disabled = currentStep === 0;
        nextBtn.classList.toggle('hidden', currentStep === steps.length - 1);
        if (currentStep === 7) renderReview();
        errorEl.textContent = '';
    }

    function validateStep(stepIndex) {
        const missing = (requiredByStep[stepIndex] || []).filter(id => !document.getElementById(id).value.trim());
        if (missing.length) {
            errorEl.textContent = 'Complete the required fields before continuing.';
            document.getElementById(missing[0]).focus();
            return false;
        }
        errorEl.textContent = '';
        return true;
    }

    function validateAll() {
        for (const step of Object.keys(requiredByStep).map(Number)) {
            if (!validateStep(step)) {
                currentStep = step;
                updateStep();
                return false;
            }
        }
        return true;
    }
});

function collectStartupData() {
    return {
        startup_name: document.getElementById('startup-name').value.trim(),
        industry: document.getElementById('industry').value,
        problem: document.getElementById('problem').value.trim(),
        solution: document.getElementById('solution').value.trim(),
        target_customers: document.getElementById('target-customers').value.trim(),
        revenue_model: document.getElementById('revenue-model').value,
        team_size: document.getElementById('team-size').value,
        funding_requirement: document.getElementById('funding-requirement').value.trim(),
        business_stage: document.getElementById('business-stage').value
    };
}

function saveDraft() {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(collectStartupData()));
}

function restoreDraft() {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    try {
        const draft = JSON.parse(raw);
        const idMap = {
            startup_name: 'startup-name',
            industry: 'industry',
            problem: 'problem',
            solution: 'solution',
            target_customers: 'target-customers',
            revenue_model: 'revenue-model',
            team_size: 'team-size',
            funding_requirement: 'funding-requirement',
            business_stage: 'business-stage'
        };
        Object.entries(idMap).forEach(([key, id]) => {
            const input = document.getElementById(id);
            if (input && draft[key]) input.value = draft[key];
        });
    } catch (_) {
        localStorage.removeItem(DRAFT_KEY);
    }
}

function renderReview() {
    const data = collectStartupData();
    const labels = {
        startup_name: 'Startup',
        industry: 'Industry',
        business_stage: 'Stage',
        problem: 'Problem',
        solution: 'Solution',
        target_customers: 'Customers',
        revenue_model: 'Revenue',
        funding_requirement: 'Funding'
    };
    document.getElementById('review-panel').innerHTML = Object.entries(labels).map(([key, label]) => `
        <div class="review-item">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(data[key] || 'Founder input pending')}</strong>
        </div>
    `).join('');
}

function persistReport(report) {
    const reports = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
    reports.unshift({
        id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
        ...report
    });
    localStorage.setItem(REPORTS_KEY, JSON.stringify(reports.slice(0, 20)));
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
