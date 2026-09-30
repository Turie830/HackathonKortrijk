const $ = selector => document.querySelector(selector);
let busy = false;
let latestResult = null;
let tabGeneration = 0;
let atlasFilter = 'all';
const statuses = {
  supported: ['Antwoord gevonden', 'Dit zeggen de goedgekeurde bronnen'],
  conflict: ['Bronnen spreken elkaar tegen', 'Er is nog geen eenduidig antwoord'],
  review: ['Bevestiging nodig', 'Deze informatie moet eerst worden gecontroleerd'],
  missing: ['Geen bron gevonden', 'We hebben nog geen antwoord op deze vraag'],
  reviewed: ['Beoordeeld in de demo', 'Dit antwoord is gekozen na beoordeling'],
};
const scenarios = {
  deadline: 'Wat is de deadline voor de maandelijkse verwerking?',
  correction: 'Wie moet een looncorrectie controleren en goedkeuren?',
  handover: 'Hoe draag ik een klantdossier over aan een nieuwe consultant?',
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function button(text, className, action) {
  const node = el('button', className, text); node.type = 'button';
  if (action) node.addEventListener('click', action);
  return node;
}
function showError(error) {$('#error').textContent = error.message || 'Er ging iets mis.'; $('#error').hidden = false;}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
  });
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
  return new Intl.DateTimeFormat('nl-BE', {day: 'numeric', month: 'long', year: 'numeric'}).format(new Date(value + 'T12:00:00'));
}
function contextLabel(context) {
  return `${context.country === 'BE' ? 'België' : 'Nederland'} · ${context.client_id ? 'Demo Acme' : 'Algemeen'} · ${readableDate(context.as_of)}`;
}
function openSource(source) {
  const root = $('#source-dialog-content'); root.replaceChildren();
  const heading = el('h2', '', source.title); heading.id = 'source-dialog-title'; root.append(heading);
  root.append(el('p', 'source-meta', `${source.kind} · ${source.country === 'BE' ? 'België' : 'Nederland'} · ${source.client_id ? 'Demo Acme' : 'Algemeen'}`));
  root.append(el('p', 'source-meta', `Bronhouder: ${source.owner || 'Niet bekend'} · Bijgewerkt op ${readableDate(source.updated_at)}`));
  root.append(el('p', 'source-meta', `Geldig vanaf ${readableDate(source.valid_from)}${source.valid_until ? ' tot ' + readableDate(source.valid_until) : ' · Geen einddatum vastgelegd'}`));
  root.append(el('span', 'badge' + (source.approved ? '' : ' warning'), source.approved ? '✓ Formeel goedgekeurd' : '○ Niet formeel goedgekeurd'));
  root.append(el('blockquote', '', source.text || source.passages.map(p => p.text).join('\n\n')));
  if (source.warnings) source.warnings.forEach(warning => root.append(el('span', 'badge warning', warning)));
  root.append(el('p', 'citation-code', source.citation || source.id));
  root.append(el('p', 'microcopy', 'Fictieve voorbeeldbron. De inhoud wordt letterlijk weergegeven.'));
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
  if (source.active === false) card.classList.add('historical');
  if (result?.decision?.citation === source.citation) card.classList.add('selected-source');
  const top = el('div', 'source-top');
  let state = source.approved ? 'Goedgekeurd' : 'Niet goedgekeurd';
  if (source.replaced_by?.length) state = 'Vervangen';
  else if (source.active === false) state = 'Niet geldig op deze datum';
  top.append(el('h3', '', source.title), el('span', 'badge' + (source.active === false || !source.approved ? ' warning' : ''), state));
  card.append(top);
  card.append(el('p', 'source-meta', `${source.kind} · ${source.owner || 'Eigenaar onbekend'}`));
  const claim = result?.conflicts.flatMap(c => c.evidence).find(e => e.citation === source.citation);
  const text = source.text || source.passages.map(p => p.text).join(' ');
  card.append(el('p', 'source-excerpt', claim ? 'Deze bron zegt: ' + claim.value : text.length > 180 ? text.slice(0, 180).trimEnd() + '…' : text));
  card.append(button('Lees volledige bron', 'text-button', () => openSource(source)));
  return card;
}

function renderEvidence(result) {
  const section = el('section', 'sources-section');
  const title = el('h2', 'section-label'); title.append(el('span', 'step', '3'), el('span', '', 'Gebruikte bronnen'));
  section.append(title, el('p', '', result.sources.length ? 'Bekijk de documenten waarop dit resultaat is gebaseerd.' : 'Er is geen passend document gevonden voor deze vraag.'));
  const list = el('div', 'source-list');
  result.sources.forEach((source, index) => list.append(sourceCard(source, index, result)));
  section.append(list);
  return section;
}

function renderInsight(result) {
  const panel = el('section', 'answer-card ' + result.status);
  const top = el('div', 'answer-top');
  const title = el('h2', 'section-label'); title.append(el('span', 'step', '2'), el('span', '', 'Antwoord'));
  top.append(title, el('span', 'badge' + (result.needs_review ? ' warning' : ''), statuses[result.status][0]));
  panel.append(top, el('h3', '', statuses[result.status][1]), el('p', 'answer-text', result.answer));
  if (result.conflicts.length && !result.decision) {
    const differences = el('ul', 'conflict-list');
    result.conflicts.forEach(conflict => conflict.evidence.forEach(evidence => {
      const row = el('li'); row.append(el('span', '', evidence.title), el('strong', '', evidence.value)); differences.append(row);
    }));
    panel.append(differences);
  }
  if (result.decision) {
    const reason = el('div', 'decision-note');
    reason.append(el('strong', '', 'Reden van de keuze'), el('p', '', result.decision.rationale)); panel.append(reason);
    panel.append(el('p', 'microcopy', 'Dit is een demobeoordeling. De oorspronkelijke bronnen blijven hieronder zichtbaar.'));
  }
  panel.append(el('p', 'result-context', 'Dit resultaat geldt voor: ' + contextLabel(result.context)));
  const review = el('div', 'review-action');
  review.append(el('p', '', result.needs_review ? `${result.expert} kan helpen om deze vraag te beoordelen.` : 'Wil je dit antwoord laten controleren?'));
  let requestId = null;
  const action = button(result.decision ? 'Bekijk beoordeling' : 'Vraag een beoordeling', 'secondary', async () => {
    if (result.decision || requestId !== null) {await switchTab('reviews'); return;}
    action.disabled = true;
    try {
      const request = await api('/api/reviews', {assessment_id: result.assessment_id});
      requestId = request.id;
      action.textContent = 'Bekijk je verzoek';
      review.append(el('p', 'success-message', 'Verzoek opgeslagen. Je vindt het bij Beoordelingen.'));
      await updateReviewCount();
    } catch (error) {showError(error);}
    finally {action.disabled = false;}
  });
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
  details.append(el('summary', '', 'Vergelijk een ander land of een eerdere datum'));
  const content = el('div', 'extra-content');
  content.append(el('p', '', 'We stellen dezelfde vraag in twee andere situaties.'));
  details.append(content);
  let requested = false;
  details.addEventListener('toggle', async () => {
    if (!details.open || requested) return;
    requested = true;
    const loading = el('p', '', 'Vergelijking laden…'); content.append(loading);
    try {
      const alternatives = await api(`/api/assessments/${result.assessment_id}/compare`);
      const grid = el('div', 'comparison-grid');
      alternatives.forEach((alternative, index) => {
        const card = el('article', 'comparison-card');
        card.append(el('h4', '', index === 0 ? 'Ander land' : 'Eerdere datum'), el('p', 'context', contextLabel(alternative.context)), el('p', '', alternative.answer));
        card.append(button('Bekijk dit antwoord', 'text-button', () => {
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
  if (result.stale_decision) root.append(el('div', 'notice', 'De bronnen zijn veranderd sinds de vorige beoordeling. Laat het antwoord opnieuw controleren.'));
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

async function renderLibrary(generation) {
  const sources = await api('/api/sources');
  if (generation !== tabGeneration) return;
  const root = $('#library-view'); root.replaceChildren();
  const heading = el('div', 'page-heading');
  heading.append(el('h1', '', 'Bronnen'), el('p', '', 'Dit zijn de voorbeeldprocedures en notities waarin de demo zoekt.')); root.append(heading);
  const filters = el('div', 'filter-row'); const list = el('div', 'source-list');
  const render = () => {list.replaceChildren(); sources.filter(s => atlasFilter === 'all' || s.country === atlasFilter).forEach((source, index) => list.append(sourceCard(source, index)));};
  [['all', 'Alle bronnen'], ['BE', 'België'], ['NL', 'Nederland']].forEach(([key, label]) => {
    const filter = button(label, 'filter-button' + (atlasFilter === key ? ' active' : ''), () => {
      atlasFilter = key; filters.querySelectorAll('button').forEach(b => {b.classList.toggle('active', b === filter); b.setAttribute('aria-pressed', String(b === filter));}); render();
    });
    filter.setAttribute('aria-pressed', String(atlasFilter === key)); filters.append(filter);
  });
  render(); root.append(filters, list);
}

function reviewCard(review) {
  const card = el('article', 'review-card'); const top = el('div', 'review-top');
  top.append(el('span', '', `Verzoek ${review.id}`), el('span', 'badge' + (review.status === 'resolved' ? '' : ' warning'), review.status === 'resolved' ? 'Beoordeeld' : 'Nog te beoordelen'));
  card.append(top, el('h3', '', review.question), el('p', '', contextLabel(review)), el('p', '', `Voorgestelde beoordelaar: ${review.expert}`));
  if (review.decision) {
    const note = el('div', 'decision-note'); note.append(el('strong', '', 'Reden van de beoordeling'), el('p', '', review.decision.rationale)); card.append(note);
    card.append(button('Bekijk het beoordeelde antwoord', 'primary', () => {setForm(review.question, review); switchTab('investigate'); $('#question-form').requestSubmit();}));
  } else if (!review.assessment_id || !review.candidates.length) {
    card.append(el('p', 'microcopy', review.assessment_id ? 'Er is nog geen actieve bron met een eigenaar om te beoordelen. Nieuwe bronkennis is nodig.' : 'Dit verzoek komt uit de vorige demo. Onderzoek de vraag opnieuw voor een volledig dossier.'));
    card.append(button('Zoek opnieuw', 'text-button', () => {setForm(review.question, review); switchTab('investigate'); $('#question-form').requestSubmit();}));
  } else {
    const form = el('form', 'resolution-form');
    form.append(el('p', 'microcopy', 'In deze demo kun je zelf een beoordeling invullen. Kies de juiste bron en leg uit waarom.'));
    const label = el('label', '', '1. Kies de bron die volgens jou geldt'); const select = el('select'); select.id = `choice-${review.id}`; label.htmlFor = select.id;
    const placeholder = el('option', '', 'Kies een bron…'); placeholder.value = ''; select.append(placeholder); select.required = true;
    review.candidates.forEach(source => {const option = el('option', '', source.title + (source.approved ? '' : ' · Nog niet formeel goedgekeurd')); option.value = source.citation; select.append(option);});
    const preview = el('div', 'decision-note'); preview.hidden = true;
    select.addEventListener('change', () => {const source = review.candidates.find(s => s.citation === select.value); preview.hidden = !source; preview.textContent = source?.text || '';});
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
        await switchTab('reviews'); await updateReviewCount();
      } catch (error) {showError(error); submit.disabled = false;}
    });
    const details = el('details', 'extra-options');
    details.append(el('summary', '', 'Beoordeling invullen'), form);
    card.append(details);
  }
  return card;
}

async function renderReviews(generation) {
  const reviews = await api('/api/reviews'); if (generation !== tabGeneration) return;
  const root = $('#reviews-view'); root.replaceChildren();
  const heading = el('div', 'page-heading');
  heading.append(el('h1', '', 'Beoordelingen'), el('p', '', 'Bekijk je verzoeken en vul voor de demo een beoordeling in.')); root.append(heading);
  if (!reviews.length) {
    const empty = el('div', 'empty-card'); empty.append(el('strong', '', 'Je hebt nog geen beoordeling gevraagd.'), el('p', '', 'Stel eerst een vraag en klik bij het antwoord op Vraag een beoordeling.')); root.append(empty);
  }
  reviews.forEach(review => root.append(reviewCard(review)));
}

async function updateReviewCount() {
  try {const reviews = await api('/api/reviews'); const count = reviews.filter(r => r.status === 'open').length; $('#review-count').textContent = String(count); $('#review-count').hidden = !count;}
  catch (_) { /* The next explicit navigation surfaces connection failures. */ }
}
async function switchTab(tab) {
  const generation = ++tabGeneration;
  document.querySelectorAll('[data-tab]').forEach(node => {const active = node.dataset.tab === tab; node.classList.toggle('active', active); node.setAttribute('aria-pressed', String(active));});
  ['investigate', 'library', 'reviews'].forEach(name => {$('#' + name + '-view').hidden = name !== tab;});
  $('#error').hidden = true;
  try {if (tab === 'library') await renderLibrary(generation); else if (tab === 'reviews') await renderReviews(generation);}
  catch (error) {if (generation === tabGeneration) showError(error);}
}
function setForm(question, context) {
  $('#question').value = question; $('#country').value = context.country;
  $('#client').value = context.client_id || ''; $('#client').disabled = context.country === 'NL'; $('#as-of').value = context.as_of;
  updateContextSummary();
  document.querySelectorAll('[data-scenario]').forEach(node => node.classList.toggle('selected', scenarios[node.dataset.scenario] === question));
}
function setBusy(value) {
  busy = value;
  $('#ask-button').disabled = value;
  ['#question', '#country', '#as-of'].forEach(selector => {$(selector).disabled = value;});
  $('#client').disabled = value || $('#country').value === 'NL';
  document.querySelectorAll('[data-scenario], [data-tab]').forEach(node => {node.disabled = value;});
  $('#loading').hidden = !value; $('#result').hidden = value;
}
$('#question-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  const payload = {question: $('#question').value.trim(), country: $('#country').value, client_id: $('#client').value || null, as_of: $('#as-of').value};
  setBusy(true); await switchTab('investigate');
  $('#question').setCustomValidity('');
  try {renderResult(await api('/api/ask', payload));}
  catch (error) {latestResult = null; showError(error); $('#result').replaceChildren(el('div', 'empty-card', 'Er kon geen antwoord worden opgehaald. Controleer je vraag en probeer opnieuw.'));}
  finally {setBusy(false);}
});
$('#question-form').addEventListener('invalid', event => {
  if (event.target.closest('#context-options')) $('#context-options').open = true;
}, true);
function updateContextSummary() {
  const dateText = $('#as-of').value ? readableDate($('#as-of').value) : 'Kies een datum';
  $('#context-summary').textContent = `${$('#country').value === 'BE' ? 'België' : 'Nederland'} · ${$('#client').value ? 'Demo Acme' : 'Algemeen'} · ${dateText}`;
}
$('#country').addEventListener('change', () => {
  if ($('#country').value === 'NL') $('#client').value = '';
  $('#client').disabled = $('#country').value === 'NL'; updateContextSummary(); markResultChanged();
});
['#client', '#as-of'].forEach(selector => $(selector).addEventListener('change', () => {updateContextSummary(); markResultChanged();}));
$('#question').addEventListener('input', () => {
  document.querySelectorAll('[data-scenario]').forEach(node => node.classList.remove('selected')); markResultChanged();
});
document.querySelectorAll('[data-tab]').forEach(node => node.addEventListener('click', () => switchTab(node.dataset.tab)));
document.querySelectorAll('[data-scenario]').forEach(node => node.addEventListener('click', () => {
  if (busy) return;
  setForm(scenarios[node.dataset.scenario], {country: $('#country').value, client_id: $('#client').value || null, as_of: $('#as-of').value});
  $('#question-form').requestSubmit();
}));
updateContextSummary();
updateReviewCount();
