'use strict';
// Trackrecord front-end. No framework, no innerHTML with data: every text goes through textContent.

const state = {csrf: null, user: null, today: null, demoControls: false, session: null, cited: new Set()};
const ROLE = {consultant: 'Consultant', owner: 'Documenteigenaar', manager: 'Kennisbeheerder'};
const HOME = {consultant: '#/tickets', owner: '#/documents', manager: '#/dashboard'};
const QUADRANT = {dangerous: 'Gevaarlijk', broken: 'Kapot', unclear: 'Onduidelijk', reliable: 'Betrouwbaar', insufficient: 'Nog geen trackrecord'};
const SVG_NS = 'http://www.w3.org/2000/svg';

// ---------- helpers ----------
function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  setAttrs(node, attrs);
  append(node, children);
  return node;
}
function s(tag, attrs, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  setAttrs(node, attrs);
  append(node, children);
  return node;
}
function setAttrs(node, attrs) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.setAttribute('class', value);
    else if (key.startsWith('on')) { if (typeof value === 'function') node.addEventListener(key.slice(2), value); }
    else node.setAttribute(key, value === true ? '' : String(value));
  }
}
function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}
const pct = value => `${Math.round(value * 100)}%`;
const monthLabel = month => new Date(`${month}-01T00:00:00`).toLocaleDateString('nl-BE', {month: 'short'});
const dateLabel = iso => new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString('nl-BE', {day: 'numeric', month: 'long', year: 'numeric'});
const badge = (quadrant, label) => h('span', {class: `badge q-${quadrant}`}, label || QUADRANT[quadrant]);

function toast(message) {
  const node = document.getElementById('toast');
  const dialog = document.getElementById('reader');
  (dialog.open ? dialog : document.body).append(node);   // stay above the modal backdrop
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 2600);
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf || ''},
    body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && path !== '/api/login' && path !== '/api/me') {
    state.user = null;
    renderLogin('Je sessie is verlopen. Log opnieuw in.');
    throw new Error('Niet ingelogd.');
  }
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail
      : Array.isArray(data.detail) ? data.detail.map(item => item.msg).join(' · ') : 'Er ging iets mis.';
    throw new Error(detail);
  }
  return data;
}

// ---------- shell ----------
function shell(active, ...content) {
  const links = {
    consultant: [['#/tickets', 'Mijn tickets']],
    owner: [['#/documents', 'Mijn documenten']],
    manager: [['#/dashboard', 'Overzicht'], ['#/documents', 'Alle documenten']],
  }[state.user.role];
  const root = document.getElementById('app');
  root.replaceChildren(
    h('div', {class: 'fictive'}, 'Prototype met volledig fictieve klanten, mensen, documenten en payrollregels. Geen SD Worx-beleid of payrolladvies.'),
    h('header', {class: 'topbar'}, h('div', {class: 'topbar-inner'},
      h('a', {class: 'brand', href: HOME[state.user.role]}, logo(), 'trackrecord'),
      h('nav', {class: 'nav', 'aria-label': 'Hoofdmenu'},
        links.map(([href, label]) => h('a', {href, class: active === href ? 'active' : null, 'aria-current': active === href ? 'page' : null}, label))),
      h('div', {class: 'userbox'},
        h('span', null, state.user.name), h('span', {class: 'role-pill'}, ROLE[state.user.role]),
        h('button', {class: 'link-button', type: 'button', onclick: logout}, 'Uitloggen')))),
    h('main', null, content));
  window.scrollTo(0, 0);
}
function logo() {
  return s('svg', {class: 'brand-mark', viewBox: '0 0 32 32', 'aria-hidden': 'true'},
    s('rect', {width: 32, height: 32, rx: 7, fill: '#22335a'}),
    s('path', {d: 'M7 22 L13 15 L18 19 L25 9', fill: 'none', stroke: '#f4b860', 'stroke-width': 3, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}),
    s('circle', {cx: 25, cy: 9, r: 2.6, fill: '#f4b860'}));
}
function loading(active, text = 'Laden…') { shell(active, h('p', {class: 'empty'}, text)); }
function failure(active, error) { shell(active, h('div', {class: 'error-box', role: 'alert'}, error.message)); }
function pageHead(eyebrow, title, lede, ...side) {
  return h('div', {class: 'page-head'},
    h('div', null, h('div', {class: 'eyebrow'}, eyebrow), h('h1', null, title), lede ? h('p', {class: 'lede'}, lede) : null),
    side.length ? h('div', null, side) : null);
}

// ---------- login ----------
function renderLogin(message) {
  const error = h('div', {class: 'error-box', role: 'alert', hidden: !message}, message || '');
  const username = h('input', {id: 'username', autocomplete: 'username', required: true, maxlength: 40, autocapitalize: 'none'});
  const password = h('input', {id: 'password', type: 'password', autocomplete: 'current-password', required: true, maxlength: 200});
  const submit = h('button', {class: 'btn primary', type: 'submit'}, 'Inloggen');
  const form = h('form', {class: 'login-card', onsubmit: async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const result = await api('/api/login', {username: username.value.trim().toLowerCase(), password: password.value});
      state.csrf = result.csrf;
      await loadMe();
      if (location.hash === HOME[state.user.role]) route();
      else location.hash = HOME[state.user.role];
    } catch (err) {
      error.textContent = err.message; error.hidden = false; submit.disabled = false;
    }
  }},
    h('div', {class: 'eyebrow'}, 'SD Worx-challenge · prototype'),
    h('h2', null, 'Inloggen'),
    h('p', {class: 'muted small'}, 'Elke rol ziet iets anders: tickets, documentdossiers of het organisatie-overzicht.'),
    error,
    h('div', {class: 'field'}, h('label', {for: 'username'}, 'Gebruikersnaam'), username),
    h('div', {class: 'field'}, h('label', {for: 'password'}, 'Wachtwoord'), password),
    h('div', {class: 'btn-row'}, submit),
    h('div', {class: 'hint'},
      h('strong', null, 'Demo-accounts: '), 'sara (consultant), an (documenteigenaar), kim (kennisbeheerder). ',
      'Het wachtwoord staat lokaal in ', h('code', null, 'data/demo-login.txt'), '.'));
  document.getElementById('app').replaceChildren(h('div', {class: 'login-wrap'},
    h('section', {class: 'login-story'},
      h('div', {class: 'brand'}, logo(), 'trackrecord'),
      h('h1', null, 'Vertrouwen wordt niet verklaard, ', h('em', null, 'het wordt verdiend.')),
      h('div', {class: 'story-steps'},
        h('div', null, h('strong', null, 'Find it'), 'Waar zoeken mensen en vinden ze niets? Dan ontbreekt er kennis.'),
        h('div', null, h('strong', null, 'Understand it'), 'Twijfelen ze nog na het lezen? Dan is het document onduidelijk.'),
        h('div', null, h('strong', null, 'Trust it'), 'Loopt het achteraf mis? Dan is het fout, of fout in een bepaalde situatie.'))),
    h('section', {class: 'login-panel'}, form)));
  username.focus();
}
async function loadMe() {
  const me = await api('/api/me');
  Object.assign(state, {user: me.user, csrf: me.csrf, today: me.today, demoControls: me.demo_controls});
}
async function logout() {
  try { await api('/api/logout', {}); } catch (_) { /* already logged out */ }
  state.user = null; state.csrf = null; location.hash = '';
  renderLogin();
}

// ---------- consultant ----------
async function renderTickets() {
  loading('#/tickets');
  try {
    const tickets = await api('/api/tickets');
    shell('#/tickets',
      pageHead('Consultant', 'Open tickets in jouw portefeuille', 'Open een ticket. Bij elke bron zie je hoe ze het in de praktijk deed, voor situaties zoals de jouwe.'),
      tickets.length ? h('div', {class: 'ticket-grid'}, tickets.map(ticket => h('a', {class: 'card ticket-card', href: `#/ticket/${ticket.id}`},
        h('div', {class: 'meta'}, h('span', {class: 'strong'}, ticket.topic_label), h('span', null, ticket.statute), h('span', null, ticket.pc)),
        h('h3', null, ticket.subject),
        h('p', {class: 'muted small'}, `${ticket.client_name} · ${dateLabel(ticket.opened_at)}`)))) : h('p', {class: 'empty'}, 'Geen open tickets.'));
  } catch (err) { if (state.user) failure('#/tickets', err); }
}

async function renderTicket(ticketId) {
  loading('#/tickets');
  try {
    const data = await api(`/api/tickets/${ticketId}`);
    if (!state.session || state.session.ticket !== ticketId) {
      const session = await api(`/api/tickets/${ticketId}/sessions`, {});
      state.session = {ticket: ticketId, id: session.session_id};
      state.cited = new Set();
    }
    const ticket = data.ticket;
    const results = h('div');
    const citedBox = h('div', {class: 'cited'});
    const refreshCited = () => citedBox.replaceChildren(...[...state.cited].map(title => h('span', null, '✓ ' + title)));
    const showResults = (items, heading) => {
      results.replaceChildren(h('p', {class: 'eyebrow'}, heading),
        ...(items.length ? items.map(item => docCard(item, refreshCited))
          : [h('p', {class: 'empty'}, 'Geen documenten gevonden. Dit zoekwerk telt mee als signaal dat hier kennis ontbreekt.')]));
    };
    const query = h('input', {type: 'search', value: data.suggested_query, 'aria-label': 'Zoek in de kennisbank', maxlength: 200});
    const searchForm = h('form', {class: 'search', onsubmit: async event => {
      event.preventDefault();
      if (query.value.trim().length < 2) return;
      try {
        const found = await api('/api/search', {session_id: state.session.id, query: query.value.trim()});
        showResults(found.results, `Zoekresultaten voor “${query.value.trim()}”`);
      } catch (err) { toast(err.message); }
    }}, query, h('button', {class: 'btn primary', type: 'submit'}, 'Zoek'));
    showResults(data.suggestions, `Kennis over ${data.topic_label.toLowerCase()} voor deze klant`);

    const question = h('textarea', {id: 'teams-question', maxlength: 500, rows: 3, placeholder: 'Bijvoorbeeld: loopt het vakantiegeld van arbeiders hier via de vakantiekas?'});
    const ask = h('form', {class: 'card stack', onsubmit: async event => {
      event.preventDefault();
      if (question.value.trim().length < 3) return;
      try {
        await api('/api/events', {session_id: state.session.id, type: 'teams_question', text: question.value.trim()});
        question.value = '';
        toast('Vraag gedeeld (gesimuleerd). Ze telt mee als twijfelsignaal.');
      } catch (err) { toast(err.message); }
    }},
      h('h2', null, 'Twijfel je nog?'),
      h('p', {class: 'muted small'}, 'Stel je vraag aan collega\'s. Trackrecord bewaart geen namen: de vraag telt alleen mee als signaal bij dit onderwerp. Persoonsgegevens worden automatisch verwijderd.'),
      h('div', {class: 'field'}, h('label', {for: 'teams-question'}, 'Vraag in Teams (gesimuleerd)'), question),
      h('div', {class: 'btn-row'}, h('button', {class: 'btn', type: 'submit'}, 'Stel vraag')));

    shell('#/tickets',
      h('p', {class: 'small'}, h('a', {href: '#/tickets'}, '← Alle tickets')),
      pageHead(`Ticket ${ticket.id}`, ticket.subject, null),
      h('div', {class: 'grid-main'},
        h('div', {class: 'stack'},
          h('section', {class: 'card'},
            h('h2', null, 'Context van het ticket'),
            h('dl', {class: 'facts'},
              h('dt', null, 'Klant'), h('dd', null, ticket.client_name),
              h('dt', null, 'Land'), h('dd', null, ticket.country === 'BE' ? 'België' : 'Nederland'),
              h('dt', null, 'Paritair comité'), h('dd', null, ticket.pc),
              h('dt', null, 'Statuut'), h('dd', null, ticket.statute),
              h('dt', null, 'Onderwerp'), h('dd', null, data.topic_label),
              h('dt', null, 'Geopend'), h('dd', null, dateLabel(ticket.opened_at))),
            h('p', {class: 'muted tiny'}, 'Deze context bepaalt welke trackrecord je te zien krijgt.'),
            citedBox),
          ask),
        h('section', {class: 'card'},
          h('div', {class: 'section-title'}, h('h2', null, 'Kennis voor dit ticket'), h('p', null, 'Waarschuwingen voor jouw situatie eerst')),
          searchForm, results)));
    refreshCited();
  } catch (err) { if (state.user) failure('#/tickets', err); }
}

function trustBlock(trust) {
  return [
    h('div', {class: 'trustline'}, badge(trust.quadrant, trust.quadrant_label), h('strong', null, trust.headline), h('span', {class: 'muted'}, trust.detail)),
    trust.warning ? h('div', {class: 'callout warning'}, '⚠ ', trust.warning) : null,
    trust.context_note ? h('div', {class: 'callout note'}, trust.context_note) : null,
    trust.tip ? h('div', {class: 'callout tip'}, trust.tip) : null,
  ];
}

function docCard(item, onCite) {
  return h('article', {class: `card doc-card${item.trust.warning ? ' has-warning' : ''}`},
    h('div', {class: 'doc-head'},
      h('div', null, h('h3', null, item.title), h('p', {class: 'muted tiny'}, `Eigenaar ${item.owner} · versie ${item.version}`)),
      h('button', {class: 'btn small', type: 'button', onclick: () => openReader(item.version_id, onCite)}, 'Lees')),
    h('p', {class: 'excerpt'}, item.excerpt + (item.excerpt.length >= 160 ? '…' : '')),
    trustBlock(item.trust));
}

async function openReader(versionId, onCite) {
  const dialog = document.getElementById('reader');
  const opened = Date.now();
  const tracking = state.user.role === 'consultant' && state.session;
  let doc;
  const query = tracking ? `?ticket=${encodeURIComponent(state.session.ticket)}` : '';
  try { doc = await api(`/api/versions/${encodeURIComponent(versionId)}${query}`); } catch (err) { toast(err.message); return; }
  const close = h('button', {class: 'close-x', type: 'button', 'aria-label': 'Sluit document', onclick: () => dialog.close()}, '×');
  const actions = tracking ? h('div', {class: 'btn-row'},
    h('button', {class: 'btn primary', type: 'button', onclick: async event => {
      event.target.disabled = true;
      try {
        await api('/api/events', {session_id: state.session.id, type: 'cite', doc_version_id: versionId});
        state.cited.add(doc.title); onCite && onCite();
        toast('Toegevoegd als bron bij dit ticket.');
      } catch (err) { toast(err.message); event.target.disabled = false; }
    }}, 'Gebruik als bron'),
    h('button', {class: 'btn warn', type: 'button', onclick: async event => {
      event.target.disabled = true;
      try {
        await api('/api/events', {session_id: state.session.id, type: 'not_helpful', doc_version_id: versionId});
        toast('Genoteerd. Eén stem per versie, anoniem.');
      } catch (err) { toast(err.message); }
    }}, 'Dit hielp niet')) : null;
  dialog.replaceChildren(h('div', {class: 'reader'},
    h('div', {class: 'reader-top'}, h('span', {class: 'eyebrow'}, `Document ${doc.id}`), close),
    h('h2', {id: 'reader-title'}, doc.title),
    h('p', {class: 'muted small'}, `Eigenaar ${doc.owner} · versie ${doc.version} · gepubliceerd ${dateLabel(doc.published_at)}`),
    h('blockquote', null, doc.body),
    trustBlock(doc.trust),
    actions,
    tracking ? h('p', {class: 'muted tiny'}, 'Leestijd, een nieuwe zoekopdracht of een vraag in Teams kort na het lezen tellen mee als twijfelsignaal voor dit document, nooit voor jou als persoon.') : null));
  dialog.onclose = () => {
    if (!tracking) return;
    const dwell = Math.min(3600, Math.round((Date.now() - opened) / 1000));
    api('/api/events', {session_id: state.session.id, type: 'open', doc_version_id: versionId, dwell_seconds: dwell}).catch(() => {});
  };
  dialog.showModal();
}

// ---------- owner & manager: documents ----------
async function renderDocuments() {
  loading('#/documents');
  try {
    const docs = await api('/api/documents');
    const manager = state.user.role === 'manager';
    shell('#/documents',
      pageHead(manager ? 'Alle documenten' : 'Documenteigenaar', manager ? 'Alle documenten, op prioriteit' : 'Jouw documenten, op prioriteit',
        'Het oordeel komt uit wat er na gebruik gebeurde: heropende tickets, looncorrecties en escalaties. Twijfel na het lezen komt uit zoek- en leesgedrag.'),
      h('section', {class: 'card'},
        h('div', {class: 'doc-list-row doc-list-head'}, h('span', null, 'Oordeel'), h('span', null, 'Document'), h('span', {class: 'num hide-sm'}, 'Gebruik'), h('span', {class: 'num'}, 'Misgelopen'), h('span', {class: 'num'}, 'Twijfel')),
        docs.map(doc => h('a', {class: 'doc-list-row', href: `#/document/${doc.document_id}`},
          h('span', null, badge(doc.quadrant, doc.quadrant_label)),
          h('span', null, h('strong', null, doc.title), h('br'), h('span', {class: 'muted tiny'}, `${doc.owner} · versie ${doc.version} · ${doc.country}`)),
          h('span', {class: 'num hide-sm'}, doc.uses),
          h('span', {class: 'num'}, doc.uses ? pct(doc.fail_rate) : '–'),
          h('span', {class: 'num'}, doc.reads ? pct(doc.doubt_rate) : '–')))));
  } catch (err) { if (state.user) failure('#/documents', err); }
}

async function renderDossier(documentId) {
  loading('#/documents');
  try {
    const d = await api(`/api/documents/${documentId}`);
    const c = d.current;
    const active = state.user.role === 'manager' ? '#/documents' : '#/documents';
    shell(active,
      h('p', {class: 'small'}, h('a', {href: state.user.role === 'manager' ? '#/dashboard' : '#/documents'}, '← Terug')),
      pageHead(`Dossier · ${d.document.id} · versie ${c.version}`, d.document.title, `Eigenaar ${d.document.owner} · stand op ${dateLabel(d.as_of)}`, badge(c.quadrant, c.quadrant_label)),
      h('section', {class: 'card'}, h('div', {class: 'eyebrow'}, 'Waarom dit oordeel'), h('p', {class: 'reason'}, c.reason)),
      h('div', {class: 'kpis'},
        kpi('Gebruikt met gekende uitkomst', c.uses, `${c.pending} nog lopend · ${c.users} collega's`),
        kpi('Misgelopen', c.uses ? pct(c.fails / c.uses) : '–', `gewogen schatting ${pct(c.fail_rate)} · typisch ${pct(d.org.fail_rate)}`, c.quadrant === 'dangerous' || c.quadrant === 'broken' ? 'k-dangerous' : ''),
        kpi('Twijfel na lezen', c.reads ? pct(c.doubts / c.reads) : '–', `gewogen schatting ${pct(c.doubt_rate)} · typisch ${pct(d.org.doubt_rate)}`, c.quadrant === 'unclear' || c.quadrant === 'broken' ? 'k-unclear' : ''),
        kpi('Te veel misgelopen', `≈ ${Math.round(c.excess_failures)}`, 'meer dan bij een typisch document')),
      h('div', {class: 'grid-2'},
        h('section', {class: 'card'}, h('div', {class: 'section-title'}, h('h2', null, 'Wanneer loopt het mis?'), h('p', null, 'per maand, alle versies')), timeline(d.history)),
        h('section', {class: 'card'}, h('div', {class: 'section-title'}, h('h2', null, 'Waar loopt het mis?'), h('p', null, `alleen groepen met ≥ ${d.rules.min_users} collega's`)), segments(c, d.org))),
      h('div', {class: 'grid-2'},
        causeCard(d, c),
        followUpCard(c)),
      h('div', {class: 'grid-2'},
        versionsCard(d),
        d.document.can_publish ? publishCard(d, c) : h('section', {class: 'card'}, h('h2', null, 'Nieuwe versie'),
          h('p', {class: 'muted small'}, 'Alleen de eigenaar van het document kan een nieuwe versie publiceren. Een kennisbeheerder kan meekijken, niet zelf wijzigen.'))),
      rulesCard(d.rules));
  } catch (err) { if (state.user) failure('#/documents', err); }
}

function kpi(label, value, sub, extra = '') {
  return h('div', {class: `kpi ${extra}`}, h('div', {class: 'eyebrow'}, label), h('div', {class: 'value'}, value), sub ? h('div', {class: 'sub'}, sub) : null);
}

function timeline(history) {
  const months = [...new Set(history.map(row => row.month))].sort();
  if (!months.length) return h('p', {class: 'empty'}, 'Nog geen gebruik.');
  const byMonth = months.map(month => {
    const rows = history.filter(row => row.month === month);
    return {month, uses: rows.reduce((a, r) => a + r.uses, 0), fails: rows.reduce((a, r) => a + r.fails, 0), version: Math.max(...rows.map(r => r.version))};
  });
  const width = 640, height = 220, left = 34, bottom = 28, top = 14;
  const max = Math.max(4, ...byMonth.map(m => m.uses));
  const band = (width - left - 8) / byMonth.length;
  const y = value => top + (height - top - bottom) * (1 - value / max);
  const chart = s('svg', {class: 'chart', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Gebruik en misgelopen gebruik per maand'});
  [0, Math.round(max / 2), max].forEach(tick => chart.append(
    s('line', {class: 'axis', x1: left, x2: width - 8, y1: y(tick), y2: y(tick), 'stroke-opacity': tick ? .4 : 1}),
    s('text', {x: left - 6, y: y(tick) + 4, 'text-anchor': 'end'}, tick)));
  byMonth.forEach((m, i) => {
    const x = left + i * band + band * 0.18, w = band * 0.64;
    chart.append(
      s('rect', {class: 'bar-uses', x, width: w, y: y(m.uses), height: y(0) - y(m.uses), rx: 2}, s('title', null, `${m.month}: ${m.uses} gebruiken, ${m.fails} misgelopen`)),
      s('rect', {class: 'bar-fails', x, width: w, y: y(m.fails), height: y(0) - y(m.fails), rx: 2}),
      s('text', {x: x + w / 2, y: height - 9, 'text-anchor': 'middle'}, monthLabel(m.month)));
    if (i > 0 && m.version !== byMonth[i - 1].version) {
      const xl = left + i * band;
      chart.append(s('line', {class: 'version-line', x1: xl, x2: xl, y1: top - 4, y2: y(0)}),
        s('text', {x: xl + 4, y: top + 6, fill: '#14213d'}, `v${m.version}`));
    }
  });
  return h('div', null, chart, h('div', {class: 'legend'},
    h('span', null, h('i', {class: 'legend-uses'}), 'gebruikt'),
    h('span', null, h('i', {class: 'legend-fails'}), 'misgelopen (heropend, gecorrigeerd, geëscaleerd)')));
}

const DIMENSION = {statute: 'Statuut', pc: 'Paritair comité', country: 'Land', size: 'Klantgrootte', period: 'Periode'};
const PERIOD = {recent: 'laatste 90 dagen', eerder: 'daarvoor'};
function segments(current, org) {
  const dims = Object.keys(current.segments || {}).filter(dim => current.segments[dim].length > 1);
  if (!dims.length) return h('p', {class: 'empty'}, 'Te weinig gebruik om per context te tonen.');
  const finding = current.segment && current.segment.high ? current.segment : null;
  const max = Math.max(0.25, ...dims.flatMap(dim => current.segments[dim].map(row => row.rate)));
  return h('div', null,
    finding ? h('div', {class: 'callout warning'}, `Het verschil zit in ${DIMENSION[finding.dimension].toLowerCase()}: ${finding.dimension === 'period' ? PERIOD[finding.value] : finding.value}.`) : null,
    dims.map(dim => h('div', {class: 'seg-block'},
      h('div', {class: 'eyebrow'}, DIMENSION[dim] || dim),
      current.segments[dim].map(row => {
        const hot = finding && finding.dimension === dim && finding.value === row.value;
        const fill = h('span', {class: 'seg-fill'}); fill.style.width = `${Math.min(100, row.rate / max * 100)}%`;
        const norm = h('span', {class: 'seg-norm', title: 'typisch document'}); norm.style.left = `${Math.min(100, org.fail_rate / max * 100)}%`;
        return h('div', {class: `seg-row${hot ? ' hot' : ''}`},
          h('span', null, dim === 'period' ? PERIOD[row.value] : row.value),
          h('span', {class: 'seg-track'}, fill, norm),
          h('span', {class: 'num'}, `${row.fails}/${row.uses}`));
      }))),
    h('p', {class: 'muted tiny'}, 'Balk: afgevlakte foutgraad. Streep: typisch document.'));
}

function causeCard(d, c) {
  const cause = d.cause;
  return h('section', {class: 'card'},
    h('div', {class: 'section-title'}, h('h2', null, 'Waarom loopt het mis?'), h('p', null, 'woordanalyse van mislukte tickets')),
    !cause ? h('p', {class: 'muted small'}, 'Er liep niets mis met deze versie.') : [
      h('p', {class: 'small'}, cause.summary),
      cause.terms.length ? h('div', {class: 'chips'}, cause.terms.map(term => h('span', {class: 'chip', title: `z-score ${term.z}`}, term.word, h('small', null, `×${term.count}`)))) : null,
      cause.examples.map(example => h('p', {class: 'quote'}, `“${example}”`)),
      d.hypothesis ? h('div', {class: 'ai-box'}, h('strong', null, 'AI-hypothese: '), d.hypothesis,
        h('p', {class: 'muted tiny'}, 'Alleen een formulering van de commentaren hierboven. Het oordeel en de cijfers komen uit vaste rekenregels.')) : null,
      h('p', {class: 'muted tiny'}, 'Kernwoorden komen opvallend vaker voor in de mislukte tickets van dit document dan elders (log-odds met informatieve prior, z ≥ 1,96).'),
    ]);
}

function followUpCard(c) {
  return h('section', {class: 'card'},
    h('div', {class: 'section-title'}, h('h2', null, 'Wat vragen lezers daarna?'), h('p', null, 'Teams-vragen kort na het lezen')),
    c.follow_ups.length ? [
      c.follow_ups.map(item => h('p', {class: 'quote'}, `“${item.text}” `, h('span', {class: 'muted tiny'}, `${item.count}×`))),
      h('p', {class: 'muted tiny'}, 'Dit is letterlijk wat er in het document ontbreekt: een herschrijfopdracht.'),
    ] : h('p', {class: 'muted small'}, 'Geen opvallende vervolgvragen.'),
    h('p', {class: 'muted tiny'}, `${c.bounces} keer snel weer gesloten (< 10 s): een vindbaarheidssignaal, geen twijfel over de inhoud.`));
}

function versionsCard(d) {
  const impact = d.impact;
  return h('section', {class: 'card'},
    h('div', {class: 'section-title'}, h('h2', null, 'Versies en effect'), h('p', null, 'een nieuwe versie start een nieuw trackrecord')),
    impact ? h('div', {class: 'callout ' + (impact.measurable ? 'good' : 'note')},
      h('div', {class: 'impact'},
        h('div', null, h('span', {class: 'tiny muted'}, `versie ${impact.before.version}`), h('strong', null, impact.before_rate === null ? '–' : pct(impact.before_rate)), h('span', {class: 'tiny'}, `misgelopen · ${impact.before.uses} gebruiken`)),
        h('div', {class: 'arrow'}, '→'),
        h('div', null, h('span', {class: 'tiny muted'}, `versie ${impact.after.version}`), h('strong', null, impact.after_rate === null ? '–' : pct(impact.after_rate)), h('span', {class: 'tiny'}, `misgelopen · ${impact.after.uses} gebruiken`))),
      h('p', {class: 'small'}, impact.measurable
        ? `≈ ${impact.avoided} mislukte tickets vermeden sinds de nieuwe versie (simulatie: we nemen aan dat de nieuwe tekst het probleem oplost).`
        : `Nog te weinig gebruik om het effect te beoordelen (${impact.after.uses} van minstens 5).`)) : null,
    d.versions.slice().reverse().map(v => h('div', {class: 'version-row'},
      h('div', null, h('strong', null, `Versie ${v.version}`), h('span', {class: 'muted small'}, ` · ${dateLabel(v.published_at)} · ${v.change_note || ''}`)),
      badge(v.quadrant, v.quadrant_label))));
}

function publishCard(d, c) {
  const body = h('textarea', {id: 'new-body', maxlength: 4000, required: true}); body.value = c.body;
  const note = h('input', {id: 'change-note', maxlength: 300, required: true, placeholder: 'Wat is er veranderd en waarom?'});
  const submit = h('button', {class: 'btn primary', type: 'submit'}, 'Publiceer nieuwe versie');
  return h('form', {class: 'card', onsubmit: async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const result = await api(`/api/documents/${d.document.id}/versions`, {body: body.value.trim(), change_note: note.value.trim()});
      toast(`Versie ${result.version} gepubliceerd. Het trackrecord begint opnieuw.`);
      renderDossier(d.document.id);
    } catch (err) { toast(err.message); submit.disabled = false; }
  }},
    h('h2', null, 'Nieuwe versie publiceren'),
    h('p', {class: 'muted small'}, 'Gebruik de oorzaak en de vervolgvragen hiernaast. De huidige versie blijft bewaard voor de vergelijking.'),
    h('div', {class: 'field'}, h('label', {for: 'new-body'}, 'Tekst'), body),
    h('div', {class: 'field'}, h('label', {for: 'change-note'}, 'Wijzigingsnota'), note),
    h('div', {class: 'btn-row'}, submit));
}

function rulesCard(rules) {
  return h('details', {class: 'card rules'},
    h('summary', null, 'Hoe we rekenen (open en controleerbaar)'),
    h('ul', null,
      h('li', null, `Een gebruik = een document dat als bron bij een ticket werd gevoegd. Mislukt = heropend, gecorrigeerd in de loonrun of geëscaleerd.`),
      h('li', null, `Twijfel na lezen = binnen ${rules.doubt_window_minutes} minuten na het lezen opnieuw zoeken, een ander document openen, een Teams-vraag of ‘dit hielp niet’. Korter dan ${rules.min_dwell_seconds} s lezen telt als vindbaarheidsprobleem.`),
      h('li', null, `Recente gebruiken wegen zwaarder (halfwaardetijd ${rules.half_life_days} dagen). Scores worden afgevlakt naar het typische document (sterkte ${rules.prior_strength}).`),
      h('li', null, `Een oordeel pas vanaf ${rules.min_uses} gebruiken door ${rules.min_users} verschillende collega's, en alleen als de kans dat het echt boven de drempel (${rules.high_factor}× typisch) ligt minstens ${Math.round(rules.confidence * 100)}% is.`),
      h('li', null, `Eén uitkomst telt één keer per document, en één persoon telt hoogstens ${rules.person_monthly_cap} keer per maand mee per documentversie: niemand kan een score alleen sturen.`),
      h('li', null, 'De AI formuleert hoogstens een hypothese. Ze beslist niets.')));
}

// ---------- manager dashboard ----------
async function renderDashboard() {
  loading('#/dashboard');
  try {
    const d = await api('/api/dashboard');
    const flagged = d.documents.filter(doc => ['dangerous', 'broken', 'unclear'].includes(doc.quadrant));
    const gaps = d.gaps.filter(gap => gap.is_gap);
    const controls = d.demo_controls ? h('div', {class: 'demo-controls'},
      h('span', {class: 'date-pill'}, `Stand op ${dateLabel(d.as_of)}`),
      h('button', {class: 'btn', type: 'button', onclick: async event => {
        event.target.disabled = true;
        try { const result = await api('/api/demo/simulate-month', {}); toast(`Een maand gesimuleerd, tot ${dateLabel(result.today)}.`); renderDashboard(); }
        catch (err) { toast(err.message); event.target.disabled = false; }
      }}, 'Simuleer volgende maand'),
      h('button', {class: 'btn', type: 'button', onclick: async event => {
        if (!confirm('De demo terugzetten naar de beginsituatie? Nieuwe versies en gesimuleerde maanden verdwijnen.')) return;
        event.target.disabled = true;
        try { await api('/api/demo/reset', {}); renderLogin('Demo teruggezet. Log opnieuw in.'); state.user = null; }
        catch (err) { toast(err.message); event.target.disabled = false; }
      }}, 'Reset demo')) : null;
    shell('#/dashboard',
      pageHead('Kennisbeheerder', 'Waar verdient kennis ons vertrouwen, en waar niet?', `${d.total_uses} gebruiken met gekende uitkomst, ${d.documents.length} documenten. Alles hieronder komt uit het gewone werk, zonder extra moeite.`, controls),
      h('div', {class: 'kpis'},
        kpi('Gevaarlijk', d.counts.dangerous, 'vertrouwd, maar het loopt mis', 'k-dangerous'),
        kpi('Kapot', d.counts.broken, 'twijfel én fouten', 'k-broken'),
        kpi('Onduidelijk', d.counts.unclear, 'klopt, maar roept vragen op', 'k-unclear'),
        kpi('Ontbrekende kennis', gaps.length, 'gezocht, niets gevonden', 'k-gap'),
        kpi('Typisch document', pct(d.org.fail_rate), `misgelopen · ${pct(d.org.doubt_rate)} twijfel`)),
      h('div', {class: 'grid-2'},
        h('section', {class: 'card'},
          h('div', {class: 'section-title'}, h('h2', null, 'Twijfel × uitkomst'), h('p', null, 'klik een punt voor het dossier')),
          scatter(d)),
        h('section', {class: 'card'},
          h('div', {class: 'section-title'}, h('h2', null, 'Eerst aanpakken'), h('p', null, 'gesorteerd op risico')),
          flagged.length ? flagged.map(doc => h('a', {class: 'priority-row', href: `#/document/${doc.document_id}`},
            badge(doc.quadrant, doc.quadrant_label),
            h('div', null, h('h3', null, doc.title), h('p', null, doc.reason)),
            doc.excess_failures >= 1 ? h('div', {class: 'excess'}, h('strong', null, Math.round(doc.excess_failures)), 'te veel misgelopen') : h('div'))) :
            h('p', {class: 'empty'}, 'Geen documenten die aandacht vragen.'))),
      h('div', {class: 'grid-2'},
        gapsCard(d.gaps),
        evaluationCard(d.evaluation)),
      h('section', {class: 'card privacy'},
        h('h2', null, 'We meten documenten, geen mensen'),
        h('p', null, `Signalen worden opgeslagen onder een pseudoniem, niet onder een naam. Er bestaat geen overzicht per medewerker, ook niet in de API. Cijfers per context verschijnen pas als minstens ${d.rules.min_users} verschillende collega's bijdroegen. Vrije tekst wordt ontdaan van rijksregisternummers, IBAN's, e-mailadressen en telefoonnummers. Uitkomsten komen uit het ticketsysteem en de loonrun, nooit uit de browser.`)));
  } catch (err) { if (state.user) failure('#/dashboard', err); }
}

function scatter(d) {
  const docs = d.documents.filter(doc => doc.enough_fail || doc.enough_doubt);
  const width = 640, height = 430, left = 50, right = 16, top = 16, bottom = 46;
  const maxX = Math.max(0.7, ...docs.map(doc => doc.doubt_rate)) * 1.05;
  const maxY = Math.max(0.4, ...docs.map(doc => doc.fail_rate)) * 1.08;
  const x = value => left + (width - left - right) * value / maxX;
  const y = value => top + (height - top - bottom) * (1 - value / maxY);
  const tx = x(d.org.doubt_threshold), ty = y(d.org.fail_threshold);
  const chart = s('svg', {class: 'chart', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Documenten volgens twijfel na lezen en misgelopen gebruik'});
  chart.append(
    s('rect', {class: 'bg-dangerous', x: left, y: top, width: tx - left, height: ty - top}),
    s('rect', {class: 'bg-broken', x: tx, y: top, width: width - right - tx, height: ty - top}),
    s('rect', {class: 'bg-reliable', x: left, y: ty, width: tx - left, height: y(0) - ty}),
    s('rect', {class: 'bg-unclear', x: tx, y: ty, width: width - right - tx, height: y(0) - ty}),
    s('text', {class: 'quad-label fill-dangerous', x: left + 10, y: top + 20}, 'Gevaarlijk'),
    s('text', {class: 'quad-label fill-broken', x: width - right - 10, y: top + 20, 'text-anchor': 'end'}, 'Kapot'),
    s('text', {class: 'quad-label fill-reliable', x: left + 10, y: y(0) - 10}, 'Betrouwbaar'),
    s('text', {class: 'quad-label fill-unclear', x: width - right - 10, y: y(0) - 10, 'text-anchor': 'end'}, 'Onduidelijk'),
    s('line', {class: 'threshold', x1: tx, x2: tx, y1: top, y2: y(0)}),
    s('line', {class: 'threshold', x1: left, x2: width - right, y1: ty, y2: ty}),
    s('line', {class: 'axis', x1: left, x2: width - right, y1: y(0), y2: y(0)}),
    s('line', {class: 'axis', x1: left, x2: left, y1: top, y2: y(0)}),
    s('text', {x: (left + width - right) / 2, y: height - 8, 'text-anchor': 'middle'}, 'Twijfel na het lezen (Understand it) →'),
    s('text', {x: 14, y: (top + y(0)) / 2, 'text-anchor': 'middle', transform: `rotate(-90 14 ${(top + y(0)) / 2})`}, 'Misgelopen na gebruik (Trust it) →'));
  [0, 0.2, 0.4, 0.6].filter(v => v <= maxX).forEach(v => chart.append(s('text', {x: x(v), y: y(0) + 16, 'text-anchor': 'middle'}, pct(v))));
  [0, 0.1, 0.2, 0.3, 0.4].filter(v => v <= maxY).forEach(v => chart.append(s('text', {x: left - 8, y: y(v) + 4, 'text-anchor': 'end'}, pct(v))));
  docs.sort((a, b) => (a.quadrant === 'reliable') - (b.quadrant === 'reliable')).reverse().forEach(doc => {
    const r = 4 + Math.sqrt(doc.uses) * 0.7;
    const link = s('a', {href: `#/document/${doc.document_id}`, 'aria-label': `${doc.title}: ${doc.quadrant_label}`},
      s('circle', {class: `dot fill-${doc.quadrant}`, cx: x(doc.doubt_rate), cy: y(doc.fail_rate), r, 'fill-opacity': doc.quadrant === 'reliable' ? 0.55 : 0.95},
        s('title', null, `${doc.title} · ${doc.quadrant_label} · ${pct(doc.fail_rate)} misgelopen · ${pct(doc.doubt_rate)} twijfel · ${doc.uses} gebruiken`)));
    chart.append(link);
    if (doc.quadrant !== 'reliable' && doc.quadrant !== 'insufficient') {
      const anchorEnd = x(doc.doubt_rate) > width * 0.6;
      chart.append(s('text', {class: 'dot-label', x: x(doc.doubt_rate) + (anchorEnd ? -r - 5 : r + 5), y: y(doc.fail_rate) + 4, 'text-anchor': anchorEnd ? 'end' : 'start'}, doc.title.split(':')[0]));
    }
  });
  return h('div', null, chart, h('p', {class: 'muted tiny'}, `Stippellijnen: ${d.rules.high_factor}× het typische document. Grootte van een punt: aantal gebruiken.`));
}

function gapsCard(gaps) {
  const real = gaps.filter(gap => gap.is_gap);
  return h('section', {class: 'card'},
    h('div', {class: 'section-title'}, h('h2', null, 'Ontbrekende kennis (Find it)'), h('p', null, 'gezocht zonder bruikbaar document · 90 dagen')),
    real.length ? real.map(gap => h('div', {class: 'gap-row'},
      h('h3', null, h('span', {class: 'gap-tag'}, 'Lacune'), `“${gap.label}” en verwante zoekopdrachten`),
      h('p', {class: 'muted small'}, `${gap.sessions} zoeksessies zonder bron · in ${pct(gap.teams_share)} daarvan volgde een vraag in Teams · ${gap.bounces} keer snel weggeklikt`),
      gap.questions.map(q => h('p', {class: 'quote'}, `“${q.text}” `, h('span', {class: 'muted tiny'}, `${q.count}×`))))) :
      h('p', {class: 'empty'}, 'Geen duidelijke lacunes.'),
    h('p', {class: 'muted tiny'}, 'Voorstel: laat een expert uit het Teams-kanaal hier een document van maken.'));
}

function evaluationCard(evaluation) {
  if (!evaluation) {
    return h('section', {class: 'card'}, h('h2', null, 'Werkt het?'),
      h('p', {class: 'muted small'}, 'Draai ', h('code', null, 'python -m trackrecord.evaluate'), ' om te meten of de geplante problemen gevonden worden.'));
  }
  const e = evaluation;
  const raw = e.ablations.zonder_afvlakking_en_minimum_bewijs;
  return h('section', {class: 'card'},
    h('div', {class: 'section-title'}, h('h2', null, 'Werkt het? Gemeten, niet beweerd'), h('p', null, `${e.seeds} nieuwe synthetische werelden`)),
    h('p', {class: 'muted small'}, 'In elke wereld zijn problemen verstopt. Trackrecord weet niet waar, en moet ze zelf vinden.'),
    h('div', {class: 'eval-grid'},
      h('div', null, h('strong', null, `${e.found}/${e.planted_total}`), h('span', null, 'geplante problemen juist herkend')),
      h('div', null, h('strong', null, `${e.false_alarms}/${e.normal_total}`), h('span', null, 'valse alarmen op normale documenten')),
      h('div', null, h('strong', null, `${e.segment_correct}/${e.seeds}`), h('span', null, 'juiste context gevonden (arbeiders)')),
      h('div', null, h('strong', null, `${e.gap_found}/${e.seeds}`), h('span', null, 'kennislacune gevonden'))),
    h('p', {class: 'small'}, `Zonder afvlakking en minimumbewijs: ${raw.false_alarms} valse alarmen in plaats van ${e.false_alarms}. `,
      `Een regelwijziging werd na mediaan ${e.median_days_to_detect_change} dagen opgemerkt (gemist in ${e.missed_change} van ${e.seeds} werelden).`));
}

// ---------- router ----------
const ROUTES = [
  [/^#\/tickets$/, renderTickets, ['consultant']],
  [/^#\/ticket\/(T-[A-Z0-9-]+)$/, renderTicket, ['consultant']],
  [/^#\/documents$/, renderDocuments, ['owner', 'manager']],
  [/^#\/document\/(TR-[A-Z0-9-]+)$/, renderDossier, ['owner', 'manager']],
  [/^#\/dashboard$/, renderDashboard, ['manager']],
];
function route() {
  if (!state.user) { renderLogin(); return; }
  for (const [pattern, view, roles] of ROUTES) {
    const match = location.hash.match(pattern);
    if (match && roles.includes(state.user.role)) { view(...match.slice(1)); return; }
  }
  location.hash = HOME[state.user.role];
}
window.addEventListener('hashchange', route);
(async () => {
  try { await loadMe(); } catch (_) { state.user = null; }
  route();
})();
