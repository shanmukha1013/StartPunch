const PS_REPORTS_KEY = 'punchstart_reports';
let paletteActiveIndex = 0;
let filteredItems = [];

document.addEventListener('DOMContentLoaded', () => {
    injectCommandPalette();
    
    document.addEventListener('keydown', event => {
        const palette = document.getElementById('command-palette');
        const isHidden = !palette || palette.classList.contains('hidden');

        // Ctrl + K open
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            if (isHidden) openCommandPalette();
            else closeCommandPalette();
            return;
        }

        if (!isHidden) {
            if (event.key === 'Escape') {
                closeCommandPalette();
            } else if (event.key === 'ArrowDown') {
                event.preventDefault();
                paletteActiveIndex = (paletteActiveIndex + 1) % Math.max(1, filteredItems.length);
                highlightActiveItem();
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                paletteActiveIndex = (paletteActiveIndex - 1 + filteredItems.length) % Math.max(1, filteredItems.length);
                highlightActiveItem();
            } else if (event.key === 'Enter') {
                event.preventDefault();
                const activeItem = filteredItems[paletteActiveIndex];
                if (activeItem) {
                    triggerCommandItem(activeItem);
                }
            }
        }
    });
});

function injectCommandPalette() {
    if (document.getElementById('command-palette')) return;
    const palette = document.createElement('div');
    palette.id = 'command-palette';
    palette.className = 'command-palette hidden';
    palette.innerHTML = `
        <div class="command-backdrop"></div>
        <section class="command-panel" role="dialog" aria-modal="true" aria-label="Command palette">
            <div class="command-input-row">
                <span class="brand-mark"><span><span class="p">P</span><span class="s">S</span></span></span>
                <input id="command-input" class="command-input" type="search" placeholder="Search reports or jump anywhere..." autocomplete="off">
                <kbd>Esc</kbd>
            </div>
            <div id="command-results" class="command-results"></div>
        </section>
    `;
    document.body.appendChild(palette);
    palette.querySelector('.command-backdrop').addEventListener('click', closeCommandPalette);
    palette.querySelector('#command-input').addEventListener('input', () => {
        paletteActiveIndex = 0;
        renderCommandResults();
    });
    renderCommandResults();
}

function openCommandPalette() {
    const palette = document.getElementById('command-palette');
    if (!palette) return;
    palette.classList.remove('hidden');
    paletteActiveIndex = 0;
    renderCommandResults();
    setTimeout(() => document.getElementById('command-input')?.focus(), 30);
}

function closeCommandPalette() {
    document.getElementById('command-palette')?.classList.add('hidden');
}

function renderCommandResults() {
    const input = document.getElementById('command-input');
    const query = (input?.value || '').toLowerCase();
    const reports = JSON.parse(localStorage.getItem(PS_REPORTS_KEY) || '[]');
    const isReportPage = window.location.pathname.includes('results.html');

    const items = [
        { label: 'Founder Command Center', detail: 'Open portfolio analytics', category: 'Navigation', shortcut: '⌥ D', href: 'dashboard.html' },
        { label: 'New Analysis', detail: 'Validate a startup idea', category: 'Navigation', shortcut: '⌥ N', href: 'analyze.html' },
        { label: 'Founder Feed', detail: 'Insights and activity', category: 'Navigation', shortcut: '⌥ F', href: 'feed.html' },
        
        { label: 'Compare Startups', detail: 'Jump to comparison controls', category: 'Actions', shortcut: '⌥ C', href: 'dashboard.html#compare-a' },
        { label: 'Export PDF', detail: 'Export this report as professional PDF', category: 'Actions', shortcut: '⌥ P', action: 'export_pdf' },
        { label: 'Share Report', detail: 'Copy link or download report', category: 'Actions', shortcut: '⌥ S', action: 'share_report' },
        
        ...reports.map(report => ({
            label: report.startup_name || 'Startup report',
            detail: `${report.industry || 'Report'} - Score ${report.startup_score || 0}/100`,
            category: 'Recent Startup Reports',
            shortcut: '↵',
            href: `results.html?id=${encodeURIComponent(report.id)}`
        }))
    ];

    filteredItems = items.filter(item => {
        if (!isReportPage && (item.action === 'export_pdf' || item.action === 'share_report')) {
            return false;
        }
        return `${item.label} ${item.detail} ${item.category}`.toLowerCase().includes(query);
    });

    const results = document.getElementById('command-results');
    if (!results) return;

    if (!filteredItems.length) {
        results.innerHTML = `
            <div class="command-empty">
                <strong>No matching command</strong>
                <span>Try a report name, page, or quick action.</span>
            </div>
        `;
        return;
    }

    let currentCategory = '';
    let html = '';
    let flatIndex = 0;

    filteredItems.forEach((item) => {
        if (item.category !== currentCategory) {
            currentCategory = item.category;
            html += `<div class="command-group-header">${escapeCommandHtml(currentCategory)}</div>`;
        }
        
        const isSelected = flatIndex === paletteActiveIndex;
        html += `
            <div class="command-item ${isSelected ? 'selected' : ''}" data-index="${flatIndex}">
                <div class="command-item-main">
                    <strong>${escapeCommandHtml(item.label)}</strong>
                    <span>${escapeCommandHtml(item.detail)}</span>
                </div>
                <div class="command-item-meta">
                    ${item.shortcut ? `<kbd>${item.shortcut}</kbd>` : ''}
                </div>
            </div>
        `;
        flatIndex++;
    });

    results.innerHTML = html;

    // Attach clicks
    results.querySelectorAll('.command-item').forEach(el => {
        el.addEventListener('click', () => {
            const idx = parseInt(el.dataset.index);
            triggerCommandItem(filteredItems[idx]);
        });
    });
}

function highlightActiveItem() {
    const results = document.getElementById('command-results');
    if (!results) return;
    results.querySelectorAll('.command-item').forEach((el, idx) => {
        el.classList.toggle('selected', idx === paletteActiveIndex);
        if (idx === paletteActiveIndex) {
            el.scrollIntoView({ block: 'nearest' });
        }
    });
}

function triggerCommandItem(item) {
    closeCommandPalette();
    if (item.href) {
        window.location.href = resolveCommandHref(item.href);
    } else if (item.action) {
        if (item.action === 'export_pdf') {
            window.print();
        } else if (item.action === 'share_report') {
            document.getElementById('share-report')?.click();
        }
    }
}

function resolveCommandHref(href) {
    const inPages = window.location.pathname.includes('/pages/');
    if (href === 'dashboard.html' || href === 'analyze.html' || href === 'feed.html' || href.startsWith('results.html')) {
        return inPages ? href : `pages/${href}`;
    }
    return href;
}

function escapeCommandHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
