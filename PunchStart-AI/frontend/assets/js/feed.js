const POSTS_KEY = 'punchstart_feed_posts';
const REPORTS_KEY = 'punchstart_reports';

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('post-form');
    const search = document.getElementById('feed-search');
    let posts = loadPosts();

    renderFeed(posts);
    renderTrendingIdeas();

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        const title = document.getElementById('post-title').value.trim();
        const body = document.getElementById('post-body').value.trim();
        if (!title || !body) return;
        posts.unshift({
            id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
            title,
            body,
            author: 'Founder',
            createdAt: new Date().toISOString(),
            likes: 0,
            liked: false,
            comments: []
        });
        savePosts(posts);
        form.reset();
        renderFeed(posts);
    });

    search.addEventListener('input', () => {
        const query = search.value.toLowerCase();
        renderFeed(posts.filter(post => `${post.title} ${post.body}`.toLowerCase().includes(query)));
    });

    document.getElementById('logout-link')?.addEventListener('click', (event) => {
        event.preventDefault();
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        window.location.href = '../index.html';
    });
});

function loadPosts() {
    const saved = JSON.parse(localStorage.getItem(POSTS_KEY) || '[]');
    const reports = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
    const reportPosts = reports.slice(0, 4).map(report => ({
        id: `report-${report.id}`,
        title: `${report.startup_name || 'Startup'} validation signal`,
        body: report.investor_attractiveness_analysis || report.executive_summary,
        author: 'PunchStart Insight',
        createdAt: report.created_at || new Date().toISOString(),
        likes: 0,
        liked: false,
        comments: []
    }));
    const existingIds = new Set(saved.map(post => post.id));
    return [...saved, ...reportPosts.filter(post => !existingIds.has(post.id))];
}

function savePosts(posts) {
    const userPosts = posts.filter(post => !String(post.id).startsWith('report-'));
    localStorage.setItem(POSTS_KEY, JSON.stringify(userPosts.slice(0, 50)));
}

function renderFeed(posts) {
    const container = document.getElementById('feed-container');
    if (!posts.length) {
        container.innerHTML = '<div class="empty-feed panel"><h2>No posts yet</h2><p>Create the first founder insight from your validation work.</p></div>';
        return;
    }
    container.innerHTML = posts.map(post => `
        <article class="idea-card" data-id="${escapeHtml(post.id)}">
            <div class="post-meta">
                <div class="founder-avatar">${escapeHtml((post.author || 'F').charAt(0))}</div>
                <div>
                    <strong>${escapeHtml(post.author || 'Founder')}</strong>
                    <span>${formatDate(post.createdAt)}</span>
                </div>
            </div>
            <h2>${escapeHtml(post.title)}</h2>
            <p>${escapeHtml(post.body)}</p>
            <div class="comment-list">${(post.comments || []).map(comment => `<small>${escapeHtml(comment)}</small>`).join('')}</div>
            <div class="idea-actions">
                <button class="action-btn like-btn" type="button">${post.liked ? 'Liked' : 'Like'} ${post.likes || 0}</button>
                <button class="action-btn comment-btn" type="button">Comment</button>
            </div>
        </article>
    `).join('');

    container.querySelectorAll('.idea-card').forEach(card => {
        const post = posts.find(item => item.id === card.dataset.id);
        card.querySelector('.like-btn').addEventListener('click', () => {
            post.liked = !post.liked;
            post.likes = Math.max(0, (post.likes || 0) + (post.liked ? 1 : -1));
            savePosts(posts);
            renderFeed(posts);
        });
        card.querySelector('.comment-btn').addEventListener('click', () => {
            const comment = prompt('Add a comment');
            if (!comment || !comment.trim()) return;
            post.comments = [...(post.comments || []), comment.trim()];
            savePosts(posts);
            renderFeed(posts);
        });
    });
}

function renderTrendingIdeas() {
    const reports = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
    const ideas = reports.length
        ? reports.slice(0, 5).map(report => `${report.industry || 'Startup'}: ${report.startup_name || 'new idea'} scored ${report.startup_score || 0}/100`)
        : [
            'Intelligent workflow copilots for underserved SMB teams',
            'Vertical SaaS with measurable 30-day ROI',
            'Founder tools that convert research into execution'
        ];
    document.getElementById('trending-ideas').innerHTML = ideas.map(idea => `<p>${escapeHtml(idea)}</p>`).join('');
}

function formatDate(value) {
    return value ? new Date(value).toLocaleDateString() : 'Today';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
