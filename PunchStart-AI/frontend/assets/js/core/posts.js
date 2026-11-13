// Post card, actions, comments and composer — shared by feed, profile, community, startup and post pages.
import { del, get, post as apiPost, uploadImage } from './api.js';
import { $, avatar, confirmDialog, esc, html, icon, modal, person, raw, render, richText, timeAgo, titleCase, toast,
  toastError, withBusy } from './ui.js';

const KIND_LABEL = { idea: 'Startup idea', update: 'Progress update', milestone: 'Milestone', article: 'Article', question: 'Question', news: 'Industry news' };

function videoEmbed(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '');
    let src = null;
    if (host === 'youtu.be') src = `https://www.youtube-nocookie.com/embed/${u.pathname.slice(1)}`;
    else if (host === 'youtube.com' && u.searchParams.get('v')) src = `https://www.youtube-nocookie.com/embed/${u.searchParams.get('v')}`;
    else if (host === 'vimeo.com' && /^\/\d+/.test(u.pathname)) src = `https://player.vimeo.com/video${u.pathname}`;
    else if (host === 'loom.com' && u.pathname.startsWith('/share/')) src = `https://www.loom.com/embed/${u.pathname.split('/')[2]}`;
    return src ? html`<iframe class="video-frame" src="${src}" title="Embedded video" loading="lazy" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>` : '';
  } catch { return ''; }
}

function body(p, { compact = false } = {}) {
  const text = compact && p.body.length > 420 ? `${p.body.slice(0, 420)}…` : p.body;
  return html`${p.title ? html`<div class="post-title">${p.title}</div>` : ''}
    ${p.body ? html`<div class="post-body">${richText(text)}</div>` : ''}
    ${p.media?.length ? html`<div class="post-media">${p.media.map((m) => html`<img src="${m.url}" alt="Post image" loading="lazy">`)}</div>` : ''}
    ${p.video_url ? videoEmbed(p.video_url) : ''}
    ${p.link_url ? html`<a class="post-link" href="${p.link_url}" target="_blank" rel="noopener noreferrer nofollow">${icon('link')}<span>${p.link_url}</span></a>` : ''}`;
}

export function postCard(p, { compact = true } = {}) {
  const repost = p.repost_of;
  return html`<article class="card post rise" data-post="${p.id}" data-own="${p.viewer.is_author ? '1' : ''}">
    ${p.hidden ? html`<div class="notice" style="margin-bottom:10px">${icon('shield')}<div><strong>Hidden by a moderator</strong>Only you can see this post.</div></div>` : ''}
    <div class="post-head">
      <div class="grow">${person(p.author, html`${timeAgo(p.created_at)}${p.edited ? ' · edited' : ''}${p.visibility === 'followers' ? ' · followers only' : ''}${p.community ? html` · in <a href="community.html?c=${p.community.slug}">${p.community.name}</a>` : ''}`)}</div>
      ${p.kind !== 'post' ? html`<span class="chip ${p.kind === 'idea' ? 'chip--yellow' : ''}">${KIND_LABEL[p.kind] || titleCase(p.kind)}</span>` : ''}
      <div class="menu-wrap"><button class="icon-btn" data-act="menu" aria-label="Post options">${icon('more')}</button></div>
    </div>
    ${p.startup ? html`<a class="chip chip--ink" href="startup.html?id=${p.startup.id}" style="margin-bottom:8px">${icon('rocket')} ${p.startup.name}</a>` : ''}
    ${body(p, { compact })}
    ${repost ? html`<div class="repost-box">${person(repost.author, timeAgo(repost.created_at))}<div style="margin-top:8px">${body(repost, { compact: true })}</div><a class="small" href="post.html?id=${repost.id}">Open original</a></div>` : ''}
    ${p.repost_unavailable ? html`<div class="repost-box muted small">The original post is no longer available.</div>` : ''}
    <div class="post-actions">
      <button class="act like" data-act="like" aria-pressed="${p.viewer.liked}" aria-label="Like">${icon('heart')}<span>${p.counts.likes || ''}</span></button>
      <button class="act" data-act="comments" aria-label="Comments">${icon('comment')}<span>${p.counts.comments || ''}</span></button>
      <button class="act" data-act="repost" aria-pressed="${p.viewer.reposted}" aria-label="Repost">${icon('repeat')}<span>${p.counts.reposts || ''}</span></button>
      <button class="act" data-act="bookmark" aria-pressed="${p.viewer.bookmarked}" aria-label="Bookmark">${icon('bookmark')}</button>
      <button class="act" data-act="share" aria-label="Share">${icon('share')}</button>
      ${p.counts.comments >= 3 ? html`<button class="act" data-act="summarize" style="margin-left:auto;color:var(--p-600)">${icon('sparkles')}<span>Summarize discussion</span></button>` : ''}
    </div>
    <div class="ai-summary"></div>
    <div class="comments hidden"></div>
  </article>`;
}

function commentHtml(c, byParent, me) {
  const replies = byParent.get(c.id) || [];
  return html`<div class="comment" data-comment="${c.id}">${avatar(c.author, 'sm')}
    <div class="grow"><div class="bubble"><strong class="small">${c.author ? html`<a href="profile.html?u=${c.author.handle}">${c.author.name}</a>` : 'Member'}</strong>
      <span class="muted tiny"> · ${timeAgo(c.created_at)}</span>${c.hidden ? html`<p class="muted"><em>Hidden by a moderator.</em></p>` : html`<p>${richText(c.body)}</p>`}</div>
      <div class="comment-tools"><button data-reply="${c.id}">Reply</button>${c.is_author || me?.role === 'admin' ? html`<button data-delete-comment="${c.id}">Delete</button>` : html`<button data-report-comment="${c.id}">Report</button>`}</div>
      ${replies.length ? html`<div class="comment-replies">${replies.map((r) => commentHtml(r, byParent, me))}</div>` : ''}
    </div></div>`;
}

async function loadComments(card, postId, me) {
  const box = $('.comments', card);
  box.classList.remove('hidden');
  render(box, html`<div class="skeleton sk-line"></div>`);
  const { comments } = await get(`/posts/${postId}/comments`);
  const byParent = new Map();
  comments.forEach((c) => { const k = c.parent_id || 'root'; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k).push(c); });
  render(box, html`${(byParent.get('root') || []).map((c) => commentHtml(c, byParent, me))}
    <form class="row" data-comment-form style="margin-top:8px;flex-wrap:nowrap">
      <input class="input" name="body" placeholder="Write a comment…" maxlength="4000" aria-label="Write a comment" required>
      <input type="hidden" name="parent_id"><button class="btn btn--sm">Post</button></form>
    <div class="reply-hint small muted hidden"></div>`);
  const form = $('[data-comment-form]', box);
  form.body.addEventListener('input', () => { if (!form.body.value) form.parent_id.value = ''; });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    try {
      await apiPost(`/posts/${postId}/comments`, { body: data.body, parent_id: data.parent_id || null });
      const count = $('[data-act="comments"] span', card);
      count.textContent = String((Number(count.textContent) || 0) + 1);
      await loadComments(card, postId, me);
    } catch (error) { toastError(error); }
  });
  if (box.dataset.bound) return;
  box.dataset.bound = '1';
  box.addEventListener('click', async (e) => {
    const form = $('[data-comment-form]', box);
    const reply = e.target.closest('[data-reply]');
    if (reply) {
      form.parent_id.value = reply.dataset.reply;
      const hint = $('.reply-hint', box);
      hint.textContent = 'Replying to a comment — clear the box to cancel.';
      hint.classList.remove('hidden');
      form.body.focus();
    }
    const remove = e.target.closest('[data-delete-comment]');
    if (remove && await confirmDialog('Delete this comment and its replies?', { confirm: 'Delete' })) {
      try { await del(`/comments/${remove.dataset.deleteComment}`); await loadComments(card, postId, me); } catch (error) { toastError(error); }
    }
    const rep = e.target.closest('[data-report-comment]');
    if (rep) reportDialog('comment', rep.dataset.reportComment);
  });
}

export function reportDialog(entityType, entityId) {
  modal({
    title: 'Report content',
    body: html`<div class="field"><label for="rr">Reason</label><select class="select" id="rr">
      ${['spam', 'harassment', 'hate', 'misinformation', 'inappropriate', 'impersonation', 'other'].map((r) => html`<option value="${r}">${titleCase(r)}</option>`)}</select></div>
      <div class="field"><label for="rd">Details <span class="hint">(optional)</span></label><textarea class="textarea" id="rd" maxlength="1000"></textarea></div>`,
    actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Send report', kind: 'btn--yellow', onClick: async (m) => {
      await apiPost('/moderation/reports', { entity_type: entityType, entity_id: entityId, reason: $('#rr', m).value, details: $('#rd', m).value });
      toast('Thanks — a moderator will review this.');
    } }],
  });
}

/** Wire up interactions for every post card inside `root`. */
export function bindPosts(root, { me, onRemoved } = {}) {
  root.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const card = btn.closest('[data-post]');
    const id = card.dataset.post;
    const act = btn.dataset.act;
    try {
      if (act === 'like' || act === 'bookmark') {
        const on = btn.getAttribute('aria-pressed') === 'true';
        await (on ? del(`/posts/${id}/${act}`) : apiPost(`/posts/${id}/${act}`));
        btn.setAttribute('aria-pressed', String(!on));
        if (act === 'like') {
          const span = $('span', btn);
          const n = (Number(span.textContent) || 0) + (on ? -1 : 1);
          span.textContent = n > 0 ? String(n) : '';
        } else toast(on ? 'Removed from bookmarks' : 'Saved to bookmarks');
      } else if (act === 'comments') {
        const box = $('.comments', card);
        if (box.classList.contains('hidden')) await loadComments(card, id, me);
        else box.classList.add('hidden');
      } else if (act === 'repost') {
        modal({ title: 'Repost', body: html`<p class="muted small">Share this post with your followers. Add your perspective (optional).</p>
          <textarea class="textarea" id="rp-text" maxlength="2000" placeholder="Why does this matter?"></textarea>`,
          actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Repost', kind: 'btn--yellow', onClick: async (m) => {
            await apiPost(`/posts/${id}/repost`, { comment: $('#rp-text', m).value });
            const span = $('span', btn);
            span.textContent = String((Number(span.textContent) || 0) + 1);
            btn.setAttribute('aria-pressed', 'true');
            toast('Reposted to your followers');
          } }] });
      } else if (act === 'share') {
        const url = new URL(`post.html?id=${id}`, location.href).href;
        try { await navigator.clipboard.writeText(url); toast('Link copied — only signed-in members can view it'); }
        catch { modal({ title: 'Share link', body: html`<input class="input" value="${url}" readonly>` }); }
      } else if (act === 'summarize') {
        await withBusy(btn, async () => {
          const s = await apiPost(`/posts/${id}/summarize`);
          render($('.ai-summary', card), html`<div class="notice notice--ai" style="margin-top:12px">${icon('sparkles')}<div>
            <strong>AI summary of ${s.comment_count} comments · ${titleCase(s.sentiment)}</strong>${s.summary}
            ${s.key_points?.length ? html`<ul class="small" style="margin:6px 0 0;padding-left:18px">${s.key_points.map((k) => html`<li>${k}</li>`)}</ul>` : ''}
            ${s.open_questions?.length ? html`<p class="small" style="margin:6px 0 0"><b>Open questions:</b> ${s.open_questions.join(' · ')}</p>` : ''}
            <p class="tiny muted" style="margin:6px 0 0">Generated by ${s.model} from the comments only.</p></div></div>`);
        });
      } else if (act === 'menu') {
        e.stopPropagation();
        document.querySelectorAll('.post-menu').forEach((m) => m.remove());
        const menu = document.createElement('div');
        menu.className = 'menu post-menu';
        const own = card.dataset.own === '1';
        render(menu, html`<a href="post.html?id=${id}">${icon('external')} Open post</a>
          ${own || me?.role === 'admin' ? html`<button data-menu="delete">${icon('trash')} Delete post</button>` : html`<button data-menu="report">${icon('flag')} Report</button>`}`);
        btn.parentElement.append(menu);
        menu.addEventListener('click', async (ev) => {
          const choice = ev.target.closest('[data-menu]')?.dataset.menu;
          menu.remove();
          if (choice === 'report') reportDialog('post', id);
          if (choice === 'delete' && await confirmDialog('Delete this post permanently?', { confirm: 'Delete' })) {
            await del(`/posts/${id}`);
            card.remove();
            toast('Post deleted');
            onRemoved?.(id);
          }
        });
        setTimeout(() => document.addEventListener('click', () => menu.remove(), { once: true }));
      }
    } catch (error) {
      toastError(error);
    }
  });
}

/** Composer. options: {communities: [{slug,name}], defaultCommunity, startupId, onPosted} */
export function composer(container, me, { communities = [], defaultCommunity = null, startupId = null, onPosted, placeholder } = {}) {
  let media = [];
  render(container, html`<form class="card" id="composer" style="margin-bottom:16px">
    <div class="composer">${avatar(me)}<div class="grow">
      <input class="input" name="title" maxlength="200" placeholder="Title (optional)" aria-label="Post title" style="margin-bottom:8px">
      <textarea class="textarea" name="body" maxlength="10000" placeholder="${placeholder || 'Share an idea, progress update, question or insight. Use #hashtags.'}" aria-label="Post text"></textarea>
      <div class="composer-preview"></div>
      <div class="link-fields hidden" style="margin-top:8px;display:grid;gap:8px">
        <input class="input" name="link_url" placeholder="Link (https://…)" aria-label="Link URL">
        <input class="input" name="video_url" placeholder="Video link (YouTube, Vimeo or Loom)" aria-label="Video URL">
      </div>
      <div class="composer-tools">
        <select class="select" name="kind" aria-label="Post type" style="width:auto;padding:7px 10px">
          <option value="post">Post</option><option value="idea">Startup idea</option><option value="update">Progress update</option>
          <option value="milestone">Milestone</option><option value="question">Question</option><option value="article">Article</option><option value="news">Industry news</option>
        </select>
        ${communities.length ? html`<select class="select" name="community" aria-label="Community" style="width:auto;padding:7px 10px">
          <option value="">No community</option>${communities.map((c) => html`<option value="${c.slug}" ${c.slug === defaultCommunity ? raw('selected') : ''}>${c.name}</option>`)}</select>` : ''}
        <select class="select" name="visibility" aria-label="Visibility" style="width:auto;padding:7px 10px"><option value="public">Everyone</option><option value="followers">Followers</option></select>
        <label class="icon-btn" title="Add image">${icon('image')}<input type="file" accept="image/png,image/jpeg,image/gif,image/webp" class="sr-only" name="file"></label>
        <button type="button" class="icon-btn" data-links title="Add link or video">${icon('link')}</button>
        <button type="button" class="btn btn--sm btn--ai" data-improve title="Get AI feedback before publishing">${icon('sparkles')} Improve</button>
        <span class="grow"></span>
        <button class="btn btn--yellow btn--sm" data-busy="Posting">${icon('send')} Publish</button>
      </div>
    </div></div></form>`);
  const form = $('#composer', container);
  const preview = $('.composer-preview', form);
  const drawPreview = () => render(preview, html`${media.map((m, i) => html`<span style="position:relative"><img src="${m.url}" alt="Attachment"><button type="button" class="icon-btn" data-rm="${i}" aria-label="Remove image" style="position:absolute;top:-8px;right:-8px;background:var(--k-900);color:#fff;width:24px;height:24px">${icon('x')}</button></span>`)}`);
  preview.addEventListener('click', (e) => { const b = e.target.closest('[data-rm]'); if (b) { media.splice(Number(b.dataset.rm), 1); drawPreview(); } });
  form.file.addEventListener('change', async () => {
    const file = form.file.files[0];
    form.file.value = '';
    if (!file) return;
    if (media.length >= 4) return toast('Up to 4 images per post', 'error');
    try { media.push(await uploadImage(file)); drawPreview(); } catch (error) { toastError(error); }
  });
  $('[data-links]', form).addEventListener('click', () => $('.link-fields', form).classList.toggle('hidden'));
  $('[data-improve]', form).addEventListener('click', async (e) => {
    if (form.body.value.trim().length < 20) return toast('Write at least a couple of sentences first.', 'error');
    await withBusy(e.currentTarget, async () => {
      try {
        const r = await apiPost('/ai/improve-idea', { title: form.title.value, body: form.body.value });
        modal({ title: 'AI feedback on your post', wide: true, body: html`<div class="stack">
          <div class="row"><span class="ai-mark">${icon('sparkles')} Clarity ${r.clarity_score}/10</span><span class="tiny muted">by ${r.model} · nothing is posted automatically</span></div>
          ${r.confidentiality_warnings?.length ? html`<div class="notice">${icon('lock')}<div><strong>Consider keeping private</strong>${r.confidentiality_warnings.join(' · ')}</div></div>` : ''}
          ${r.strengths?.length ? html`<div><b>Strengths</b><ul>${r.strengths.map((s) => html`<li>${s}</li>`)}</ul></div>` : ''}
          ${r.missing?.length ? html`<div><b>What's missing</b><ul>${r.missing.map((s) => html`<li>${s}</li>`)}</ul></div>` : ''}
          ${r.questions_readers_will_ask?.length ? html`<div><b>Readers will ask</b><ul>${r.questions_readers_will_ask.map((s) => html`<li>${s}</li>`)}</ul></div>` : ''}
          <div class="card card--ai"><b>${r.suggested_title}</b><p class="post-body" style="margin-top:6px">${r.suggested_body}</p></div></div>`,
          actions: [{ label: 'Keep mine', kind: 'btn--ghost' }, { label: 'Use suggestion', kind: 'btn--ai', onClick: () => {
            form.title.value = r.suggested_title || form.title.value;
            form.body.value = r.suggested_body || form.body.value;
          } }] });
      } catch (error) { toastError(error); }
    });
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    if (!data.body.trim() && !data.title.trim() && !media.length) return toast('Write something first.', 'error');
    await withBusy($('button[data-busy]', form), async () => {
      try {
        const created = await apiPost('/posts', { kind: data.kind, title: data.title, body: data.body, media_ids: media.map((m) => m.id),
          link_url: data.link_url || '', video_url: data.video_url || '', community: data.community || defaultCommunity || null,
          startup_id: startupId, visibility: data.visibility });
        form.reset();
        media = [];
        drawPreview();
        toast('Published');
        onPosted?.(created);
      } catch (error) { toastError(error); }
    });
  });
}

export function renderPostList(container, posts, { me, append = false, empty } = {}) {
  const markup = html`${posts.map((p) => postCard(p))}`;
  if (append) container.insertAdjacentHTML('beforeend', markup.html);
  else if (!posts.length && empty) render(container, empty);
  else render(container, markup);
  if (!container.dataset.bound) { bindPosts(container, { me }); container.dataset.bound = '1'; }
}

export { esc };
