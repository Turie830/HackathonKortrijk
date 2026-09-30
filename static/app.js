const $ = selector => document.querySelector(selector);
let busy = false;
let activeTab = 'investigate';
let latestResult = null;
let tabGeneration = 0;
let atlasFilter = 'all';
const statuses = {
  supported: ['BRONNEN GEVEN HOUVAST', 'Je kunt de onderbouwing volgen.'],
  conflict: ['HIER ZIT DE TWIJFEL', 'Twee bronnen. Twee antwoorden.'],
  review: ['EEN STUK VAN HET VERHAAL ONTBREEKT', 'Eerst even bevestigen.'],
  missing: ['DE KENNIS IS NOG NIET GEVANGEN', 'Dit vraagt om een mens.'],
  reviewed: ['BEOORDEELD IN HET DEMOLAB', 'Een keuze met een reden.'],
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
function contextLabel(context) {
  return `${context.country === 'BE' ? 'België' : 'Nederland'} / ${context.client_id ? 'Demo Acme' : 'Algemeen'} / ${context.as_of}`;
}
function openSource(source) {
  const root = $('#source-dialog-content'); root.replaceChildren();
  const heading = el('h2', '', source.title); heading.id = 'source-dialog-title'; root.append(heading);
  root.append(el('p', 'source-meta', `${source.kind} · ${source.country} · ${source.client_id ? 'Demo Acme' : 'Algemeen'}`));
  root.append(el('p', 'source-meta', `Bronhouder: ${source.owner || 'Niet bekend'} · Bijgewerkt op ${source.updated_at}`));
  root.append(el('p', 'source-meta', `Geldig vanaf ${source.valid_from}${source.valid_until ? ' tot ' + source.valid_until : ' · Geen einddatum vastgelegd'}`));
  root.append(el('span', 'source-state' + (source.approved ? '' : ' warning'), source.approved ? '✓ Formeel goedgekeurd' : '○ Niet formeel goedgekeurd'));
  root.append(el('blockquote', '', source.text || source.passages.map(p => p.text).join('\n\n')));
  if (source.warnings) source.warnings.forEach(warning => root.append(el('span', 'source-state warning', warning)));
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
  if (source.in_conflict) card.classList.add('conflicting');
  if (source.active === false) card.classList.add('historical');
  if (result?.decision?.citation === source.citation) card.classList.add('selected-source');
  const header = el('div', 'source-header');
  header.append(el('span', 'source-type', (source.kind === 'Teams-notitie' ? '◌ ' : '▤ ') + source.kind.toUpperCase()), el('span', 'source-index', String(index + 1).padStart(2, '0')));
  card.append(header, el('h4', '', source.title));
  const claim = result?.conflicts.flatMap(c => c.evidence).find(e => e.citation === source.citation);
  if (claim) card.append(el('div', 'claim-value', claim.value));
  card.append(el('p', 'source-meta', source.owner || 'Bronhouder ontbreekt'));
  card.append(el('p', 'source-meta', `Geldig vanaf ${source.valid_from}`));
  if (source.replaced_by?.length) card.append(el('span', 'source-state warning', '↺ Vervangen'));
  else if (source.active === false) card.append(el('span', 'source-state warning', '○ Buiten geldigheid'));
  else if (source.in_conflict) {
    card.append(el('span', 'source-state conflict', '≠ Verschillende inhoud'));
    card.append(el('p', 'source-meta', source.approved ? '✓ Formeel goedgekeurd' : '○ Niet formeel goedgekeurd'));
  }
  else card.append(el('span', 'source-state' + (source.approved ? '' : ' warning'), source.approved ? '✓ Formeel goedgekeurd' : '○ Goedkeuring ontbreekt'));
  card.append(button('Lees de passage ↗', 'passage-button', () => openSource(source)));
  return card;
}

function renderEvidence(result) {
  const panel = el('section', 'evidence-panel');
  const header = el('div', 'panel-header'); header.append(el('h3', '', 'De herkomst van het antwoord'), el('span', '', `${result.sources.length} bronpassages`)); panel.append(header);
  if (!result.sources.length) {
    const empty = el('div', 'empty-card'); empty.append(el('strong', '', 'Een lege plek op de kaart.'), el('p', '', 'Er is geen passende bron gevonden. De bronhouder kan deze kennis aanvullen.'));
    panel.append(empty); return panel;
  }
  const lenses = el('div', 'lens-bar');
  const help = el('p', 'lens-help', 'Volg de bronnen en open de passages die het antwoord dragen.');
  const map = el('div', 'evidence-map');
  const cards = el('div', 'source-grid');
  const pairs = result.sources.map((source, index) => {const card = sourceCard(source, index, result); cards.append(card); return [source, card];});
  [
    ['all', 'Alles', 'Volg de bronnen en open de passages die het antwoord dragen.'],
    ['date', 'Geldigheid', 'Uitgelicht: bronnen buiten hun geldigheidsperiode of met een opvolger.'],
    ['owner', 'Bronhouder', 'Uitgelicht: kennis zonder eigenaar of formele goedkeuring.'],
    ['agreement', 'Verschillen', 'Uitgelicht: passages met een vastgelegd inhoudelijk verschil.'],
  ].forEach(([key, label, explanation]) => {
    const lens = button(label, 'lens' + (key === 'all' ? ' active' : ''), () => {
      lenses.querySelectorAll('button').forEach(b => {b.classList.toggle('active', b === lens); b.setAttribute('aria-pressed', String(b === lens));});
      help.textContent = explanation;
      pairs.forEach(([source, card]) => {
        const issue = key === 'all' || (key === 'date' ? !source.checks.date || !source.checks.current : key === 'owner' ? !source.checks.owner || !source.checks.approval : source.in_conflict);
        card.classList.toggle('muted-source', !issue);
      });
    });
    lens.setAttribute('aria-pressed', String(key === 'all')); lenses.append(lens);
  });
  map.append(cards);
  const connection = el('div', 'connection');
  const relation = el('div', 'relation' + (result.conflicts.length ? ' conflict' : ''));
  relation.append(el('span', '', result.conflicts.length ? '≠' : '↓'), el('strong', '', result.conflicts.length ? 'Hier lopen de verhalen uiteen' : result.sources.some(s => s.replaced_by.length) ? 'Een nieuwe versie neemt het over' : 'Dit draagt het antwoord'));
  connection.append(relation); map.append(connection);
  const scopeConflict = result.conflicts.some(c => c.scope_difference);
  map.append(el('p', 'map-caption', scopeConflict ? 'Het toepassingsgebied verschilt. Laat bevestigen of dit een echte uitzondering is.' : result.conflicts.length ? 'Een recentere chat bewijst niet dat een goedgekeurde procedure vervallen is.' : 'Geen conflict gevonden in de vastgelegde claims. Onbekende verschillen blijven mogelijk.'));
  const counts = el('div', 'coverage-strip');
  [[result.coverage.retrieved, 'gevonden passages'], [result.coverage.active, 'geldig op deze datum'], [result.coverage.conflicts, result.coverage.conflicts === 1 ? 'inhoudelijk verschil' : 'inhoudelijke verschillen']].forEach(([number, label]) => {
    const count = el('div'); count.append(el('strong', '', number), el('span', '', label)); counts.append(count);
  });
  panel.append(lenses, help, map, counts);
  return panel;
}

function renderInsight(result) {
  const panel = el('section', 'insight ' + result.status);
  panel.append(el('div', 'status-label', statuses[result.status][0]), el('h2', '', statuses[result.status][1]), el('p', 'answer-text', result.answer));
  if (result.decision) {
    const note = el('div', 'decision-note'); note.append(el('strong', '', 'Waarom deze bron gekozen is'), el('span', '', result.decision.rationale)); panel.append(note);
    panel.append(el('p', 'microcopy', 'Deze demobeoordeling geldt alleen voor deze vraag, context en ongewijzigde bronnen. De oorspronkelijke verschillen blijven zichtbaar.'));
  }
  const refs = el('div', 'citation-buttons');
  result.citations.forEach(citation => {const source = result.sources.find(s => s.citation === citation); if (source) refs.append(button('↗ ' + citation, 'citation-link', () => openSource(source)));});
  panel.append(refs);
  const checklist = el('ul', 'checklist');
  const active = result.sources.filter(s => s.active);
  [
    ['Context', contextLabel(result.context), true],
    ['Geldigheid', `${active.length} van ${result.sources.length} actief`, active.length > 0],
    ['Bronhouder', active.length && active.every(s => s.owner) ? 'Bekend' : 'Niet volledig bekend', active.length > 0 && active.every(s => s.owner)],
    ['Verschillen', result.conflicts.length ? `${result.conflicts.length} ${result.decision ? 'met demobeoordeling' : 'vraagt om beoordeling'}` : 'Geen gevonden in vastgelegde claims', (!result.conflicts.length || !!result.decision) && result.sources.length > 0],
  ].forEach(([label, value, ok]) => {const row = el('li'); row.append(el('span', '', label), el('span', ok ? 'ok' : 'issue', value)); checklist.append(row);});
  panel.append(checklist);
  const expert = el('div', 'expert-box');
  const person = el('div', 'expert-line');
  const name = el('div'); name.append(el('strong', '', result.expert), el('small', '', 'Voorgestelde bronhouder · op basis van bronmetadata'));
  person.append(el('span', 'avatar', result.expert.split(' ').slice(0, 2).map(w => w[0]).join('')), name); expert.append(person);
  const action = button(result.decision ? 'Bekijk de beoordeling ↗' : 'Leg de twijfel voor ↗', 'review-button', async () => {
    if (result.decision) {await switchTab('reviews'); return;}
    action.disabled = true;
    try {
      const request = await api('/api/reviews', {assessment_id: result.assessment_id});
      action.textContent = `Verzoek #${request.id} · Open Kennislus ↗`; action.disabled = false;
      const replacement = action.cloneNode(true); action.replaceWith(replacement);
      replacement.addEventListener('click', () => switchTab('reviews'));
      expert.append(el('p', 'success-message', 'De vraag, context en bronpassages zijn samen vastgelegd.'));
      await updateReviewCount();
    } catch (error) {showError(error); action.disabled = false;}
  });
  expert.append(action, el('p', 'microcopy', 'Demobeoordelingen blijven lokaal. Er wordt geen bericht naar een expert verstuurd.')); panel.append(expert);
  if (result.model_notice) panel.append(el('p', 'microcopy', result.model_notice));
  return panel;
}

function renderComparison(result) {
  const box = el('section', 'compare-box'); const heading = el('div', 'compare-heading'); const text = el('div');
  text.append(el('h3', '', 'Verander de context. Kijk wat er verschuift.'), el('p', '', 'Dezelfde vraag, een ander land of een eerdere datum.'));
  const run = button('Vergelijk perspectieven ↗', 'compare-button', async () => {
    run.disabled = true;
    try {
      const alternatives = await api(`/api/assessments/${result.assessment_id}/compare`);
      const grid = el('div', 'comparison-grid');
      alternatives.forEach(alternative => {
        const card = el('article', 'comparison-card');
        card.append(el('span', 'changed-label', alternative.changed ? '↗ ANDERE ONDERBOUWING' : '— ZELFDE UITKOMST'), el('h4', '', alternative.label), el('p', 'context', contextLabel(alternative.context)), el('p', '', alternative.answer));
        card.append(button('Onderzoek in deze context →', '', () => {
          setForm(result.question, alternative.context); $('#question-form').requestSubmit();
        }));
        grid.append(card);
      });
      box.append(grid); run.textContent = 'Perspectieven vergeleken ✓';
    } catch (error) {showError(error); run.disabled = false;}
  });
  heading.append(text, run); box.append(heading); return box;
}

function renderResult(result) {
  latestResult = result;
  const root = $('#result'); root.replaceChildren();
  if (result.stale_decision) root.append(el('div', 'notice', 'Een eerdere beoordeling is vervallen: de bronnen zijn gewijzigd. Beoordeel de nieuwe informatie opnieuw.'));
  const bar = el('div', 'dossier-bar'); const title = el('div', 'dossier-title');
  title.append(el('h2', '', 'Jouw kennisdossier'), el('span', 'dossier-id', result.assessment_id));
  const download = el('a', 'text-button', '↓ Bewaar de onderbouwing');
  download.href = `/api/assessments/${result.assessment_id}/receipt`; download.setAttribute('download', result.assessment_id + '.md');
  bar.append(title, download); root.append(bar);
  const grid = el('div', 'dossier-grid'); grid.append(renderEvidence(result), renderInsight(result)); root.append(grid, renderComparison(result));
  if (result.excluded.length) {
    const excluded = el('details', 'excluded'); excluded.append(el('summary', '', `${result.excluded.length} bronnen buiten deze context · Bekijk waarom`));
    const list = el('ul'); result.excluded.forEach(source => list.append(el('li', '', `${source.title} — ${source.reason}`))); excluded.append(list); root.append(excluded);
  }
  root.append(el('p', 'timestamp', 'Momentopname · ' + contextLabel(result.context) + ' · ' + result.notice));
}

async function renderLibrary(generation) {
  const sources = await api('/api/sources');
  if (generation !== tabGeneration) return;
  const root = $('#library-view'); root.replaceChildren();
  const heading = el('div', 'page-heading'); const title = el('div'); title.append(el('div', 'eyebrow', '02 — BRONNENATLAS'), el('h1', '', 'Achter ieder antwoord, een bron.')); heading.append(title); root.append(heading);
  root.append(el('p', 'atlas-intro', 'Procedures, gesprekken en klantafspraken. Elke bron heeft een herkomst en een toepassingsgebied. Onderzoek hoe die samenhangen; een datum alleen vertelt niet het hele verhaal.'));
  const filters = el('div', 'atlas-filter'); const grid = el('div', 'atlas-grid');
  const render = () => {grid.replaceChildren(); sources.filter(s => atlasFilter === 'all' || s.country === atlasFilter).forEach((source, index) => grid.append(sourceCard(source, index)));};
  [['all', 'Alle bronnen'], ['BE', 'België'], ['NL', 'Nederland']].forEach(([key, label]) => {
    const filter = button(label, 'filter-button' + (atlasFilter === key ? ' active' : ''), () => {
      atlasFilter = key; filters.querySelectorAll('button').forEach(b => {b.classList.toggle('active', b === filter); b.setAttribute('aria-pressed', String(b === filter));}); render();
    });
    filter.setAttribute('aria-pressed', String(atlasFilter === key)); filters.append(filter);
  });
  render(); root.append(filters, grid);
}

function reviewCard(review) {
  const card = el('article', 'review-card'); const top = el('div', 'review-top');
  top.append(el('span', 'eyebrow', `VERZOEK ${String(review.id).padStart(2, '0')}`), el('span', 'review-state' + (review.status === 'resolved' ? ' resolved' : ''), review.status === 'resolved' ? '↺ Kennis vastgelegd' : '○ Wacht op beoordeling'));
  card.append(top, el('h3', '', review.question), el('p', '', contextLabel(review)), el('p', '', `Bronhouder: ${review.expert}`));
  if (review.decision) {
    const note = el('div', 'decision-note'); note.append(el('strong', '', 'Gekozen bron: ' + review.decision.citation), el('p', '', review.decision.rationale)); card.append(note);
    card.append(button('Onderzoek opnieuw met deze kennis ↗', 'primary', () => {setForm(review.question, review); switchTab('investigate'); $('#question-form').requestSubmit();}));
  } else if (!review.assessment_id || !review.candidates.length) {
    card.append(el('p', 'microcopy', review.assessment_id ? 'Er is nog geen actieve bron met een eigenaar om te beoordelen. Nieuwe bronkennis is nodig.' : 'Dit verzoek komt uit de vorige demo. Onderzoek de vraag opnieuw voor een volledig dossier.'));
    card.append(button('Open deze vraag opnieuw →', 'text-button', () => {setForm(review.question, review); switchTab('investigate'); $('#question-form').requestSubmit();}));
  } else {
    const form = el('form', 'resolution-form');
    form.append(el('p', 'microcopy', 'Neem voor deze oefening de rol van bronhouder aan. Je keuze wordt als demobeoordeling opgeslagen, inclusief motivatie.'));
    const label = el('label', '', 'Welke bron geldt volgens jouw beoordeling?'); const select = el('select'); select.id = `choice-${review.id}`; label.htmlFor = select.id;
    const placeholder = el('option', '', 'Kies een bron…'); placeholder.value = ''; select.append(placeholder); select.required = true;
    review.candidates.forEach(source => {const option = el('option', '', source.title + (source.approved ? '' : ' · Nog niet formeel goedgekeurd')); option.value = source.citation; select.append(option);});
    const preview = el('div', 'decision-note'); preview.hidden = true;
    select.addEventListener('change', () => {const source = review.candidates.find(s => s.citation === select.value); preview.hidden = !source; preview.textContent = source?.text || '';});
    const reasonLabel = el('label', '', 'Waarom geldt deze bron?'); const reason = el('textarea'); reason.id = `reason-${review.id}`; reasonLabel.htmlFor = reason.id;
    reason.required = true; reason.minLength = 20; reason.maxLength = 2000; reason.placeholder = 'Leg de keuze uit, inclusief de betekenis van de andere bron.';
    const acknowledge = el('label', 'acknowledge'); const check = el('input'); check.type = 'checkbox'; check.required = true;
    acknowledge.append(check, el('span', '', 'Ik begrijp dat dit een simulatie met fictieve kennis is; dit is geen officiële goedkeuring.'));
    const actions = el('div', 'review-actions'); const submit = button('Leg beoordeling vast ↺', 'primary'); submit.type = 'submit'; actions.append(submit);
    form.append(label, select, preview, reasonLabel, reason, acknowledge, actions);
    form.addEventListener('submit', async event => {
      event.preventDefault(); submit.disabled = true;
      try {
        await api(`/api/reviews/${review.id}/resolve`, {citation: select.value, rationale: reason.value.trim(), demo_acknowledged: check.checked});
        await switchTab('reviews'); await updateReviewCount();
      } catch (error) {showError(error); submit.disabled = false;}
    });
    card.append(form);
  }
  return card;
}

async function renderReviews(generation) {
  const reviews = await api('/api/reviews'); if (generation !== tabGeneration) return;
  const root = $('#reviews-view'); root.replaceChildren();
  const heading = el('div', 'page-heading'); const title = el('div'); title.append(el('div', 'eyebrow', '03 — KENNISLUS'), el('h1', '', 'Eén keer uitgezocht. Samen onthouden.')); heading.append(title); root.append(heading);
  root.append(el('p', 'atlas-intro', 'Maak van twijfel gedeelde kennis. Leg vast welke bron je kiest en waarom. Die beoordeling reist mee met dezelfde vraag en context, zolang de bronnen ongewijzigd blijven.'));
  if (!reviews.length) {const empty = el('div', 'empty-card'); empty.append(el('strong', '', 'De lus begint met een vraag.'), el('p', '', 'Onderzoek een scenario en kies ‘Leg de twijfel voor’.')); root.append(empty);}
  reviews.forEach(review => root.append(reviewCard(review)));
}

async function updateReviewCount() {
  try {const reviews = await api('/api/reviews'); const count = reviews.filter(r => r.status === 'open').length; $('#review-count').textContent = count ? String(count).padStart(2, '0') : '03';}
  catch (_) { /* The next explicit navigation surfaces connection failures. */ }
}
async function switchTab(tab) {
  activeTab = tab; const generation = ++tabGeneration;
  document.querySelectorAll('[data-tab]').forEach(node => {const active = node.dataset.tab === tab; node.classList.toggle('active', active); node.setAttribute('aria-pressed', String(active));});
  ['investigate', 'library', 'reviews'].forEach(name => {$('#' + name + '-view').hidden = name !== tab;});
  $('#error').hidden = true;
  try {if (tab === 'library') await renderLibrary(generation); else if (tab === 'reviews') await renderReviews(generation);}
  catch (error) {if (generation === tabGeneration) showError(error);}
}
function setForm(question, context) {
  $('#question').value = question; $('#country').value = context.country;
  $('#client').value = context.client_id || ''; $('#client').disabled = context.country === 'NL'; $('#as-of').value = context.as_of;
  document.querySelectorAll('[data-scenario]').forEach(node => node.classList.toggle('selected', scenarios[node.dataset.scenario] === question));
}
function setBusy(value) {
  busy = value;
  $('#ask-button').disabled = value;
  ['#question', '#country', '#as-of'].forEach(selector => {$(selector).disabled = value;});
  $('#client').disabled = value || $('#country').value === 'NL';
  document.querySelectorAll('[data-scenario]').forEach(node => {node.disabled = value;});
  $('#loading').hidden = !value; $('#result').hidden = value;
}
$('#question-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  const payload = {question: $('#question').value.trim(), country: $('#country').value, client_id: $('#client').value || null, as_of: $('#as-of').value};
  setBusy(true); await switchTab('investigate');
  try {renderResult(await api('/api/ask', payload));}
  catch (error) {showError(error); $('#result').replaceChildren(el('div', 'empty-card', 'Er kon geen dossier worden gemaakt. Controleer je invoer en probeer opnieuw.'));}
  finally {setBusy(false);}
});
$('#country').addEventListener('change', () => {if ($('#country').value === 'NL') $('#client').value = ''; $('#client').disabled = $('#country').value === 'NL';});
$('#question').addEventListener('input', () => document.querySelectorAll('[data-scenario]').forEach(node => node.classList.remove('selected')));
$('#guide-button').addEventListener('click', () => {$('#guide').hidden = !$('#guide').hidden; $('#guide-button').setAttribute('aria-expanded', String(!$('#guide').hidden));});
document.querySelectorAll('[data-tab]').forEach(node => node.addEventListener('click', () => switchTab(node.dataset.tab)));
document.querySelectorAll('[data-scenario]').forEach(node => node.addEventListener('click', () => {
  if (busy) return; setForm(scenarios[node.dataset.scenario], {country: 'BE', client_id: null, as_of: '2026-09-30'}); $('#question-form').requestSubmit();
}));
updateReviewCount();
$('#question-form').requestSubmit();
