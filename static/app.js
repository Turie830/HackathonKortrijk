const $ = (selector) => document.querySelector(selector);
let submittedQuestion = null;
let busy = false;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, payload) {
  const response = await fetch(path, payload ? {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  } : {});
  if (!response.ok) throw new Error(response.status === 422
    ? 'Controleer je vraag, land en datum.' : 'De aanvraag is mislukt. Probeer opnieuw.');
  return response.json();
}

function showError(error) {
  $('#error').textContent = error.message || 'Er is iets misgegaan.';
  $('#error').hidden = false;
}

function sourceCard(source, library = false) {
  const card = element('article', 'source');
  const top = element('div', 'source-top');
  top.append(element('h4', '', source.title), element('span', 'badge ' + (source.approved ? 'green' : 'amber'), source.kind));
  card.append(top);
  card.append(element('p', 'source-meta', `${source.owner || 'Eigenaar onbekend'} · ${source.country} · ${source.client_id || 'Algemeen'} · Bijgewerkt ${source.updated_at}`));
  const signals = element('div', 'signals');
  if (library) {
    signals.append(element('span', 'signal' + (source.approved ? '' : ' warning'), source.approved ? 'Goedgekeurd' : 'Geen goedkeuring'));
  } else {
    if (source.usable) signals.append(element('span', 'signal', 'Broncontroles in orde'));
    source.warnings.forEach(warning => signals.append(element('span', 'signal warning', warning)));
  }
  card.append(signals);
  card.append(element('p', 'source-meta', `Geldig vanaf ${source.valid_from}${source.valid_until ? ' tot ' + source.valid_until : ' · Geen einddatum vastgelegd'}`));
  const details = element('details');
  details.append(element('summary', '', 'Bekijk originele bronpassage'));
  const text = library ? source.passages.map(p => p.text).join('\n\n') : source.text;
  details.append(element('p', 'source-text', text));
  details.append(element('p', 'citation', library ? source.id : source.citation));
  card.append(details);
  return card;
}

function renderResult(result) {
  const root = $('#result');
  root.replaceChildren();
  const settings = {
    supported: ['green', 'Broncontroles in orde', 'Antwoord met bronverwijzingen'],
    conflict: ['red', 'Tegenstrijdige bronnen', 'Menselijke beoordeling nodig'],
    review: ['amber', 'Bevestiging nodig', 'Bronnen met aandachtspunten'],
    missing: ['amber', 'Kennis ontbreekt', 'Geen passende bron gevonden'],
  };
  const [color, label, title] = settings[result.status];
  const heading = element('div', 'result-heading');
  heading.append(element('span', 'eyebrow', 'RESULTAAT'), element('span', `badge ${color}`, label));
  root.append(heading, element('div', 'context-line', `${result.context.country === 'BE' ? 'België' : 'Nederland'} · ${result.context.client_id || 'Algemene procedures'} · Situatie op ${result.context.as_of}`));
  const answer = element('div', 'answer-card');
  answer.append(element('h2', '', title), element('div', 'answer-text', result.answer));
  answer.append(element('p', 'answer-note', result.mode === 'model' ? 'Geformuleerd met AI · Beoordeel de bronpassages.' : 'Antwoord opgebouwd uit originele bronpassages.'));
  if (result.model_notice) answer.append(element('p', 'answer-note', result.model_notice));
  root.append(answer);
  result.conflicts.forEach(conflict => {
    const box = element('div', 'conflict-card');
    box.append(element('h3', '', '≠ Deze bronnen verschillen: ' + conflict.topic.replaceAll('_', ' ')));
    conflict.evidence.forEach(evidence => {
      const item = element('div', 'conflict-evidence');
      item.append(element('strong', '', evidence.value), element('p', '', evidence.text), element('span', 'citation', evidence.citation));
      box.append(item);
    });
    root.append(box);
  });
  const sourceHeading = element('div', 'section-heading');
  sourceHeading.append(element('h3', '', 'Onderbouwing'), element('span', '', `${result.sources.length} bronpassage${result.sources.length === 1 ? '' : 's'}`));
  root.append(sourceHeading);
  result.sources.forEach(source => root.append(sourceCard(source)));
  const review = element('div', 'review-box');
  review.append(element('h3', '', result.needs_review ? 'Vraag de bronhouder om bevestiging' : 'Nog twijfel over de toepassing?'));
  review.append(element('p', '', `Voorgestelde bronhouder: ${result.expert}. Het verzoek wordt lokaal opgeslagen; er wordt geen bericht verstuurd.`));
  const button = element('button', 'secondary', 'Expertbeoordeling aanvragen →');
  button.type = 'button';
  const payload = {...submittedQuestion};
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const request = await api('/api/reviews', payload);
      review.append(element('div', 'review-message', `Verzoek #${request.id} opgeslagen voor ${request.expert}.`));
      button.textContent = 'Verzoek opgeslagen ✓';
    } catch (error) {showError(error); button.disabled = false;}
  });
  review.append(button);
  root.append(review, element('p', 'answer-note', result.notice));
  root.hidden = false;
}

async function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(button => {
    const active = button.dataset.tab === tab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  ['answer', 'library', 'reviews'].forEach(name => {$('#' + name + '-view').hidden = name !== tab;});
  $('#error').hidden = true;
  try {
    if (tab === 'library') {
      const sources = await api('/api/sources');
      const root = $('#library-view'); root.replaceChildren();
      root.append(element('h2', '', 'Een kleine kennisbank, echte frictie.'), element('p', 'library-intro', 'Alle documenten zijn fictief. Claims voor conflictcontrole zijn handmatig gestructureerd voor deze demo.'));
      sources.forEach(source => root.append(sourceCard(source, true)));
    } else if (tab === 'reviews') {
      const requests = await api('/api/reviews');
      const root = $('#reviews-view'); root.replaceChildren();
      root.append(element('h2', '', 'Expertbeoordelingen'), element('p', 'library-intro', 'Lokale verzoeken om een bron of toepassing te laten beoordelen. Er wordt geen expert automatisch gecontacteerd.'));
      if (!requests.length) root.append(element('p', 'muted', 'Nog geen verzoeken. Je kunt er een aanmaken bij een antwoord.'));
      requests.forEach(request => {
        const item = element('article', 'review-entry');
        item.append(element('span', 'badge amber', `#${request.id} · Open`), element('h3', '', request.question), element('p', '', `${request.expert} · ${request.country} · ${request.client_id || 'Algemeen'} · Situatie op ${request.as_of}`));
        root.append(item);
      });
    }
  } catch (error) {showError(error);}
}

$('#question-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  const button = $('#ask-button'); button.disabled = true;
  document.querySelectorAll('[data-example]').forEach(b => {b.disabled = true;});
  submittedQuestion = {
    question: $('#question').value.trim(), country: $('#country').value,
    client_id: $('#client').value || null, as_of: $('#as-of').value,
  };
  await switchTab('answer');
  $('#empty').hidden = true; $('#result').hidden = true; $('#loading').hidden = false;
  try {renderResult(await api('/api/ask', submittedQuestion));}
  catch (error) {showError(error); $('#empty').hidden = false;}
  finally {
    $('#loading').hidden = true; button.disabled = false; busy = false;
    document.querySelectorAll('[data-example]').forEach(b => {b.disabled = false;});
  }
});

const scenarios = {
  handover: 'Hoe draag ik een klantdossier over aan een nieuwe consultant?',
  correction: 'Wie moet een looncorrectie controleren en goedkeuren?',
  deadline: 'Wat is de deadline voor de maandelijkse verwerking?',
};
document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => {
  if (busy) return;
  $('#question').value = scenarios[button.dataset.example];
  $('#country').value = 'BE'; $('#client').value = ''; $('#as-of').value = '2026-09-30';
  $('#question-form').requestSubmit();
}));
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.tab)));
