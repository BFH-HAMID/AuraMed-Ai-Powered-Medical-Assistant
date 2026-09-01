/* ==========================================================================
   AuraMed — web app logic
   Wizard (patient → symptoms/triage → diagnosis/medicines → report),
   bilingual UI, live safety checks and the downloadable patient report.
   All API calls are same-origin relative URLs so the app works behind any
   reverse proxy (clinic LAN, Docker, edge node or the dev preview).
   ========================================================================== */
(function () {
  'use strict';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* ─────────────────────────── i18n ─────────────────────────── */
  // Bengali is the source language: it is captured from the DOM on load, so the
  // HTML stays readable and only the English strings live here.
  const bnSource = {};
  const EN = {
    'skip': 'Skip to main content',
    'nav.home': 'Home', 'nav.workspace': 'Workspace', 'nav.report': 'Report',
    'nav.arch': 'Architecture', 'nav.start': 'Get started',
    'hero.badge': '26-node clinical AI engine · online',
    'hero.title1': 'Your healthcare', 'hero.title2': 'AI companion',
    'hero.sub': 'Symptom analysis in Bengali, emergency triage, drug-safety checks and a diet plan — all in one place. Then download the complete patient report.',
    'hero.cta1': 'Build a report', 'hero.cta2': 'Load demo data',
    'hero.stat1': 'AI nodes', 'hero.stat2': 'Languages (বাংলা / English)',
    'hero.stat3': 'passing tests', 'hero.stat4v': 'Offline', 'hero.stat4': 'edge-ready',
    'brain.status': 'AI engine active · neural network running',
    'brain.m1': 'Triage', 'brain.m2': 'Drug safety', 'brain.m3': 'Risk',
    'cap1.t': 'Emergency triage',
    'cap1.d': 'RED / YELLOW / GREEN — red flags immediately trigger 999 and first-aid guidance.',
    'cap2.t': 'Drug safety',
    'cap2.d': 'Drug-drug interactions, allergies, kidney and cardiac risk — critical findings hard-stop.',
    'cap3.t': 'Diet & advice',
    'cap3.d': 'Regional (Bengali plate) diet plans, plain-language explanations and lifestyle advice.',
    'cap4.t': 'Downloadable report',
    'cap4.d': 'Patient data, diagnosis, dosing rules, advice and diet — a print-ready A4 report.',
    'ws.title': 'Create a patient report',
    'ws.sub': 'Fill in four steps — AuraMed runs a safety check at every step.',
    'step1': 'Patient details', 'step2': 'Symptoms & triage', 'step3': 'Diagnosis & medicines', 'step4': 'Report',
    's1.title': 'Patient details',
    'f.name': 'Patient name *', 'f.age': 'Age (years)', 'f.sex': 'Sex',
    'o.unknown': 'Unknown', 'o.male': 'Male', 'o.female': 'Female', 'o.other': 'Other',
    'f.weight': 'Weight (kg)', 'f.height': 'Height (cm)', 'f.phone': 'Mobile',
    'f.address': 'Address', 'f.allergies': 'Drug allergies (comma separated)',
    'f.conditions': 'Existing conditions (comma separated)', 'f.egfr': 'Kidney eGFR (optional)',
    'f.diabetic': 'Has diabetes', 'f.smoker': 'Smokes', 'f.pregnant': 'Pregnant', 'f.bmi': 'BMI',
    's2.title': 'Symptoms & vitals',
    'f.symptoms': 'Describe the symptoms (বাংলা or English) *',
    'f.temp': 'Temperature (°C)', 'f.spo2': 'SpO₂ (%)', 'f.sbp': 'Systolic BP',
    'f.dbp': 'Diastolic BP', 'f.hr': 'Pulse (HR)', 'f.rr': 'Respiratory rate',
    'a.triage': 'Run triage', 'a.triageHint': 'Node 02 — red-flag engine',
    's3.title': 'Diagnosis & medicines', 'f.diagnosis': 'Diagnosis *',
    'f.protocol': 'Protocol (Node 13)', 's3.meds': 'Medicine list', 'a.addMed': 'Add medicine',
    'a.safety': 'Run drug-safety check', 'a.safetyHint': 'Node 05 — 28-drug formulary',
    's4.title': 'Patient report',
    's4.note': 'The report contains: patient name, age, weight, height, diagnosis, medicines with dosing rules, advice for the patient and the diet plan.',
    'a.build': 'Build the report', 'a.download': 'Download report', 'a.print': 'PDF / Print',
    'a.prev': '← Back', 'a.next': 'Next →',
    'rs.title': 'What the report contains',
    'rs1.t': 'Patient identity', 'rs1.d': 'Name, age, sex, weight, height, BMI, allergies and existing conditions.',
    'rs2.t': 'Diagnosis', 'rs2.d': 'Diagnosis, plain-language explanation and the triage result (RED/YELLOW/GREEN).',
    'rs3.t': 'Medicines & rules', 'rs3.d': 'Dose, frequency, timing (before/after food) and duration — with warnings.',
    'rs4.t': 'Advice & diet', 'rs4.d': 'Advice for the patient, recommended tests and a regional diet plan.',
    'rs.note': 'Every report carries the mandatory disclaimer and a physician signature block — AuraMed never prescribes on its own.',
    'foot.tag': 'AI-Powered Medical Assistant · v1.0.0',
  };

  const PH_EN = {
    p_name: 'e.g. Rahima Begum', p_age: '45', p_weight: '62', p_height: '158',
    p_phone: '01XXXXXXXXX', p_address: 'Village/area, upazila, district',
    p_allergies: 'e.g. penicillin, sulfa', p_conditions: 'e.g. diabetes, hypertension',
    p_egfr: '—', symptoms: 'e.g. Fever for 3 days, cough, mild chest tightness, fatigue…',
    diagnosis: 'e.g. hypertension / high blood pressure',
  };
  const PH_BN = {};

  let lang = localStorage.getItem('auramed.lang') || 'bn';

  function applyLang(next) {
    lang = next;
    document.documentElement.lang = lang;
    localStorage.setItem('auramed.lang', lang);
    $$('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (!(key in bnSource)) bnSource[key] = el.textContent.trim();
      el.textContent = lang === 'en' ? (EN[key] || bnSource[key]) : bnSource[key];
    });
    Object.keys(PH_EN).forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      if (!(id in PH_BN)) PH_BN[id] = el.placeholder;
      el.placeholder = lang === 'en' ? PH_EN[id] : PH_BN[id];
    });
    $$('.lang-switch button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === lang)));
    $$('.med-row').forEach(row => labelMedRow(row));
    if (state.report) renderReportPreview(state.report);
    if (state.triage) renderTriage(state.triage);
    if (state.safety) renderSafety(state.safety);
    updateDisclaimer();
  }

  /* ─────────────────────────── state ─────────────────────────── */
  const state = {
    step: 1,
    triage: null,
    safety: null,
    report: null,
    reportHtml: null,
    reportName: null,
  };

  const DISCLAIMER = {
    bn: 'AuraMed AI-এর আউটপুট শুধুমাত্র সিদ্ধান্ত-সহায়তার জন্য; চিকিৎসা সংক্রান্ত কোনো ব্যবস্থা নেওয়ার আগে অবশ্যই নিবন্ধিত চিকিৎসকের পর্যালোচনা প্রয়োজন।',
    en: 'AuraMed AI output is for decision-support only; requires licensed physician review before clinical action.',
  };

  function L(bn, en) { return lang === 'en' ? en : bn; }

  function updateDisclaimer() {
    const el = $('#footDisclaimer');
    if (el) el.textContent = DISCLAIMER[lang === 'en' ? 'en' : 'bn'];
  }

  /* ─────────────────────────── toasts ─────────────────────────── */
  function toast(message, kind) {
    const wrap = $('#toasts');
    const el = document.createElement('div');
    el.className = 'toast toast--' + (kind || 'ok');
    el.textContent = message;
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(18px)'; }, 4200);
    setTimeout(() => el.remove(), 4700);
  }

  /* ─────────────────────────── API ─────────────────────────── */
  async function api(path, body) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    let payload = null;
    try { payload = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      const detail = payload && (payload.data && payload.data.detail || payload.detail || payload.data && payload.data.error);
      throw new Error(typeof detail === 'string' ? detail : (L('সার্ভার ত্রুটি', 'Server error') + ' (' + res.status + ')'));
    }
    return { payload, res };
  }

  /* ─────────────────────────── brain ─────────────────────────── */
  let brain = null;
  function brainBusy(on) {
    if (!brain) return;
    brain.setActivity(on ? 1 : 0.55);
    if (on) brain.pulse(10);
  }
  function setMetric(id, text, tone) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = tone || '';
  }

  /* ─────────────────────── patient + BMI ─────────────────────── */
  function num(id) {
    const v = $('#' + id).value.trim();
    return v === '' ? null : Number(v);
  }

  function csvList(id) {
    return $('#' + id).value.split(',').map(s => s.trim()).filter(Boolean);
  }

  function bmiCategory(bmi) {
    if (bmi < 18.5) return { key: 'underweight', bn: 'কম ওজন', en: 'Underweight' };
    if (bmi < 23) return { key: 'normal', bn: 'স্বাভাবিক', en: 'Normal' };
    if (bmi < 27.5) return { key: 'overweight', bn: 'বেশি ওজন', en: 'Overweight' };
    return { key: 'obese', bn: 'স্থূলকায়', en: 'Obese' };
  }

  function updateBmi() {
    const w = num('p_weight'), h = num('p_height');
    const card = $('#bmiCard');
    if (!w || !h) { card.hidden = true; return; }
    const bmi = Math.round((w / Math.pow(h / 100, 2)) * 10) / 10;
    const cat = bmiCategory(bmi);
    card.hidden = false;
    $('#bmiValue').textContent = bmi.toFixed(1);
    $('#bmiLabel').textContent = L(cat.bn, cat.en);
  }

  function patientPayload() {
    return {
      name: $('#p_name').value.trim(),
      age_years: num('p_age'),
      sex: $('#p_sex').value,
      weight_kg: num('p_weight'),
      height_cm: num('p_height'),
      phone: $('#p_phone').value.trim(),
      address: $('#p_address').value.trim(),
      allergies: csvList('p_allergies'),
      conditions: csvList('p_conditions'),
      current_medications: medicationRows().map(m => m.name).filter(Boolean),
      renal_egfr: num('p_egfr'),
      diabetic: $('#p_diabetic').checked,
      smoker: $('#p_smoker').checked,
      pregnant: $('#p_pregnant').checked,
    };
  }

  function vitalsPayload() {
    const v = {};
    [['v_temp', 'temp_c'], ['v_spo2', 'spo2'], ['v_sbp', 'sbp'], ['v_dbp', 'dbp'], ['v_hr', 'hr'], ['v_rr', 'rr']]
      .forEach(([id, key]) => { const n = num(id); if (n !== null) v[key] = n; });
    return v;
  }

  /* ─────────────────────────── medicines ─────────────────────── */
  const MED_FIELDS = [
    ['name', 'ওষুধের নাম', 'Medicine', 'metformin'],
    ['dose', 'মাত্রা', 'Dose', '500 mg'],
    ['frequency', 'কতবার (1+0+1)', 'Frequency (1+0+1)', '1+0+1'],
    ['duration', 'কতদিন', 'Duration', '30 days'],
  ];

  function labelMedRow(row) {
    $$('.fld > span', row).forEach((span, i) => {
      const f = MED_FIELDS[i];
      if (f) span.textContent = L(f[1], f[2]);
    });
  }

  function addMedRow(values) {
    const row = document.createElement('div');
    row.className = 'med-row';
    MED_FIELDS.forEach(f => {
      const label = document.createElement('label');
      label.className = 'fld';
      const span = document.createElement('span');
      span.textContent = L(f[1], f[2]);
      const input = document.createElement('input');
      input.type = 'text';
      input.dataset.med = f[0];
      input.placeholder = f[3];
      if (values && values[f[0]] != null) input.value = values[f[0]];
      label.appendChild(span); label.appendChild(input);
      row.appendChild(label);
    });
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'med-del';
    del.title = L('মুছুন', 'Remove');
    del.textContent = '×';
    del.addEventListener('click', () => row.remove());
    row.appendChild(del);
    $('#medList').appendChild(row);
  }

  function medicationRows() {
    return $$('.med-row').map(row => {
      const get = k => { const el = row.querySelector('[data-med="' + k + '"]'); return el ? el.value.trim() : ''; };
      return { name: get('name'), dose: get('dose'), frequency: get('frequency'), duration: get('duration') };
    }).filter(m => m.name);
  }

  /* ─────────────────────────── wizard ─────────────────────────── */
  function goStep(n) {
    state.step = Math.max(1, Math.min(4, n));
    $$('.panel').forEach(p => p.classList.toggle('is-active', Number(p.dataset.panel) === state.step));
    $$('.step').forEach(s => {
      const i = Number(s.dataset.step);
      s.classList.toggle('is-active', i === state.step);
      s.classList.toggle('is-done', i < state.step);
    });
    $('#stepsFill').style.width = (state.step * 25) + '%';
    $('#prevBtn').disabled = state.step === 1;
    $('#nextBtn').disabled = state.step === 4;
    $('#panelInfo').textContent = L('ধাপ', 'Step') + ' ' + state.step + ' / 4';
    $('#workspace').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function validateStep(n) {
    if (n === 1 && !$('#p_name').value.trim()) {
      toast(L('রোগীর নাম লিখুন।', 'Please enter the patient name.'), 'warn');
      $('#p_name').focus();
      return false;
    }
    if (n === 2 && !$('#symptoms').value.trim()) {
      toast(L('উপসর্গ লিখুন — না লিখলে ট্রয়েজ চালানো যাবে না।', 'Enter the symptoms — triage needs them.'), 'warn');
      $('#symptoms').focus();
      return false;
    }
    if (n === 3 && !$('#diagnosis').value.trim()) {
      toast(L('রোগের নাম লিখুন।', 'Please enter the diagnosis.'), 'warn');
      $('#diagnosis').focus();
      return false;
    }
    return true;
  }

  /* ─────────────────────────── rendering ─────────────────────── */
  const RISK_LABEL = {
    red: { bn: 'রেড — এখনই জরুরি সেবা', en: 'RED — emergency care now' },
    yellow: { bn: 'ইয়েলো — আজই চিকিৎসা নিন', en: 'YELLOW — care today' },
    green: { bn: 'গ্রিন — পর্যবেক্ষণসহ ঘরোয়া যত্ন', en: 'GREEN — home care with monitoring' },
  };

  function riskBadge(level) {
    const label = RISK_LABEL[level] || RISK_LABEL.green;
    return '<span class="badge badge--' + level + '">' + (level === 'red' ? '🔴' : level === 'yellow' ? '🟡' : '🟢') +
      ' ' + L(label.bn, label.en) + '</span>';
  }

  function esc(v) {
    return String(v == null ? '—' : v).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function renderTriage(data) {
    state.triage = data;
    const level = data.risk_level || 'green';
    const box = $('#triageResult');
    box.hidden = false;
    const flags = (data.matched_red_flags || []).map(f => f.title_bn || f.title_en || f.id).filter(Boolean);
    const advice = lang === 'en' ? data.immediate_advice_en : data.immediate_advice_bn;
    box.innerHTML =
      '<div class="card card--' + level + '">' +
      '<h4>' + riskBadge(level) + '</h4>' +
      (advice ? '<p style="margin-top:10px">' + esc(advice) + '</p>' : '') +
      (flags.length ? '<div class="card__meta">' + flags.map(f => '<span class="chipx">⚠ ' + esc(f) + '</span>').join('') + '</div>' : '') +
      ((data.possible_conditions || []).length ? '<div class="card__meta">' + data.possible_conditions.map(c => '<span class="chipx">' + esc(c) + '</span>').join('') + '</div>' : '') +
      '</div>';
    setMetric('metricTriage', level.toUpperCase(), level);
  }

  function renderSafety(data) {
    state.safety = data;
    const box = $('#safetyResult');
    box.hidden = false;
    const level = data.safe_to_proceed ? (data.overall_severity === 'moderate' ? 'yellow' : 'green') : 'red';
    const findings = data.findings || [];
    box.innerHTML =
      '<div class="card card--' + level + '">' +
      '<h4>' + (data.safe_to_proceed ? '✅ ' : '⛔ ') + esc(lang === 'en' ? data.summary_en : data.summary_bn) + '</h4>' +
      (findings.length
        ? '<ul>' + findings.map(f =>
          '<li><b>[' + esc(f.severity) + ']</b> ' + esc(lang === 'en' ? f.title_en : f.title_bn) +
          (f.recommendation_en || f.recommendation_bn
            ? ' — ' + esc(lang === 'en' ? f.recommendation_en : f.recommendation_bn) : '') + '</li>').join('') + '</ul>'
        : '<p style="margin-top:10px">' + esc(L('কোনো সমস্যা পাওয়া যায়নি।', 'No findings.')) + '</p>') +
      '</div>';
    setMetric('metricDrug', data.safe_to_proceed ? L('নিরাপদ', 'Safe') : L('ঝুঁকি', 'Risk'), data.safe_to_proceed ? 'ok' : 'red');
  }

  function rpSection(title, icon, inner) {
    return '<div class="rp-section"><h4>' + icon + ' ' + esc(title) + '</h4>' + inner + '</div>';
  }

  function rpGrid(pairs) {
    return '<div class="rp-grid">' + pairs.filter(p => p[1] != null && p[1] !== '').map(p =>
      '<div class="rp-item"><span>' + esc(p[0]) + '</span><b>' + esc(p[1]) + '</b></div>').join('') + '</div>';
  }

  function renderReportPreview(r) {
    state.report = r;
    const p = r.patient || {};
    const box = $('#reportPreview');
    box.hidden = false;

    const meds = (r.medications || []).map(m =>
      '<tr><td><b>' + esc(m.name) + '</b>' + (m.warnings && m.warnings.length ? '<br/><span style="color:var(--red)">⚠ ' + esc(m.warnings.join(' · ')) + '</span>' : '') + '</td>' +
      '<td>' + esc(m.dose) + '</td><td>' + esc(m.frequency || m.frequency_raw) + '</td>' +
      '<td>' + esc(m.timing) + '</td><td>' + esc(m.duration) + '</td></tr>').join('');

    const diag = r.diagnosis || {};
    const diet = r.diet || {};
    const labs = (r.lab_tests && r.lab_tests.recommended_tests) || [];
    const scores = r.risk_scores || {};

    box.innerHTML =
      rpSection(L('রোগীর তথ্য', 'Patient information'), '🧍', rpGrid([
        [L('নাম', 'Name'), p.name],
        [L('বয়স', 'Age'), p.age_years != null ? p.age_years + ' ' + L('বছর', 'yrs') : ''],
        [L('লিঙ্গ', 'Sex'), lang === 'en' ? p.sex : p.sex_bn],
        [L('ওজন', 'Weight'), p.weight_kg ? p.weight_kg + ' kg' : ''],
        [L('উচ্চতা', 'Height'), p.height_cm ? p.height_cm + ' cm' : ''],
        ['BMI', p.bmi ? p.bmi + ' — ' + p.bmi_category : ''],
        [L('মোবাইল', 'Phone'), p.phone],
        [L('অ্যালার্জি', 'Allergies'), (p.allergies || []).join(', ')],
        [L('পুরনো রোগ', 'Conditions'), (p.conditions || []).join(', ')],
      ])) +

      rpSection(L('রোগ নির্ণয় ও ট্রয়েজ', 'Diagnosis & triage'), '🩺',
        '<div class="card__meta" style="margin:0 0 10px">' + riskBadge(r.risk_level) +
        '<span class="chipx">' + esc(r.report_id) + '</span></div>' +
        rpGrid([[L('রোগ', 'Diagnosis'), diag.text], [L('সহজ ভাষায়', 'In simple words'), diag.plain_explanation]]) +
        ((r.assessment && r.assessment.triage)
          ? '<p style="margin-top:12px">' + esc(lang === 'en' ? r.assessment.triage.immediate_advice_en : r.assessment.triage.immediate_advice_bn) + '</p>' : '')) +

      rpSection(L('ঔষধ ও সেবনবিধি', 'Medicines & dosing'), '💊', meds
        ? '<div class="table-wrap"><table class="rp-table"><tr><th>' + L('ঔষধ', 'Medicine') + '</th><th>' + L('মাত্রা', 'Dose') +
          '</th><th>' + L('কতবার', 'Frequency') + '</th><th>' + L('কখন', 'When') + '</th><th>' + L('কতদিন', 'Duration') +
          '</th></tr>' + meds + '</table></div>'
        : '<p>' + esc(L('কোনো ওষুধ যোগ করা হয়নি।', 'No medicines added.')) + '</p>') +

      rpSection(L('রোগীর জন্য পরামর্শ', 'Advice for the patient'), '📌',
        '<ul>' + (r.suggestions || []).map(s => '<li>' + esc(s) + '</li>').join('') + '</ul>') +

      rpSection(L('খাদ্য ও জীবনযাপন', 'Diet & lifestyle'), '🥗',
        '<p style="margin-bottom:8px"><b>' + esc(diet.title) + '</b></p>' +
        '<ul>' + (diet.diet || []).map(d => '<li>' + esc(d) + '</li>').join('') + '</ul>' +
        ((diet.activity || []).length ? '<p style="margin:10px 0 4px;color:var(--muted)">' + esc(L('শারীরিক কার্যকলাপ', 'Activity')) + '</p><ul>' +
          diet.activity.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>' : '')) +

      (labs.length ? rpSection(L('প্রয়োজনীয় পরীক্ষা', 'Recommended tests'), '🧪',
        '<ul>' + labs.map(t => '<li><b>' + esc(t.test) + '</b> — ' + esc(t.rationale) + '</li>').join('') + '</ul>') : '') +

      (Object.keys(scores).length ? rpSection(L('ঝুঁকি স্কোর', 'Risk score'), '📈', rpGrid(
        Object.keys(scores).filter(k => k !== 'status').map(k => [k.replace(/_/g, ' '), typeof scores[k] === 'object' ? JSON.stringify(scores[k]) : scores[k]])
      )) : '');

    setMetric('metricRisk', (r.risk_level || '').toUpperCase(), r.risk_level);
  }

  /* ─────────────────────── report build / download ─────────────── */
  function reportRequest() {
    return {
      patient: patientPayload(),
      symptoms_text: $('#symptoms').value.trim(),
      vitals: vitalsPayload(),
      diagnosis: $('#diagnosis').value.trim(),
      diagnosis_key: $('#diagnosisKey').value,
      medications: medicationRows(),
      language: lang === 'en' ? 'en' : 'bn',
    };
  }

  async function buildReport() {
    const btn = $('#buildReport');
    if (!validateStep(1)) { goStep(1); return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span>';
    brainBusy(true);
    try {
      const { payload } = await api('/api/v1/report/patient', reportRequest());
      renderReportPreview(payload.data);
      $('#downloadReport').disabled = false;
      $('#printReport').disabled = false;
      toast(L('রিপোর্ট তৈরি হয়েছে — এখন ডাউনলোড করুন।', 'Report built — you can download it now.'), 'ok');
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = L('রিপোর্ট তৈরি করুন', 'Build the report');
      brainBusy(false);
    }
  }

  async function fetchReportFile() {
    const res = await fetch('/api/v1/report/patient/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reportRequest()),
    });
    if (!res.ok) throw new Error(L('ডাউনলোড ব্যর্থ', 'Download failed') + ' (' + res.status + ')');
    const disp = res.headers.get('Content-Disposition') || '';
    let name = 'AuraMed-Report.html';
    const match = /filename\*=UTF-8''([^;]+)/i.exec(disp) || /filename="?([^";]+)"?/i.exec(disp);
    if (match) { try { name = decodeURIComponent(match[1]); } catch (e) { name = match[1]; } }
    const blob = await res.blob();
    return { blob, name, reportId: res.headers.get('X-AuraMed-Report-Id') };
  }

  async function downloadReport() {
    const btn = $('#downloadReport');
    btn.disabled = true; btn.innerHTML = '<span class="loading"></span>';
    brainBusy(true);
    try {
      const { blob, name } = await fetchReportFile();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast(L('রিপোর্ট ডাউনলোড হয়েছে: ', 'Report downloaded: ') + name, 'ok');
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false; btn.textContent = L('রিপোর্ট ডাউনলোড', 'Download report'); brainBusy(false);
    }
  }

  async function printReport() {
    const btn = $('#printReport');
    btn.disabled = true; btn.innerHTML = '<span class="loading"></span>';
    try {
      const { blob, name } = await fetchReportFile();
      const url = URL.createObjectURL(blob);
      const win = window.open(url, '_blank');
      if (!win) {
        // popup blocked — fall back to a normal download
        const a = document.createElement('a');
        a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
        toast(L('পপ-আপ বন্ধ ছিল, তাই ফাইলটি ডাউনলোড হয়েছে।', 'Popup blocked — the file was downloaded instead.'), 'warn');
      } else {
        toast(L('নতুন ট্যাবে রিপোর্ট খুলেছে — “প্রিন্ট / PDF” চাপুন।', 'Report opened in a new tab — press “Print / Save as PDF”.'), 'ok');
      }
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false; btn.textContent = L('PDF / প্রিন্ট', 'PDF / Print');
    }
  }

  /* ─────────────────────── triage / safety calls ─────────────── */
  async function runTriage() {
    const symptoms = $('#symptoms').value.trim();
    if (!symptoms) { toast(L('আগে উপসর্গ লিখুন।', 'Enter the symptoms first.'), 'warn'); return; }
    const btn = $('#runTriage');
    btn.disabled = true; btn.innerHTML = '<span class="loading"></span>';
    brainBusy(true);
    try {
      const { payload } = await api('/api/v1/02/triage', {
        symptoms_text: symptoms, vitals: vitalsPayload(), language: lang === 'en' ? 'en' : 'bn',
      });
      renderTriage(payload.data);
      if (payload.risk_level === 'red') {
        toast(L('🔴 রেড ফ্ল্যাগ! এখনই ৯৯৯-এ কল করুন বা জরুরি বিভাগে যান।', '🔴 RED FLAG! Call 999 now or go to the emergency department.'), 'err');
      } else {
        toast(L('ট্রয়েজ সম্পন্ন: ', 'Triage complete: ') + payload.risk_level.toUpperCase(), 'ok');
      }
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false; btn.textContent = L('ট্রয়েজ চালান', 'Run triage'); brainBusy(false);
    }
  }

  async function runSafety() {
    const meds = medicationRows();
    if (!meds.length) { toast(L('অন্তত একটি ওষুধের নাম লিখুন।', 'Add at least one medicine name.'), 'warn'); return; }
    const btn = $('#runSafety');
    btn.disabled = true; btn.innerHTML = '<span class="loading"></span>';
    brainBusy(true);
    try {
      const p = patientPayload();
      const { payload } = await api('/api/v1/05/drug-safety', {
        medications: meds.map(m => ({ name: m.name, dose: m.dose || null })),
        patient: {
          patient_id: null, age_years: p.age_years, sex: p.sex, weight_kg: p.weight_kg,
          allergies: p.allergies, conditions: p.conditions, current_medications: [],
          renal_egfr: p.renal_egfr, pregnant: p.pregnant, language: lang === 'en' ? 'en' : 'bn',
        },
        language: lang === 'en' ? 'en' : 'bn',
      });
      renderSafety(payload.data);
      if (!payload.data.safe_to_proceed) {
        toast(L('⛔ ঔষধে গুরুতর সমস্যা পাওয়া গেছে — চিকিৎসকের পরামর্শ নিন।', '⛔ Critical drug-safety finding — consult the physician.'), 'err');
      } else {
        toast(L('ঔষধ নিরাপত্তা যাচাই সম্পন্ন।', 'Drug-safety check complete.'), 'ok');
      }
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false; btn.textContent = L('ঔষধ নিরাপত্তা যাচাই', 'Run drug-safety check'); brainBusy(false);
    }
  }

  /* ─────────────────────────── demo data ─────────────────────── */
  function loadDemo() {
    $('#p_name').value = 'রহিমা বেগম';
    $('#p_age').value = 54;
    $('#p_sex').value = 'female';
    $('#p_weight').value = 68;
    $('#p_height').value = 155;
    $('#p_phone').value = '01712345678';
    $('#p_address').value = 'ওয়ার্ড ০৩, গাজীপুর সদর, গাজীপুর';
    $('#p_allergies').value = 'penicillin';
    $('#p_conditions').value = 'hypertension, diabetes';
    $('#p_egfr').value = 58;
    $('#p_diabetic').checked = true;
    $('#p_smoker').checked = false;
    $('#p_pregnant').checked = false;
    $('#symptoms').value = 'তিন সপ্তাহ ধরে মাথা ঘোরা, ঘাড়ে ব্যথা, হালকা বুকে চাপ, পিপাসা বেশি পাচ্ছে';
    $('#v_sbp').value = 158; $('#v_dbp').value = 96; $('#v_hr').value = 92; $('#v_spo2').value = 97; $('#v_temp').value = 37.1;
    $('#diagnosis').value = 'hypertension';
    $('#diagnosisKey').value = 'hypertension';
    $('#medList').innerHTML = '';
    addMedRow({ name: 'metformin', dose: '500 mg', frequency: '1+0+1', duration: '30 days' });
    addMedRow({ name: 'ibuprofen', dose: '400 mg', frequency: '0+1+0', duration: '5 days' });
    addMedRow({ name: 'warfarin', dose: '5 mg', frequency: '0+0+1', duration: 'চলমান' });
    updateBmi();
    goStep(2);
    toast(L('ডেমো ডেটা বসানো হয়েছে — “ট্রয়েজ চালান” চাপুন।', 'Demo data loaded — press “Run triage”.'), 'ok');
  }

  /* ─────────────────────────── wiring ─────────────────────────── */
  function init() {
    // capture Bengali source strings before any switch
    $$('[data-i18n]').forEach(el => { bnSource[el.getAttribute('data-i18n')] = el.textContent.trim(); });
    Object.keys(PH_EN).forEach(id => { const el = document.getElementById(id); if (el) PH_BN[id] = el.placeholder; });

    brain = window.AuraMedBrain ? window.AuraMedBrain.mount($('#brainCanvas')) : null;
    if (brain) brain.pulse(14);

    $$('.lang-switch button').forEach(b => b.addEventListener('click', () => applyLang(b.dataset.lang)));
    applyLang(localStorage.getItem('auramed.lang') || 'bn');

    ['p_weight', 'p_height'].forEach(id => $('#' + id).addEventListener('input', updateBmi));

    $('#addMed').addEventListener('click', () => addMedRow());
    addMedRow({ name: '', dose: '', frequency: '1+0+1', duration: '' });

    $('#runTriage').addEventListener('click', runTriage);
    $('#runSafety').addEventListener('click', runSafety);
    $('#buildReport').addEventListener('click', buildReport);
    $('#downloadReport').addEventListener('click', downloadReport);
    $('#printReport').addEventListener('click', printReport);
    $('#demoBtn').addEventListener('click', loadDemo);

    $('#nextBtn').addEventListener('click', () => { if (validateStep(state.step)) goStep(state.step + 1); });
    $('#prevBtn').addEventListener('click', () => goStep(state.step - 1));
    $$('.step').forEach(s => s.addEventListener('click', () => {
      const target = Number(s.dataset.step);
      if (target > state.step && !validateStep(state.step)) return;
      goStep(target);
    }));

    goStep(1);
    updateBmi();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
