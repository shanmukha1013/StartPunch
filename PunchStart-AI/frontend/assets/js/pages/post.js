import { get } from '../core/api.js';
import { postCard, bindPosts } from '../core/posts.js';
import { boot } from '../core/shell.js';
import { $, emptyState, html, icon, param, render } from '../core/ui.js';

const { page, user } = await boot({ active: 'feed', title: 'Post' });
try {
  const p = await get(`/posts/${encodeURIComponent(param('id') || '')}`);
  render(page, html`<div style="max-width:760px;margin:0 auto"><a class="btn btn--quiet btn--sm" href="feed.html" style="margin-bottom:12px">${icon('back')} Feed</a>
    <div id="post">${postCard(p, { compact: false })}</div></div>`);
  bindPosts($('#post'), { me: user, onRemoved: () => { location.href = 'feed.html'; } });
  $('#post [data-act="comments"]').click();
} catch (error) {
  render(page, emptyState({ iconName: 'feed', title: 'Post not available', text: 'It may have been deleted, hidden, or shared only with followers.', action: html`<a class="btn" href="feed.html">Back to feed</a>` }));
}
