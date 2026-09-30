const $ = selector => document.querySelector(selector);
let busy = false;
let latestResult = null;
let tabGeneration = 0;
let atlasFilter = 'all';
const state = {me: null, csrf: '', sessionId: null, tickets: []};
const statuses = {
  supported: ['Antwoord gevonden', 'Dit zeggen de goedgekeurde bronnen'],
  practice: ['Loopt vaak mis in de praktijk', 'Goedgekeurd, maar niet betrouwbaar voor jouw situatie'],
  conflict: ['Bronnen spreken elkaar tegen', 'Er is nog geen eenduidig antwoord'],
  review: ['Bevestiging nodig', 'Deze informatie moet eerst worden gecontroleerd'],
  missing: ['Geen bron gevonden', 'We hebben nog geen antwoord op deze vraag'],
  reviewed: ['Beoordeeld door de bronhouder', 'Dit antwoord is gekozen na beoordeling'],
};
const scenarios = {
  deadline: 'Wat is de deadline voor de maandelijkse verwerking?',
  correction: 'Wie moet een looncorrectie controleren en goedkeuren?',
  handover: 'Hoe draag ik een klantdossier over aan een nieuwe consultant?',
  holiday: 'Wie betaalt het vakantiegeld van een arbeider?',
};
const ROLE = {consultant: 'Consultant', owner: 'Bronhouder', manager: 'Kennisbeheerder'};
const HOME = {consultant: 'investigate', owner: 'reviews', manager: 'overview'};
const STATUTE = {alle: 'Statuut onbekend', arbeider: 'Arbeider', bediende: 'Bediende'};
const DIMENSION = {statute: 'Statuut', pc: 'Paritair comité', country: 'Land', size: 'Klantgrootte', period: 'Periode'};
const SEGMENT_VALUE = {recent: 'laatste 90 dagen', eerder: 'daarvoor', alle: 'geen statuut (NL)'};
const FLAGGED = ['dangerous', 'broken', 'unclear'];
const SVG = 'http://www.w3.org/2000/svg';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function svg(tag, attributes = {}, text) {
  const node = document.createElementNS(SVG, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function button(text, className, action) {
  const node = el('button', className, text); node.type = 'button';
  if (action) node.addEventListener('click', action);
  return node;
}
function showError(error) {$('#error').textContent = error.message || 'Er ging iets mis.'; $('#error').hidden = false;}
function toast(message) {
  const node = $('#toast'); const dialog = $('#source-dialog');
  (dialog.open ? dialog : document.body).append(node);   // stay above the modal backdrop
  node.textContent = message; node.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => {node.hidden = true;}, 2800);
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf}, body: JSON.stringify(payload),
  });
  if (response.status === 401 && path !== '/api/login' && path !== '/api/me') {showLogin('Je sessie is verlopen. Log opnieuw in.');}
  if (!response.ok) {
    let message = 'Deze actie lukte niet. Probeer opnieuw.';
    try {
      const problem = await response.json();
      if (typeof problem.detail === 'string') message = problem.detail;
      else if (Array.isArray(problem.detail)) message = problem.detail.map(item => item.msg).join(' · ');
    } catch (_) {if (response.status === 413) message = 'De ingevoerde tekst is te lang.';}
    throw new Error(message);
  }
  return response.json();
}
function readableDate(value) {
  return new Intl.DateTimeFormat('nl-BE', {day: 'numeric', month: 'long', year: 'numeric'}).format(new Date(value.slice(0, 10) + 'T12:00:00'));
}
const pct = value => `${Math.round(value * 100)}%`;
function clientName(id) {return (state.me?.clients || []).find(c => c.id === id)?.name || (id ? 'Klant' : 'Algemeen');}
function contextLabel(context) {
  const parts = [context.country === 'BE' ? 'België' : 'Nederland', context.client_name || clientName(context.client_id)];
  if (context.statute && context.statute !== 'alle') parts.push(STATUTE[context.statute]);
  return [...parts, readableDate(context.as_of)].join(' · ');
}
function badge(text, className = '') {return el('span', 'badge' + (className ? ' ' + className : ''), text);}
function quadrantBadge(trust) {return badge(trust.quadrant_label, 'q-' + trust.quadrant);}

// ---------- track record ----------
function trustBlock(trust, compact = false) {
  const block = el('div', 'trust');
  if (!trust) return block;
  const line = el('div', 'trust-line');
  line.append(el('span', 'trust-label', 'Trackrecord'), quadrantBadge(trust), el('strong', '', trust.headline));
  if (!compact) line.append(el('span', 'trust-detail', trust.detail));
  block.append(line);
  if (trust.warning) block.append(el('p', 'callout warning', '⚠ ' + trust.warning));
  if (trust.context_note && !compact) block.append(el('p', 'callout note', trust.context_note));
  if (trust.tip && !compact) block.append(el('p', 'callout tip', trust.tip));
  return block;
}

async function useForTicket(sourceId, control) {
  if (!state.sessionId) return;
  control.disabled = true;
  try {
    await api('/api/events', {session_id: state.sessionId, type: 'cite', source_id: sourceId});
    control.textContent = '✓ Gebruikt voor dit ticket'; toast('Bron gekoppeld aan het ticket. De uitkomst telt mee voor haar trackrecord.');
  } catch (error) {toast(error.message); control.disabled = false;}
}

// ---------- sources (PARALLAX) ----------
function openSource(source) {
  const root = $('#source-dialog-content'); root.replaceChildren();
  const heading = el('h2', '', source.title); heading.id = 'source-dialog-title'; root.append(heading);
  root.append(el('p', 'source-meta', `${source.kind} · ${source.country === 'BE' ? 'België' : 'Nederland'} · ${source.client_id ? clientName(source.client_id) : 'Algemeen'}${source.statute && source.statute !== 'ALL' ? ' · alleen ' + source.statute + 's' : ''}`));
  root.append(el('p', 'source-meta', `Bronhouder: ${source.owner || 'Niet bekend'} · Bijgewerkt op ${readableDate(source.updated_at)}`));
  root.append(el('p', 'source-meta', `Geldig vanaf ${readableDate(source.valid_from)}${source.valid_until ? ' tot ' + readableDate(source.valid_until) : ' · Geen einddatum vastgelegd'}`));
  root.append(badge(source.approved ? '✓ Formeel goedgekeurd' : '○ Niet formeel goedgekeurd', source.approved ? '' : 'warning'));
  root.append(el('blockquote', '', source.text || source.passages.map(p => p.text).join('\n\n')));
  if (source.warnings) source.warnings.forEach(warning => root.append(badge(warning, 'warning')));
  root.append(trustBlock(source.trust));
  const sourceId = source.source_id || source.id;
  const tracking = Boolean(state.sessionId) && source.active !== false && source.is_current !== false;
  if (tracking) {
    const actions = el('div', 'review-actions');
    if (latestResult?.ticket) actions.append(button('Gebruik voor dit ticket', 'primary', event => useForTicket(sourceId, event.target)));
    actions.append(button('Dit hielp niet', 'secondary', async event => {
      event.target.disabled = true;
      try {await api('/api/events', {session_id: state.sessionId, type: 'not_helpful', source_id: sourceId}); toast('Genoteerd. Eén stem per versie, zonder naam.');}
      catch (error) {toast(error.message);}
    }));
    root.append(actions);
  }
  root.append(el('p', 'citation-code', source.citation || source.id));
  root.append(el('p', 'microcopy', 'Fictieve voorbeeldbron. Leestijd, opnieuw zoeken of een beoordeling vragen kort na het lezen tellen mee als twijfelsignaal voor deze bron, nooit voor jou als persoon.'));
  const opened = Date.now();
  $('#source-dialog').onclose = () => {
    if (!tracking) return;
    const dwell = Math.min(3600, Math.round((Date.now() - opened) / 1000));
    api('/api/events', {session_id: state.sessionId, type: 'open', source_id: sourceId, dwell_seconds: dwell}).catch(() => {});
  };
  $('#source-dialog').showModal();
}
$('#close-dialog').addEventListener('click', () => $('#source-dialog').close());
$('#source-dialog').addEventListener('click', event => {
  if (event.target === $('#source-dialog')) {
    const rect = event.target.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close();
  }
});

function sourceCard(source, index, result = null) {
  const card = el('article', 'source-card');
  if (source.active === false || source.is_current === false) card.classList.add('historical');
  if (result?.decision?.citation === source.citation) card.classList.add('selected-source');
  if (source.trust?.warning && source.active !== false) card.classList.add('has-warning');
  const top = el('div', 'source-top');
  let state_ = source.approved ? 'Goedgekeurd' : 'Niet goedgekeurd';
  if (source.replaced_by?.length || (source.is_current === false && !result)) state_ = 'Vervangen of verlopen';
  else if (source.active === false) state_ = 'Niet geldig op deze datum';
  top.append(el('h3', '', source.title), badge(state_, source.active === false || source.is_current === false || !source.approved ? 'warning' : ''));
  card.append(top);
  card.append(el('p', 'source-meta', `${source.kind} · ${source.owner || 'Eigenaar onbekend'}`));
  const claim = result?.conflicts.flatMap(c => c.evidence).find(e => e.citation === source.citation);
  const text = source.text || source.passages.map(p => p.text).join(' ');
  card.append(el('p', 'source-excerpt', claim ? 'Deze bron zegt: ' + claim.value : text.length > 180 ? text.slice(0, 180).trimEnd() + '…' : text));
  if (source.active !== false) card.append(trustBlock(source.trust, true));
  const actions = el('div', 'card-actions');
  actions.append(button('Lees volledige bron', 'text-button', () => openSource(source)));
  if (result?.ticket && source.active !== false) actions.append(button('Gebruik voor dit ticket', 'text-button', event => useForTicket(source.source_id, event.target)));
  if (source.can_open_dossier) actions.append(button('Open trackrecord', 'text-button', () => openDossier(source.id)));
  card.append(actions);
  return card;
}

function renderEvidence(result) {
  const section = el('section', 'sources-section');
  const title = el('h2', 'section-label'); title.append(el('span', 'step', '3'), el('span', '', 'Gebruikte bronnen'));
  section.append(title, el('p', '', result.sources.length ? 'Bekijk de documenten waarop dit resultaat is gebaseerd, en hoe ze het deden in de praktijk.' : 'Er is geen passend document gevonden voor deze vraag.'));
  const list = el('div', 'source-list');
  result.sources.forEach((source, index) => list.append(sourceCard(source, index, result)));
  section.append(list);
  return section;
}

function renderInsight(result) {
  const panel = el('section', 'answer-card ' + result.status);
  const top = el('div', 'answer-top');
  const title = el('h2', 'section-label'); title.append(el('span', 'step', '2'), el('span', '', 'Antwoord'));
  top.append(title, badge(statuses[result.status][0], result.needs_review ? 'warning' : ''));
  panel.append(top, el('h3', '', statuses[result.status][1]));
  if (result.practice_warning) panel.append(el('p', 'callout warning', '⚠ ' + result.practice_warning + ' Laat de bronhouder bevestigen wat geldt.'));
  panel.append(el('p', 'answer-text', result.answer));
  if (result.conflicts.length && !result.decision) {
    const differences = el('ul', 'conflict-list');
    result.conflicts.forEach(conflict => conflict.evidence.forEach(evidence => {
      const row = el('li');
      const left = el('div'); left.append(el('span', '', evidence.title));
      if (evidence.trust) {
        const trust = el('div', 'conflict-trust'); trust.append(quadrantBadge(evidence.trust), el('span', '', evidence.trust.headline)); left.append(trust);
      }
      row.append(left, el('strong', '', evidence.value)); differences.append(row);
    }));
    panel.append(differences);
    if (result.conflicts.some(c => c.evidence.some(e => e.trust?.warning))) {
      panel.append(el('p', 'microcopy', 'Goedgekeurd is niet hetzelfde als juist: het trackrecord toont wat er gebeurde nadat collega\'s elke bron gebruikten.'));
    }
  }
  if (result.decision) {
    const reason = el('div', 'decision-note');
    reason.append(el('strong', '', 'Reden van de keuze'), el('p', '', result.decision.rationale)); panel.append(reason);
    if (result.decision_challenged) panel.append(el('p', 'callout warning', '⚠ ' + result.decision_challenged));
    panel.append(el('p', 'microcopy', 'Deze beoordeling geldt voor dezelfde vraag en context, zolang de bronnen niet veranderen.'));
  }
  panel.append(el('p', 'result-context', 'Dit resultaat geldt voor: ' + contextLabel(result.context)));
  if (result.ticket) {
    const box = el('div', 'ticket-box');
    box.append(el('p', '', `Ticket ${result.ticket.id} · ${result.ticket.client_name}`));
    if (result.citations.length && ['supported', 'reviewed'].includes(result.status)) {
      box.append(button('Gebruik dit antwoord voor het ticket', 'secondary', async event => {
        event.target.disabled = true;
        try {
          for (const citation of result.citations) await api('/api/events', {session_id: state.sessionId, type: 'cite', source_id: citation.split(':')[0]});
          event.target.textContent = '✓ Gekoppeld aan het ticket';
          toast('Na afsluiting van het ticket telt de uitkomst mee voor het trackrecord van deze bronnen.');
        } catch (error) {toast(error.message); event.target.disabled = false;}
      }));
    } else {
      box.append(el('p', 'microcopy', 'Kies hieronder zelf een bron met ‘Gebruik voor dit ticket’, of vraag eerst een beoordeling.'));
    }
    panel.append(box);
  }
  const review = el('div', 'review-action');
  review.append(el('p', '', result.needs_review ? `${result.expert} kan helpen om deze vraag te beoordelen.` : 'Wil je dit antwoord laten controleren?'));
  const noteId = 'note-' + result.assessment_id;
  const noteLabel = el('label', 'note-label', 'Wat is er onduidelijk? (optioneel)'); noteLabel.htmlFor = noteId;
  const note = el('textarea'); note.id = noteId; note.rows = 2; note.maxLength = 500;
  note.placeholder = 'Bijvoorbeeld: geldt dit ook voor arbeiders?';
  let requestId = null;
  const action = button(result.decision ? 'Bekijk beoordeling' : 'Vraag een beoordeling', 'secondary', async () => {
    if (result.decision || requestId !== null) {await switchTab('reviews'); return;}
    action.disabled = true;
    try {
      const request = await api('/api/reviews', {assessment_id: result.assessment_id, note: note.value.trim() || null, session_id: state.sessionId});
      requestId = request.id;
      action.textContent = 'Bekijk je verzoek'; note.disabled = true;
      review.append(el('p', 'success-message', `Verzoek opgeslagen voor ${request.expert}. Je vindt het bij Beoordelingen.`));
      await updateReviewCount();
    } catch (error) {showError(error);}
    finally {action.disabled = false;}
  });
  if (!result.decision) review.append(noteLabel, note);
  review.append(action, el('p', 'microcopy', 'In deze demo wordt je verzoek lokaal opgeslagen. Er wordt geen expert gecontacteerd.'));
  if (result.needs_review || result.decision) panel.append(review);
  else {
    const optional = el('details', 'extra-options'); optional.append(el('summary', '', 'Een beoordeling vragen')); optional.append(review); panel.append(optional);
  }
  if (result.model_notice) panel.append(el('p', 'microcopy', result.model_notice));
  return panel;
}

function renderComparison(result) {
  const details = el('details', 'extra-options');
  details.append(el('summary', '', 'Vergelijk een ander land, statuut of een eerdere datum'));
  const content = el('div', 'extra-content');
  content.append(el('p', '', 'We stellen dezelfde vraag in andere situaties.'));
  details.append(content);
  let requested = false;
  details.addEventListener('toggle', async () => {
    if (!details.open || requested) return;
    requested = true;
    const loading = el('p', '', 'Vergelijking laden…'); content.append(loading);
    try {
      const alternatives = await api(`/api/assessments/${result.assessment_id}/compare`);
      const grid = el('div', 'comparison-grid');
      alternatives.forEach(alternative => {
        const card = el('article', 'comparison-card');
        card.append(el('h4', '', alternative.label.replace('Zelfde vraag, ', '').replace(/^./, c => c.toUpperCase())), el('p', 'context', contextLabel(alternative.context)), el('p', '', alternative.answer));
        card.append(button('Bekijk dit antwoord', 'text-button', () => {
          $('#ticket').value = ''; applyTicket();
          setForm(result.question, alternative.context); $('#question-form').requestSubmit();
        }));
        grid.append(card);
      });
      content.append(grid);
    } catch (error) {showError(error); requested = false;}
    finally {loading.remove();}
  });
  return details;
}

function renderResult(result) {
  latestResult = result;
  const root = $('#result'); root.replaceChildren();
  if (result.stale_decision && result.needs_review) root.append(el('div', 'notice', 'De bronnen zijn veranderd sinds de vorige beoordeling. Laat het antwoord opnieuw controleren.'));
  root.append(renderInsight(result), renderEvidence(result), renderComparison(result));
  const tools = el('div', 'result-tools');
  const download = el('a', '', 'Download antwoord en bronnen');
  download.href = `/api/assessments/${result.assessment_id}/receipt`;
  download.setAttribute('download', result.assessment_id + '.md'); tools.append(download);
  root.append(tools);
  if (result.excluded.length) {
    const excluded = el('details', 'excluded'); excluded.append(el('summary', '', 'Waarom zijn sommige bronnen weggelaten?'));
    const list = el('ul'); result.excluded.forEach(source => list.append(el('li', '', `${source.title} — ${source.reason}`))); excluded.append(list); root.append(excluded);
  }
}

function markResultChanged() {
  if (!latestResult || $('#result-changed')) return;
  const note = el('p', 'notice', 'Je hebt de vraag of instellingen aangepast. Klik op Zoek antwoord voor een nieuw resultaat.');
  note.id = 'result-changed'; $('#result').prepend(note);
}

// ---------- library ----------
async function renderLibrary(generation) {
  const sources = await api('/api/sources');
  if (generation !== tabGeneration) return;
  const root = $('#library-view'); root.replaceChildren();
  const heading = el('div', 'page-heading');
  heading.append(el('h1', '', 'Bronnen'), el('p', '', 'De fictieve procedures en notities waarin de demo zoekt, met het trackrecord van elke bron.')); root.append(heading);
  const filters = el('div', 'filter-row'); const list = el('div', 'source-list');
  const render = () => {
    list.replaceChildren();
    sources.filter(s => atlasFilter === 'all' || (atlasFilter === 'flagged' ? s.is_current && FLAGGED.includes(s.trust?.quadrant) : s.country === atlasFilter))
      .forEach((source, index) => list.append(sourceCard(source, index)));
  };
  [['all', 'Alle bronnen'], ['flagged', 'Vragen aandacht'], ['BE', 'België'], ['NL', 'Nederland']].forEach(([key, label]) => {
    const filter = button(label, 'filter-button' + (atlasFilter === key ? ' active' : ''), () => {
      atlasFilter = key; filters.querySelectorAll('button').forEach(b => {b.classList.toggle('active', b === filter); b.setAttribute('aria-pressed', String(b === filter));}); render();
    });
    filter.setAttribute('aria-pressed', String(atlasFilter === key)); filters.append(filter);
  });
  render(); root.append(filters, list);
}

// ---------- reviews ----------
function reviewCard(review) {
  const card = el('article', 'review-card'); const top = el('div', 'review-top');
  top.append(el('span', '', `Verzoek ${review.id}${review.mine ? ' · van jou' : ''}`), badge(review.status === 'resolved' ? 'Beoordeeld' : 'Nog te beoordelen', review.status === 'resolved' ? '' : 'warning'));
  card.append(top, el('h3', '', review.question), el('p', '', contextLabel({...review, statute: review.statute})), el('p', '', `Bronhouder: ${review.expert}`));
  if (review.note) card.append(el('p', 'quote', `“${review.note}”`));
  if (review.decision) {
    const note = el('div', 'decision-note'); note.append(el('strong', '', 'Reden van de beoordeling'), el('p', '', review.decision.rationale)); card.append(note);
    if (review.mine) card.append(button('Bekijk het beoordeelde antwoord', 'primary', () => {setForm(review.question, review); switchTab('investigate'); $('#question-form').requestSubmit();}));
  } else if (!review.can_resolve) {
    card.append(el('p', 'microcopy', review.mine ? 'Wacht op de bronhouder. Je kunt je eigen verzoek niet zelf beoordelen.' : 'Alleen een bronhouder van dit onderwerp kan dit verzoek beoordelen.'));
  } else if (!review.candidates.length) {
    card.append(el('p', 'microcopy', 'Er is nog geen actieve bron met een eigenaar om te beoordelen. Nieuwe bronkennis is nodig.'));
  } else {
    const form = el('form', 'resolution-form');
    form.append(el('p', 'microcopy', 'Kies de bron die geldt en leg uit waarom. Het trackrecord toont hoe elke bron het deed in deze situatie.'));
    const label = el('label', '', '1. Kies de bron die volgens jou geldt'); const select = el('select'); select.id = `choice-${review.id}`; label.htmlFor = select.id;
    const placeholder = el('option', '', 'Kies een bron…'); placeholder.value = ''; select.append(placeholder); select.required = true;
    review.candidates.forEach(source => {
      const suffix = [source.approved ? '' : 'niet formeel goedgekeurd', source.trust ? source.trust.quadrant_label.toLowerCase() : ''].filter(Boolean).join(' · ');
      const option = el('option', '', source.title + (suffix ? ' · ' + suffix : '')); option.value = source.citation; select.append(option);
    });
    const preview = el('div', 'decision-note'); preview.hidden = true;
    select.addEventListener('change', () => {
      const source = review.candidates.find(s => s.citation === select.value); preview.hidden = !source; preview.replaceChildren();
      if (source) preview.append(el('p', '', source.text), trustBlock(source.trust));
    });
    const reasonLabel = el('label', '', '2. Leg uit waarom je deze bron kiest'); const reason = el('textarea'); reason.id = `reason-${review.id}`; reasonLabel.htmlFor = reason.id;
    reason.required = true; reason.minLength = 20; reason.maxLength = 2000; reason.placeholder = 'Leg de keuze uit, inclusief de betekenis van de andere bron.';
    const acknowledge = el('label', 'acknowledge'); const check = el('input'); check.type = 'checkbox'; check.required = true;
    acknowledge.append(check, el('span', '', 'Ik begrijp dat dit een simulatie met fictieve kennis is; dit is geen officiële goedkeuring.'));
    const actions = el('div', 'review-actions'); const submit = button('Bewaar beoordeling', 'primary'); submit.type = 'submit'; actions.append(submit);
    form.append(label, select, preview, reasonLabel, reason, acknowledge, actions);
    form.addEventListener('submit', async event => {
      event.preventDefault(); submit.disabled = true;
      try {
        await api(`/api/reviews/${review.id}/resolve`, {citation: select.value, rationale: reason.value.trim(), demo_acknowledged: check.checked});
        toast('Beoordeling bewaard. Ze geldt voor dezelfde vraag en context.');
        await switchTab('reviews'); await updateReviewCount();
      } catch (error) {showError(error); submit.disabled = false;}
    });
    const details = el('details', 'extra-options');
    details.append(el('summary', '', 'Beoordeling invullen'), form);
    card.append(details);
  }
  return card;
}

function signalRow(source) {
  const row = el('button', 'priority-row'); row.type = 'button';
  const text = el('div'); text.append(el('strong', '', source.title), el('span', '', source.reason));
  row.append(quadrantBadge(source), text); row.addEventListener('click', () => openDossier(source.id));
  return row;
}

async function renderReviews(generation) {
  const [reviews, signals] = await Promise.all([
    api('/api/reviews'),
    state.me.user.role === 'owner' ? api('/api/track/sources') : Promise.resolve([]),
  ]);
  if (generation !== tabGeneration) return;
  const root = $('#reviews-view'); root.replaceChildren();
  const heading = el('div', 'page-heading');
  const intro = {
    consultant: 'Je verzoeken aan de bronhouders. Een beoordeling wordt hergebruikt voor dezelfde vraag en context.',
    owner: 'Verzoeken aan jouw team, en bronnen die in de praktijk opvallen. Jij beslist, met bewijs uit de praktijk.',
    manager: 'Alle verzoeken. Alleen de bronhouder van een onderwerp kan beoordelen.',
  }[state.me.user.role];
  heading.append(el('h1', '', 'Beoordelingen'), el('p', '', intro)); root.append(heading);
  const flagged = signals.filter(s => FLAGGED.includes(s.quadrant));
  if (flagged.length) root.append(el('h2', 'list-heading', 'Verzoeken van collega\'s'));
  if (!reviews.length) {
    const empty = el('div', 'empty-card');
    empty.append(el('strong', '', 'Er zijn nog geen verzoeken.'), el('p', '', state.me.user.role === 'consultant' ? 'Stel eerst een vraag en klik bij het antwoord op Vraag een beoordeling.' : 'Verzoeken van consultants verschijnen hier.'));
    root.append(empty);
  }
  reviews.forEach(review => root.append(reviewCard(review)));
  if (flagged.length) {
    root.append(el('h2', 'list-heading signals-heading', `Signalen uit de praktijk (${flagged.length})`),
      el('p', 'microcopy', 'Bronnen van jouw team die in de praktijk opvallen, ook zonder dat iemand een verzoek deed.'));
    flagged.forEach(source => root.append(signalRow(source)));
  }
}

async function updateReviewCount() {
  try {
    const reviews = await api('/api/reviews');
    const count = reviews.filter(r => r.status === 'open' && (state.me.user.role !== 'owner' || r.can_resolve)).length;
    $('#review-count').textContent = String(count); $('#review-count').hidden = !count;
  } catch (_) { /* The next explicit navigation surfaces connection failures. */ }
}

// ---------- my sources and the dossier ----------
async function renderMine(generation) {
  const sources = await api('/api/track/sources');
  if (generation !== tabGeneration) return;
  const root = $('#mine-view'); root.replaceChildren();
  const heading = el('div', 'page-heading');
  heading.append(el('h1', '', 'Mijn bronnen'), el('p', '', `Bronnen van ${state.me.user.teams.join(' en ')}, op prioriteit. Het oordeel komt uit wat er na gebruik gebeurde.`));
  root.append(heading);
  const list = el('div', 'source-list');
  sources.forEach(source => {
    const row = el('button', 'track-row'); row.type = 'button';
    const text = el('div'); text.append(el('strong', '', source.title), el('span', '', source.uses ? `${source.uses - source.fails} van ${source.uses} keer zonder correctie · twijfel na lezen ${pct(source.doubt_rate)}` : 'Nog weinig gebruik'));
    row.append(quadrantBadge(source), text, el('span', 'arrow', '→'));
    row.addEventListener('click', () => openDossier(source.id));
    list.append(row);
  });
  root.append(list);
}

function openDossier(sourceId) {
  if ($('#source-dialog').open) $('#source-dialog').close();
  state.dossier = sourceId; switchTab('dossier');
}

function kpi(label, value, sub) {
  const box = el('div', 'kpi'); box.append(el('span', 'kpi-label', label), el('strong', '', value));
  if (sub) box.append(el('span', 'kpi-sub', sub));
  return box;
}

function section(title, subtitle) {
  const box = el('section', 'panel');
  const head = el('div', 'panel-head'); head.append(el('h2', '', title));
  if (subtitle) head.append(el('span', '', subtitle));
  box.append(head);
  return box;
}

function timeline(history) {
  const months = [...new Set(history.map(row => row.month))].sort();
  if (!months.length) return el('p', 'microcopy', 'Nog geen gebruik.');
  const rows = months.map(month => {
    const items = history.filter(row => row.month === month);
    return {month, uses: items.reduce((a, r) => a + r.uses, 0), fails: items.reduce((a, r) => a + r.fails, 0), version: Math.max(...items.map(r => r.version))};
  });
  const width = 640, height = 200, left = 30, bottom = 26, top = 12;
  const max = Math.max(4, ...rows.map(r => r.uses));
  const band = (width - left - 6) / rows.length;
  const y = value => top + (height - top - bottom) * (1 - value / max);
  const chart = svg('svg', {class: 'chart', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Gebruik en misgelopen gebruik per maand'});
  [0, Math.round(max / 2), max].forEach(tick => {chart.append(svg('line', {class: 'axis', x1: left, x2: width - 6, y1: y(tick), y2: y(tick)}), svg('text', {x: left - 6, y: y(tick) + 4, 'text-anchor': 'end'}, tick));});
  rows.forEach((row, i) => {
    const x = left + i * band + band * 0.2, w = band * 0.6;
    const uses = svg('rect', {class: 'bar-uses', x, width: w, y: y(row.uses), height: y(0) - y(row.uses), rx: 2}); uses.append(svg('title', {}, `${row.month}: ${row.uses} gebruiken, ${row.fails} misgelopen`));
    chart.append(uses, svg('rect', {class: 'bar-fails', x, width: w, y: y(row.fails), height: y(0) - y(row.fails), rx: 2}),
      svg('text', {x: x + w / 2, y: height - 8, 'text-anchor': 'middle'}, new Date(row.month + '-01T12:00:00').toLocaleDateString('nl-BE', {month: 'short'})));
    if (i > 0 && row.version !== rows[i - 1].version) {
      const xl = left + i * band;
      chart.append(svg('line', {class: 'version-line', x1: xl, x2: xl, y1: top, y2: y(0)}), svg('text', {class: 'version-text', x: xl + 4, y: top + 10}, `v${row.version}`));
    }
  });
  const legend = el('div', 'legend');
  legend.append(el('span', 'legend-uses', 'gebruikt'), el('span', 'legend-fails', 'misgelopen: heropend, gecorrigeerd of geëscaleerd'));
  const wrap = el('div'); wrap.append(chart, legend); return wrap;
}

function segments(source, org) {
  const dims = Object.keys(source.segments || {}).filter(dim => source.segments[dim].length > 1);
  if (!dims.length) return el('p', 'microcopy', 'Te weinig gebruik om per situatie te tonen.');
  const finding = source.segment?.high ? source.segment : null;
  const max = Math.max(0.25, ...dims.flatMap(dim => source.segments[dim].map(row => row.rate)));
  const wrap = el('div');
  if (finding) wrap.append(el('p', 'callout warning', `Het verschil zit in ${DIMENSION[finding.dimension].toLowerCase()}: ${SEGMENT_VALUE[finding.value] || finding.value}.`));
  dims.forEach(dim => {
    const block = el('div', 'seg-block'); block.append(el('span', 'kpi-label', DIMENSION[dim] || dim));
    source.segments[dim].forEach(row => {
      const hot = finding && finding.dimension === dim && finding.value === row.value;
      const line = el('div', 'seg-row' + (hot ? ' hot' : ''));
      const track = el('span', 'seg-track'); const fill = el('span', 'seg-fill'); fill.style.width = `${Math.min(100, row.rate / max * 100)}%`;
      const norm = el('span', 'seg-norm'); norm.style.left = `${Math.min(100, org.fail_rate / max * 100)}%`; track.append(fill, norm);
      line.append(el('span', '', SEGMENT_VALUE[row.value] || row.value), track, el('span', 'seg-count', `${row.fails}/${row.uses}`));
      block.append(line);
    });
    wrap.append(block);
  });
  wrap.append(el('p', 'microcopy', `Balk: afgevlakte foutgraad. Streep: een typische bron. Alleen groepen met minstens 5 collega's.`));
  return wrap;
}

async function renderDossier(generation) {
  const d = await api(`/api/track/sources/${encodeURIComponent(state.dossier)}`);
  if (generation !== tabGeneration) return;
  const s = d.source;
  const root = $('#dossier-view'); root.replaceChildren();
  root.append(button('← Terug', 'text-button back-link', () => switchTab(state.me.user.role === 'manager' ? 'overview' : 'mine')));
  const heading = el('div', 'page-heading');
  const badges = el('div', 'badge-row'); badges.append(quadrantBadge(s), badge(s.approved ? 'Goedgekeurd' : 'Niet goedgekeurd', s.approved ? '' : 'warning'));
  if (!s.is_current) badges.append(badge('Vervangen', 'warning'));
  heading.append(el('p', 'eyebrow', `Trackrecord · ${s.id} · versie ${s.version}`), el('h1', '', s.title),
    el('p', '', `Bronhouder ${s.owner} · geldig vanaf ${readableDate(s.published_at)} · stand op ${readableDate(d.as_of)}`), badges);
  root.append(heading);
  const why = section('Waarom dit oordeel'); why.append(el('p', 'reason', s.reason)); root.append(why);
  const kpis = el('div', 'kpis');
  kpis.append(kpi('Gebruikt voor tickets', s.uses, `${s.pending} nog lopend · ${s.users} collega's`),
    kpi('Misgelopen', s.uses ? pct(s.fails / s.uses) : '–', `typische bron ${pct(d.org.fail_rate)}`),
    kpi('Twijfel na lezen', s.reads ? pct(s.doubts / s.reads) : '–', `typische bron ${pct(d.org.doubt_rate)}`),
    kpi('Te veel misgelopen', `≈ ${Math.round(s.excess_failures)}`, 'meer dan bij een typische bron'));
  root.append(kpis);
  const when = section('Wanneer loopt het mis?', 'per maand, alle versies'); when.append(timeline(d.history)); root.append(when);
  const where = section('Waar loopt het mis?', 'per situatie'); where.append(segments(s, d.org)); root.append(where);
  const cause = section('Waarom loopt het mis?', 'woordanalyse van mislukte tickets');
  if (!d.cause) cause.append(el('p', 'microcopy', 'Er liep niets mis met deze versie.'));
  else {
    cause.append(el('p', '', d.cause.summary));
    const chips = el('div', 'chips'); d.cause.terms.forEach(term => {const chip = el('span', 'chip', `${term.word} ×${term.count}`); chip.title = `z-score ${term.z}`; chips.append(chip);}); cause.append(chips);
    d.cause.examples.forEach(example => cause.append(el('p', 'quote', `“${example}”`)));
    if (d.hypothesis) {const ai = el('div', 'decision-note'); ai.append(el('strong', '', 'AI-hypothese'), el('p', '', d.hypothesis), el('p', 'microcopy', 'Alleen een formulering van de commentaren hierboven. Het oordeel komt uit vaste rekenregels.')); cause.append(ai);}
    cause.append(el('p', 'microcopy', 'Kernwoorden komen opvallend vaker voor in de mislukte tickets van deze bron dan elders (log-odds met informatieve prior, z ≥ 1,96).'));
  }
  root.append(cause);
  const follow = section('Wat vragen lezers daarna?', 'vragen kort na het lezen');
  if (s.follow_ups.length) s.follow_ups.forEach(item => follow.append(el('p', 'quote', `“${item.text}” · ${item.count}×`)));
  else follow.append(el('p', 'microcopy', 'Geen opvallende vervolgvragen.'));
  follow.append(el('p', 'microcopy', `${s.bounces} keer binnen 10 seconden weer gesloten: een vindbaarheidssignaal, geen twijfel over de inhoud.`));
  root.append(follow);
  const versions = section('Versies en effect', 'een nieuwe versie start een nieuw trackrecord');
  if (d.impact) {
    const impact = el('div', 'impact');
    const side = (label, rate, uses) => {const box = el('div'); box.append(el('span', 'kpi-label', label), el('strong', '', rate === null ? '–' : pct(rate)), el('span', 'kpi-sub', `misgelopen · ${uses} gebruiken`)); return box;};
    impact.append(side(`Versie ${d.impact.before.version}`, d.impact.before_rate, d.impact.before.uses), el('span', 'arrow', '→'), side(`Versie ${d.impact.after.version}`, d.impact.after_rate, d.impact.after.uses));
    versions.append(impact, el('p', 'microcopy', d.impact.measurable ? `≈ ${d.impact.avoided} mislukte tickets vermeden sinds de nieuwe versie. In de demo nemen we aan dat de nieuwe tekst het probleem oplost; in de praktijk meet het trackrecord dat.` : `Nog te weinig gebruik om het effect te beoordelen (${d.impact.after.uses} van minstens 5).`));
  }
  d.versions.slice().reverse().forEach(v => {
    const row = el('div', 'version-row');
    const text = el('div'); text.append(el('strong', '', `Versie ${v.version}`), el('span', 'source-meta', ` · ${readableDate(v.published_at)}${v.change_note ? ' · ' + v.change_note : ''}`));
    row.append(text, badge(v.quadrant_label, 'q-' + v.quadrant)); versions.append(row);
  });
  root.append(versions);
  if (d.can_publish) root.append(publishForm(d));
  else root.append(el('p', 'microcopy', state.me.user.role === 'manager' ? 'Alleen de bronhouder publiceert een nieuwe versie. Een kennisbeheerder kijkt mee.' : ''));
  const rules = el('details', 'extra-options rules');
  rules.append(el('summary', '', 'Hoe we rekenen'));
  const list = el('ul');
  [`Een gebruik is een bron die bij een ticket werd gebruikt. Mislukt betekent: heropend, gecorrigeerd in de loonrun of geëscaleerd.`,
    `Twijfel na lezen betekent: binnen ${d.rules.doubt_window_minutes} minuten opnieuw zoeken, een andere bron openen, een beoordeling vragen of ‘dit hielp niet’.`,
    `Recente gebruiken wegen zwaarder (halfwaardetijd ${d.rules.half_life_days} dagen); scores worden afgevlakt naar een typische bron.`,
    `Een oordeel pas vanaf ${d.rules.min_uses} gebruiken door ${d.rules.min_users} collega's, en alleen als de kans op een echt hoge score minstens ${pct(d.rules.confidence)} is.`,
    `Eén ticket telt één keer per bron; één persoon telt hoogstens ${d.rules.person_monthly_cap} keer per maand mee. We meten bronnen, geen mensen.`,
    'De AI formuleert hoogstens een hypothese. Ze beslist niets.'].forEach(text => list.append(el('li', '', text)));
  rules.append(list); root.append(rules);
}

function publishForm(d) {
  const form = el('form', 'panel publish');
  const head = el('div', 'panel-head'); head.append(el('h2', '', 'Nieuwe versie publiceren')); form.append(head);
  form.append(el('p', 'microcopy', 'Gebruik de oorzaak en de vervolgvragen hierboven. In PARALLAX verschijnt de oude versie daarna als vervangen, en oude beoordelingen vervallen.'));
  const bodyLabel = el('label', '', 'Nieuwe tekst'); const body = el('textarea'); body.id = 'new-body'; bodyLabel.htmlFor = body.id;
  body.required = true; body.minLength = 40; body.maxLength = 4000; body.rows = 6; body.value = d.source.body;
  const noteLabel = el('label', '', 'Wat is er veranderd en waarom?'); const note = el('input'); note.id = 'change-note'; noteLabel.htmlFor = note.id; note.required = true; note.minLength = 5; note.maxLength = 300;
  form.append(bodyLabel, body, noteLabel, note);
  const boxes = [];
  if (d.absorbable.length) {
    form.append(el('p', 'field-title', 'Neemt deze versie ook deze notities op?'));
    d.absorbable.forEach(source => {
      const label = el('label', 'acknowledge'); const check = el('input'); check.type = 'checkbox'; check.value = source.id;
      label.append(check, el('span', '', `${source.title} (${source.kind}) wordt vervangen door de nieuwe versie`)); boxes.push(check); form.append(label);
    });
  }
  const submit = button('Publiceer nieuwe versie', 'primary'); submit.type = 'submit';
  const actions = el('div', 'review-actions'); actions.append(submit); form.append(actions);
  form.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true;
    try {
      const result = await api(`/api/track/sources/${encodeURIComponent(d.source.id)}/versions`, {body: body.value.trim(), change_note: note.value.trim(), also_replaces: boxes.filter(b => b.checked).map(b => b.value)});
      toast(`Versie ${result.version} gepubliceerd. Het trackrecord begint opnieuw.`);
      openDossier(result.id);
    } catch (error) {showError(error); submit.disabled = false;}
  });
  return form;
}

// ---------- manager overview ----------
function scatter(data) {
  const sources = data.sources.filter(s => s.enough_fail || s.enough_doubt);
  const width = 640, height = 400, left = 46, right = 12, top = 12, bottom = 42;
  const maxX = Math.max(0.7, ...sources.map(s => s.doubt_rate)) * 1.05;
  const maxY = Math.max(0.4, ...sources.map(s => s.fail_rate)) * 1.08;
  const x = value => left + (width - left - right) * value / maxX;
  const y = value => top + (height - top - bottom) * (1 - value / maxY);
  const tx = x(data.org.doubt_threshold), ty = y(data.org.fail_threshold);
  const chart = svg('svg', {class: 'chart', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Bronnen volgens twijfel na lezen en misgelopen gebruik'});
  chart.append(
    svg('rect', {class: 'bg-dangerous', x: left, y: top, width: tx - left, height: ty - top}),
    svg('rect', {class: 'bg-broken', x: tx, y: top, width: width - right - tx, height: ty - top}),
    svg('rect', {class: 'bg-reliable', x: left, y: ty, width: tx - left, height: y(0) - ty}),
    svg('rect', {class: 'bg-unclear', x: tx, y: ty, width: width - right - tx, height: y(0) - ty}),
    svg('text', {class: 'quad dangerous', x: left + 8, y: top + 18}, 'Gevaarlijk'),
    svg('text', {class: 'quad broken', x: width - right - 8, y: top + 18, 'text-anchor': 'end'}, 'Kapot'),
    svg('text', {class: 'quad reliable', x: left + 8, y: y(0) - 8}, 'Betrouwbaar'),
    svg('text', {class: 'quad unclear', x: width - right - 8, y: y(0) - 8, 'text-anchor': 'end'}, 'Onduidelijk'),
    svg('line', {class: 'threshold', x1: tx, x2: tx, y1: top, y2: y(0)}),
    svg('line', {class: 'threshold', x1: left, x2: width - right, y1: ty, y2: ty}),
    svg('line', {class: 'axis', x1: left, x2: width - right, y1: y(0), y2: y(0)}),
    svg('text', {x: (left + width - right) / 2, y: height - 6, 'text-anchor': 'middle'}, 'Twijfel na het lezen →'),
    svg('text', {x: 12, y: (top + y(0)) / 2, 'text-anchor': 'middle', transform: `rotate(-90 12 ${(top + y(0)) / 2})`}, 'Misgelopen na gebruik →'));
  [0, 0.2, 0.4, 0.6].filter(v => v <= maxX).forEach(v => chart.append(svg('text', {x: x(v), y: y(0) + 15, 'text-anchor': 'middle'}, pct(v))));
  [0, 0.1, 0.2, 0.3, 0.4].filter(v => v <= maxY).forEach(v => chart.append(svg('text', {x: left - 6, y: y(v) + 4, 'text-anchor': 'end'}, pct(v))));
  sources.sort((a, b) => (b.quadrant === 'reliable') - (a.quadrant === 'reliable')).forEach(source => {
    const r = 4 + Math.sqrt(source.uses) * 0.6;
    const link = svg('a', {href: '#', 'aria-label': `${source.title}: ${source.quadrant_label}`});
    const dot = svg('circle', {class: `dot q-${source.quadrant}`, cx: x(source.doubt_rate), cy: y(source.fail_rate), r});
    dot.append(svg('title', {}, `${source.title} · ${source.quadrant_label} · ${pct(source.fail_rate)} misgelopen · ${pct(source.doubt_rate)} twijfel`));
    link.append(dot); link.addEventListener('click', event => {event.preventDefault(); openDossier(source.id);});
    chart.append(link);
    if (FLAGGED.includes(source.quadrant)) {
      const end = x(source.doubt_rate) > width * 0.6;
      chart.append(svg('text', {class: 'dot-label', x: x(source.doubt_rate) + (end ? -r - 5 : r + 5), y: y(source.fail_rate) + 4, 'text-anchor': end ? 'end' : 'start'}, source.title.split(':')[0]));
    }
  });
  return chart;
}

async function renderOverview(generation) {
  const d = await api('/api/overview');
  if (generation !== tabGeneration) return;
  const root = $('#overview-view'); root.replaceChildren();
  const heading = el('div', 'page-heading');
  heading.append(el('h1', '', 'Waar verdient kennis vertrouwen, en waar niet?'),
    el('p', '', `${d.total_uses} gebruiken met gekende uitkomst over ${d.sources.length} bronnen. Alles komt uit het gewone werk, zonder extra moeite.`));
  root.append(heading);
  if (d.demo_controls) {
    const controls = el('div', 'demo-controls');
    controls.append(el('span', 'badge', `Stand op ${readableDate(d.as_of)}`),
      button('Simuleer volgende maand', 'secondary', async event => {
        event.target.disabled = true;
        try {const result = await api('/api/demo/simulate-month', {}); toast(`Een maand gesimuleerd, tot ${readableDate(result.today)}.`); switchTab('overview');}
        catch (error) {showError(error); event.target.disabled = false;}
      }),
      button('Reset demo', 'text-button', async () => {
        if (!confirm('De demo terugzetten naar de beginsituatie? Beoordelingen, nieuwe versies en gesimuleerde maanden verdwijnen.')) return;
        try {await api('/api/demo/reset', {}); showLogin('De demo is teruggezet. Log opnieuw in.');} catch (error) {showError(error);}
      }));
    root.append(controls);
  }
  const gaps = d.gaps.filter(g => g.is_gap);
  const kpis = el('div', 'kpis');
  kpis.append(kpi('Gevaarlijk', d.counts.dangerous, 'vertrouwd, maar het loopt mis'), kpi('Kapot', d.counts.broken, 'twijfel én fouten'),
    kpi('Onduidelijk', d.counts.unclear, 'klopt, maar roept vragen op'), kpi('Ontbrekende kennis', gaps.length, 'gezocht, niets gevonden'),
    kpi('Open verzoeken', d.open_reviews, 'wachten op een bronhouder'));
  root.append(kpis);
  const grid = el('div', 'overview-grid');
  const matrix = section('Twijfel × uitkomst', 'klik een punt voor het trackrecord');
  matrix.append(scatter(d), el('p', 'microcopy', `Stippellijnen: ${d.rules.high_factor}× een typische bron. Grootte: aantal gebruiken.`));
  const first = section('Eerst aanpakken', 'op risico');
  const flagged = d.sources.filter(s => FLAGGED.includes(s.quadrant));
  if (!flagged.length) first.append(el('p', 'microcopy', 'Geen bronnen die aandacht vragen.'));
  flagged.forEach(source => {
    const row = el('button', 'priority-row'); row.type = 'button';
    const text = el('div'); text.append(el('strong', '', source.title), el('span', '', source.reason));
    row.append(quadrantBadge(source), text); row.addEventListener('click', () => openDossier(source.id)); first.append(row);
  });
  grid.append(matrix, first); root.append(grid);
  const gapBox = section('Ontbrekende kennis', 'gezocht zonder bruikbare bron · 90 dagen');
  if (!gaps.length) gapBox.append(el('p', 'microcopy', 'Geen duidelijke lacunes.'));
  gaps.forEach(gap => {
    const row = el('div', 'gap-row');
    row.append(el('strong', '', `“${gap.label}” en verwante vragen`), el('p', 'source-meta', `${gap.sessions} zoeksessies zonder bron · in ${pct(gap.teams_share)} daarvan volgde een vraag aan collega's · ${gap.bounces} keer snel weggeklikt`));
    gap.questions.forEach(q => row.append(el('p', 'quote', `“${q.text}” · ${q.count}×`)));
    gapBox.append(row);
  });
  root.append(gapBox);
  const evaluation = section('Werkt het? Gemeten, niet beweerd');
  if (!d.evaluation) evaluation.append(el('p', 'microcopy', 'Draai python -m trackrecord.evaluate om te meten of geplante problemen gevonden worden.'));
  else {
    const e = d.evaluation;
    evaluation.append(el('p', 'microcopy', `In ${e.seeds} nieuwe fictieve werelden zijn problemen verstopt. Het trackrecord weet niet waar, en moet ze zelf vinden.`));
    const numbers = el('div', 'kpis');
    numbers.append(kpi('Juist herkend', `${e.found}/${e.planted_total}`, 'geplante problemen'), kpi('Valse alarmen', `${e.false_alarms}/${e.normal_total}`, 'op normale bronnen'),
      kpi('Juiste context', `${e.segment_correct}/${e.seeds}`, 'arbeiders gevonden'), kpi('Lacune gevonden', `${e.gap_found}/${e.seeds}`, 'flexi-jobs'));
    evaluation.append(numbers, el('p', 'microcopy', `Zonder afvlakking en minimumbewijs: ${e.ablations.zonder_afvlakking_en_minimum_bewijs.false_alarms} valse alarmen. Een regelwijziging werd na mediaan ${e.median_days_to_detect_change} dagen opgemerkt (gemist in ${e.missed_change} van ${e.seeds} werelden).`));
  }
  root.append(evaluation);
  const privacy = section('We meten bronnen, geen mensen');
  privacy.append(el('p', 'microcopy', `Signalen worden bewaard onder een pseudoniem. Er bestaat geen overzicht per medewerker, ook niet in de API. Cijfers per situatie verschijnen pas bij minstens ${d.rules.min_users} verschillende collega's. Vrije tekst wordt ontdaan van rijksregisternummers, IBAN's, e-mailadressen en telefoonnummers. Uitkomsten komen uit het ticketsysteem en de loonrun, nooit uit de browser.`));
  root.append(privacy);
}

// ---------- navigation ----------
async function switchTab(tab) {
  const generation = ++tabGeneration;
  document.querySelectorAll('[data-tab]').forEach(node => {const active = node.dataset.tab === tab || (tab === 'dossier' && node.dataset.tab === (state.me.user.role === 'manager' ? 'overview' : 'mine')); node.classList.toggle('active', active); node.setAttribute('aria-pressed', String(active));});
  ['login', 'investigate', 'library', 'reviews', 'mine', 'dossier', 'overview'].forEach(name => {$('#' + name + '-view').hidden = name !== tab;});
  $('#error').hidden = true;
  window.scrollTo(0, 0);
  try {
    if (tab === 'library') await renderLibrary(generation);
    else if (tab === 'reviews') await renderReviews(generation);
    else if (tab === 'mine') await renderMine(generation);
    else if (tab === 'dossier') await renderDossier(generation);
    else if (tab === 'overview') await renderOverview(generation);
  } catch (error) {if (generation === tabGeneration && state.me) showError(error);}
}
function setForm(question, context) {
  $('#question').value = question; $('#country').value = context.country;
  fillClients(); $('#client').value = context.client_id || '';
  $('#statute').value = context.statute || 'alle'; $('#as-of').value = context.as_of;
  updateContextSummary();
  document.querySelectorAll('[data-scenario]').forEach(node => node.classList.toggle('selected', scenarios[node.dataset.scenario] === question));
}
function setBusy(value) {
  busy = value;
  $('#ask-button').disabled = value;
  const locked = Boolean($('#ticket').value);
  ['#question', '#as-of', '#ticket'].forEach(selector => {$(selector).disabled = value;});
  ['#country', '#client', '#statute'].forEach(selector => {$(selector).disabled = value || locked;});
  document.querySelectorAll('[data-scenario], [data-tab]').forEach(node => {node.disabled = value;});
  $('#loading').hidden = !value; $('#result').hidden = value;
}
function fillClients() {
  const current = $('#client').value;
  const options = (state.me?.clients || []).filter(c => c.country === $('#country').value);
  $('#client').replaceChildren(Object.assign(el('option', '', 'Algemeen'), {value: ''}), ...options.map(c => Object.assign(el('option', '', `${c.name} · ${c.pc}`), {value: c.id})));
  $('#client').value = options.some(c => c.id === current) ? current : '';
}
function updateContextSummary() {
  const dateText = $('#as-of').value ? readableDate($('#as-of').value) : 'Kies een datum';
  const ticket = state.tickets.find(t => t.id === $('#ticket').value);
  $('#context-summary').textContent = [ticket ? `Van ticket ${ticket.id}` : null, $('#country').value === 'BE' ? 'België' : 'Nederland',
    clientName($('#client').value), STATUTE[$('#statute').value], dateText].filter(Boolean).join(' · ');
}
function applyTicket() {
  const ticket = state.tickets.find(t => t.id === $('#ticket').value);
  $('#ticket-note').hidden = !ticket;
  ['#country', '#client', '#statute'].forEach(selector => {$(selector).disabled = Boolean(ticket);});
  if (ticket) {
    $('#country').value = ticket.country; fillClients(); $('#client').value = ticket.client_id; $('#statute').value = ticket.statute;
    $('#question').value = ticket.question;
    document.querySelectorAll('[data-scenario]').forEach(node => node.classList.remove('selected'));
  }
  state.sessionId = null;   // a new ticket is a new work session
  updateContextSummary(); markResultChanged();
}

$('#question-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  const ticketId = $('#ticket').value || null;
  const payload = {question: $('#question').value.trim(), country: $('#country').value, client_id: $('#client').value || null,
    statute: $('#statute').value, as_of: $('#as-of').value, session_id: state.sessionId, ticket_id: ticketId};
  setBusy(true); await switchTab('investigate');
  $('#question').setCustomValidity('');
  try {const result = await api('/api/ask', payload); state.sessionId = result.session_id; renderResult(result);}
  catch (error) {latestResult = null; showError(error); $('#result').replaceChildren(el('div', 'empty-card', 'Er kon geen antwoord worden opgehaald. Controleer je vraag en probeer opnieuw.'));}
  finally {setBusy(false);}
});
$('#question-form').addEventListener('invalid', event => {
  if (event.target.closest('#context-options')) $('#context-options').open = true;
}, true);
$('#country').addEventListener('change', () => {fillClients(); updateContextSummary(); markResultChanged();});
['#client', '#statute', '#as-of'].forEach(selector => $(selector).addEventListener('change', () => {updateContextSummary(); markResultChanged();}));
$('#ticket').addEventListener('change', applyTicket);
$('#question').addEventListener('input', () => {
  document.querySelectorAll('[data-scenario]').forEach(node => node.classList.remove('selected')); markResultChanged();
});
document.querySelectorAll('[data-tab]').forEach(node => node.addEventListener('click', () => switchTab(node.dataset.tab)));
document.querySelectorAll('[data-scenario]').forEach(node => node.addEventListener('click', () => {
  if (busy) return;
  if ($('#ticket').value) {$('#ticket').value = ''; applyTicket();}
  setForm(scenarios[node.dataset.scenario], {country: $('#country').value, client_id: $('#client').value || null, statute: $('#statute').value, as_of: $('#as-of').value});
  $('#question-form').requestSubmit();
}));

// ---------- login and perspective ----------
function showLogin(message) {
  state.me = null; state.csrf = ''; state.sessionId = null; latestResult = null;
  $('#main-nav').hidden = true; $('#user-box').hidden = true; $('#result').replaceChildren();
  switchTab('login');
  if (message) showError(new Error(message));
  $('#username').focus();
}
async function startSession() {
  state.me = await api('/api/me'); state.csrf = state.me.csrf;
  const role = state.me.user.role;
  $('#main-nav').hidden = false; $('#user-box').hidden = false;
  document.querySelectorAll('[data-roles]').forEach(node => {node.hidden = !node.dataset.roles.split(' ').includes(role);});
  $('#user-name').textContent = `${state.me.user.name} · ${ROLE[role]}`;
  $('#perspective-wrap').hidden = !state.me.is_admin;
  $('#user-name').hidden = state.me.is_admin;   // the perspective picker already says who you are
  if (state.me.is_admin) {
    const order = ['sara', 'an', 'kim'];
    $('#perspective').replaceChildren(...state.me.perspectives.sort((a, b) => order.indexOf(a.username) - order.indexOf(b.username))
      .map(p => Object.assign(el('option', '', `${p.display_name} · ${ROLE[p.role]}`), {value: p.username})));
    $('#perspective').value = state.me.user.username;
  }
  $('#as-of').value = state.me.today; $('#country').value = 'BE'; $('#statute').value = 'alle';
  fillClients();
  state.tickets = role === 'consultant' ? await api('/api/tickets') : [];
  $('#ticket-row').hidden = role !== 'consultant';
  $('#ticket').replaceChildren(Object.assign(el('option', '', 'Geen ticket'), {value: ''}),
    ...state.tickets.map(t => Object.assign(el('option', '', `${t.id} · ${t.client_name} · ${t.subject}`), {value: t.id})));
  $('#ticket').disabled = false; ['#country', '#client', '#statute'].forEach(selector => {$(selector).disabled = false;});
  state.sessionId = null; latestResult = null; $('#result').replaceChildren(); $('#question').value = '';
  $('#ticket-note').hidden = true;
  updateContextSummary(); updateReviewCount();
  await switchTab(HOME[role]);
}
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('#login-button').disabled = true;
  try {
    await api('/api/login', {username: $('#username').value.trim().toLowerCase(), password: $('#password').value});
    $('#password').value = '';
    await startSession();
  } catch (error) {showError(error);}
  finally {$('#login-button').disabled = false;}
});
$('#logout').addEventListener('click', async () => {
  try {await api('/api/logout', {});} catch (_) { /* already logged out */ }
  showLogin();
});
$('#perspective').addEventListener('change', async () => {
  try {await api('/api/act-as', {username: $('#perspective').value}); await startSession(); toast(`Je bekijkt de demo nu als ${state.me.user.name}.`);}
  catch (error) {showError(error);}
});
(async () => {
  try {await startSession();} catch (_) {showLogin();}
})();
