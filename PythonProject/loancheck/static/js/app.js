const state = { ...window.LOANCHECK.input };
let result = { ...window.LOANCHECK.result };
let currentStep = 1;

const form = document.querySelector("#eligibilityForm");
const resultsPanel = document.querySelector("#resultsPanel");
const configs = window.LOANCHECK.configs;
const faqs = window.LOANCHECK.faqs;
let bankRates = null;
let bankRatesLoanType = "";
let selectedBorrowerType = "salaried";
let selectedBankName = "";

const money = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0
});

function formatINR(value) {
  return money.format(Math.max(0, Math.round(value || 0)));
}

function compactINR(value) {
  const amount = Math.max(0, Number(value || 0));
  if (amount >= 10000000) return `₹${(amount / 10000000).toFixed(2)} Cr`;
  if (amount >= 100000) return `₹${(amount / 100000).toFixed(2)} L`;
  return formatINR(amount);
}

function readForm() {
  const formData = new FormData(form);
  const next = Object.fromEntries(formData.entries());
  for (const key of ["monthly_income", "other_income", "existing_emis", "co_applicant_income", "property_value"]) {
    next[key] = Number(next[key] || 0);
  }
  for (const key of ["dependants", "cibil", "co_applicant_cibil", "preferred_tenure_years"]) {
    next[key] = Number(next[key] || 0);
  }
  next.has_co_applicant = formData.has("has_co_applicant");
  Object.assign(state, next);
}

async function calculate(extra = {}) {
  readForm();
  const previousLoanType = state.loan_type;
  const payload = { ...state, ...extra };
  const response = await fetch("/api/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  Object.assign(state, data.input);
  result = data.result;
  if (state.loan_type !== previousLoanType) {
    selectedBankName = "";
    bankRates = null;
    bankRatesLoanType = "";
    loadBankRates();
  }
  renderAll();
  return data;
}

function setInitialValues() {
  for (const [key, value] of Object.entries(state)) {
    const field = form.elements[key];
    if (!field) continue;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else field.value = value;
  }
}

function updateStep() {
  document.querySelectorAll(".form-step").forEach((step) => {
    step.classList.toggle("hidden", Number(step.dataset.step) !== currentStep);
  });
  document.querySelector("#stepText").textContent = `Step ${currentStep} of 3`;
  document.querySelector("#stepPercent").textContent = `${Math.round((currentStep / 3) * 100)}%`;
  document.querySelector("#progressBar").style.width = `${(currentStep / 3) * 100}%`;
  document.querySelector("#backBtn").disabled = currentStep === 1;
  document.querySelector("#nextBtn").textContent = currentStep < 3 ? "Continue" : "Check eligibility";
}

function renderLiveLabels() {
  document.querySelectorAll("[data-display]").forEach((element) => {
    const key = element.dataset.display;
    const value = state[key];
    element.textContent = key.includes("income") || key.includes("emis") ? formatINR(value) : value;
  });
  const cibil = Number(state.cibil || 0);
  const cibilDisplay = document.querySelector("#cibilDisplay");
  cibilDisplay.textContent = cibil;
  cibilDisplay.className = cibil < 650 ? "float-right text-red-600" : cibil < 750 ? "float-right text-amber-600" : "float-right text-emerald-600";

  const coFields = document.querySelector("#coApplicantFields");
  coFields.classList.toggle("hidden", !state.has_co_applicant);

  const config = configs[state.loan_type];
  document.querySelectorAll("[data-loan-card]").forEach((card) => {
    card.classList.toggle("active", card.dataset.loanCard === state.loan_type);
  });
  const propertyWrap = document.querySelector("#propertyValueWrap");
  propertyWrap.classList.toggle("hidden", !config.secured);
  document.querySelector("#ltvHelp").textContent = config.ltv ? `LTV cap ${Math.round(config.ltv * 100)}%` : "";
  form.elements.preferred_tenure_years.max = config.max_tenure_years;
}

function toneClass(tone) {
  return {
    excellent: "bg-emerald-50 text-emerald-700 border-emerald-200",
    good: "bg-blue-50 text-brand-blue border-blue-200",
    fair: "bg-amber-50 text-amber-700 border-amber-200",
    low: "bg-red-50 text-red-700 border-red-200"
  }[tone] || "bg-slate-50 text-slate-700 border-slate-200";
}

function renderResults() {
  const principalShare = result.total_payable > 0 ? Math.round((result.max_loan / result.total_payable) * 100) : 0;
  const warnings = result.warnings.length
    ? `<div class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">${result.warnings.map((warning) => `<p>${warning}</p>`).join("")}</div>`
    : "";
  const amortRows = result.amortisation
    .map((row) => `<tr class="border-t border-brand-line"><td class="px-3 py-2 font-semibold">${row.year}</td><td class="px-3 py-2">${formatINR(row.opening_balance)}</td><td class="px-3 py-2">${formatINR(row.principal)}</td><td class="px-3 py-2">${formatINR(row.interest)}</td><td class="px-3 py-2">${formatINR(row.closing_balance)}</td></tr>`)
    .join("");

  resultsPanel.innerHTML = `
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-slate-500">Maximum eligible amount</p>
        <p class="mt-1 font-heading text-4xl font-extrabold text-brand-blue">${compactINR(result.max_loan)}</p>
      </div>
      <span class="rounded-full border px-3 py-1 text-xs font-bold ${toneClass(result.verdict_tone)}">${result.verdict}</span>
    </div>
    <div class="mt-5 grid grid-cols-2 gap-3">
      ${metric("Monthly EMI", formatINR(result.monthly_emi))}
      ${rateMetric()}
      ${metric("Total interest", formatINR(result.total_interest))}
      ${metric("Tenure used", `${result.selected_tenure_years} yrs`)}
    </div>
    <div class="mt-5">
      <div class="flex justify-between text-sm font-semibold"><span>Eligibility strength</span><span>${result.score}%</span></div>
      <div class="mt-2 h-3 overflow-hidden rounded-full bg-slate-100">
        <div class="h-full rounded-full bg-gradient-to-r from-red-500 via-amber-400 to-emerald-500 transition-all" style="width: ${result.score}%"></div>
      </div>
    </div>
    <div class="my-5 flex items-center justify-center gap-5">
      <div class="doughnut" style="--principal: ${principalShare}%"></div>
      <div class="text-sm text-slate-600"><p><strong class="text-brand-blue">Principal</strong> ${formatINR(result.max_loan)}</p><p><strong class="text-[#70A9D6]">Interest</strong> ${formatINR(result.total_interest)}</p></div>
    </div>
    ${warnings}
    <section class="mt-5">
      <h3 class="font-heading text-base font-bold">Personalised tips</h3>
      <ul class="mt-2 space-y-2 text-sm text-slate-600">${result.tips.map((tip) => `<li>${tip}</li>`).join("")}</ul>
    </section>
    <div class="no-print mt-5 grid grid-cols-2 gap-2">
      <button type="button" class="col-span-2 rounded-md bg-brand-blue px-3 py-2 text-sm font-semibold text-white" id="expertBtn">Talk to a Loan Expert</button>
      <button type="button" class="rounded-md border border-brand-line px-3 py-2 text-sm font-semibold text-brand-blue" id="printBtn">Print</button>
      <button type="button" class="rounded-md border border-brand-line px-3 py-2 text-sm font-semibold text-brand-blue" id="shareBtn">WhatsApp</button>
      <button type="button" class="col-span-2 rounded-md border border-brand-line px-3 py-2 text-sm font-semibold text-brand-blue" id="copyLinkBtn">Copy share link</button>
    </div>
    <section class="mt-5 border-t border-brand-line pt-4">
      <details>
        <summary class="cursor-pointer font-heading text-base font-bold">Year-wise amortisation</summary>
        <div class="mt-4 max-h-72 overflow-auto rounded-lg border border-brand-line">
          <table class="w-full min-w-[620px] text-sm">
            <thead class="bg-brand-mist text-left text-xs uppercase text-slate-500"><tr><th class="px-3 py-2">Year</th><th class="px-3 py-2">Opening</th><th class="px-3 py-2">Principal</th><th class="px-3 py-2">Interest</th><th class="px-3 py-2">Closing</th></tr></thead>
            <tbody>${amortRows}</tbody>
          </table>
        </div>
      </details>
    </section>`;

  document.querySelector("#expertBtn").addEventListener("click", () => document.querySelector("#expertModal").classList.replace("hidden", "grid"));
  document.querySelector("#printBtn").addEventListener("click", () => window.print());
  document.querySelector("#shareBtn").addEventListener("click", shareWhatsApp);
  document.querySelector("#copyLinkBtn").addEventListener("click", copyShareLink);
}

function metric(label, value) {
  return `<div class="rounded-lg bg-brand-mist p-3"><p class="text-xs font-semibold uppercase text-slate-500">${label}</p><p class="mt-1 font-heading text-base font-bold">${value}</p></div>`;
}

function rateMetric() {
  const marketRate = currentMarketRate();
  const value = marketRate ? `${marketRate.toFixed(2)}%` : `${result.interest_rate.toFixed(2)}%`;
  const note = marketRate ? `<span class="mt-1 block text-[11px] font-medium normal-case text-slate-500">(based on current market rates)</span>` : "";
  return `<div class="rounded-lg bg-brand-mist p-3"><p class="text-xs font-semibold uppercase text-slate-500">Rate offered</p><p class="mt-1 font-heading text-base font-bold">${value}</p>${note}</div>`;
}

function currentMarketRate() {
  if (!bankRates || !bankRates.banks || bankRatesLoanType !== state.loan_type) return null;
  const selected = selectedBankName
    ? bankRates.banks.find((bank) => bank.name === selectedBankName)
    : null;
  const bank = selected || bestBankForBorrower();
  if (!bank) return null;
  return selectedBorrowerType === "self" ? Number(bank.selfMin) : Number(bank.salariedMin);
}

function renderTools() {
  document.querySelector("#scenarioTenureLabel").textContent = document.querySelector("#scenarioTenure").value;
  calculateScenario();
  document.querySelector("#emiToolOutput").innerHTML = `${metric("Loan amount", compactINR(result.max_loan))}${metric("EMI", formatINR(result.monthly_emi))}${metric("Rate", `${result.interest_rate.toFixed(2)}%`)}`;
  calculateTransfer();
  calculateAffordability();
}

async function calculateScenario() {
  const tenure = Number(document.querySelector("#scenarioTenure").value);
  const response = await fetch("/api/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...state, preferred_tenure_years: tenure })
  });
  const data = await response.json();
  const scenario = data.result;
  document.querySelector("#compareOutput").innerHTML = `
    ${scenarioCard("Current", result)}
    ${scenarioCard("Scenario B", scenario)}
  `;
}

function scenarioCard(title, item) {
  return `<div class="rounded-lg border border-brand-line p-4"><h3 class="font-heading font-bold">${title}</h3><div class="mt-3 space-y-2 text-sm"><p>Eligible: <strong>${compactINR(item.max_loan)}</strong></p><p>EMI: <strong>${formatINR(item.monthly_emi)}</strong></p><p>Interest: <strong>${formatINR(item.total_interest)}</strong></p><p>Rate: <strong>${item.interest_rate.toFixed(2)}%</strong></p></div></div>`;
}

async function calculateTransfer() {
  const response = await fetch("/api/balance-transfer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      outstanding: Number(document.querySelector("#btOutstanding").value),
      current_rate: Number(document.querySelector("#btCurrent").value),
      new_rate: Number(document.querySelector("#btNew").value),
      remaining_years: result.selected_tenure_years
    })
  });
  const data = await response.json();
  document.querySelector("#transferOutput").innerHTML = `${metric("Monthly saving", formatINR(data.monthly_saving))}${metric("Total saving", formatINR(data.total_saving))}${metric("New EMI", formatINR(data.new_emi))}`;
}

async function calculateAffordability() {
  const response = await fetch("/api/affordability", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      emi: Number(document.querySelector("#affordEmi").value),
      annual_rate: result.interest_rate,
      tenure_years: result.selected_tenure_years
    })
  });
  const data = await response.json();
  document.querySelector("#affordOutput").innerHTML = metric("Estimated affordable loan", compactINR(data.amount));
}

function renderFaqs() {
  const list = document.querySelector("#faqList");
  list.innerHTML = faqs[state.loan_type]
    .map((item) => `<details class="py-3"><summary class="cursor-pointer font-semibold">${item.q}</summary><p class="mt-2 text-sm text-slate-600">${item.a}</p></details>`)
    .join("");
}

function renderAll() {
  renderLiveLabels();
  renderResults();
  renderTools();
  renderFaqs();
  renderBankRates();
  if (window.lucide) window.lucide.createIcons();
}

async function loadBankRates(forceRefresh = false) {
  const status = document.querySelector("#bankRatesStatus");
  if (status) {
    status.classList.remove("hidden");
    status.innerHTML = `<span class="h-5 w-5 animate-spin rounded-full border-2 border-brand-line border-t-brand-blue"></span> Fetching current rates...`;
  }
  try {
    const params = new URLSearchParams({ loanType: state.loan_type });
    if (forceRefresh) params.set("refresh", "true");
    const response = await fetch(`/api/bank-rates?${params.toString()}`);
    if (!response.ok) throw new Error("Bank rate request failed");
    bankRates = await response.json();
    bankRatesLoanType = bankRates.loanType || state.loan_type;
  } catch (error) {
    bankRates = null;
    bankRatesLoanType = "";
  }
  renderAll();
}

function renderBankRates() {
  const section = document.querySelector("#bankRatesSection");
  if (!section) return;
  const status = document.querySelector("#bankRatesStatus");
  const grid = document.querySelector("#bankRateGrid");
  const details = document.querySelector("#bankRateDetails");
  const recommendation = document.querySelector("#bankRecommendation");
  if (!bankRates || bankRatesLoanType !== state.loan_type) {
    status.classList.remove("hidden");
    grid.innerHTML = "";
    details.innerHTML = "";
    recommendation.innerHTML = "";
    return;
  }

  status.classList.add("hidden");
  document.querySelector("#bankRatesUpdated").textContent = bankRates.lastUpdated;
  document.querySelector("#bankRatesSubtitle").textContent = `Compare current market rates for ${bankRates.productLabel || configs[state.loan_type].label.toLowerCase()}.`;
  document.querySelectorAll(".borrower-toggle").forEach((button) => {
    button.classList.toggle("active", button.dataset.borrower === selectedBorrowerType);
  });

  const banks = bankRates.banks || [];
  const rates = banks.map((bank) => displayRateForBank(bank));
  const minRate = Math.min(...rates);
  const maxRate = Math.max(...rates);

  grid.innerHTML = banks
    .map((bank) => {
      const rate = displayRateForBank(bank);
      const competitiveness = maxRate === minRate ? 100 : 100 - ((rate - minRate) / (maxRate - minRate)) * 72;
      const isSelected = bank.name === selectedBankName;
      const bestBadge = bank.isBest ? `<span class="rounded-full bg-emerald-50 px-2 py-1 text-xs font-bold text-emerald-700">Lowest rate</span>` : "";
      return `
        <button type="button" data-bank-name="${bank.name}" class="bank-rate-card rounded-lg border p-4 text-left transition ${isSelected ? "border-brand-blue bg-blue-50" : "border-brand-line hover:bg-brand-mist"}">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="font-heading text-base font-extrabold">${bank.name}</p>
              <p class="mt-2 text-3xl font-extrabold text-brand-blue">${rate.toFixed(2)}%</p>
              <p class="text-xs text-slate-500">p.a. starting rate</p>
            </div>
            ${bestBadge}
          </div>
          <p class="mt-3 text-sm text-slate-600">up to ${Number(bank.maxRate).toFixed(2)}% p.a.</p>
          <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div class="h-full rounded-full bg-brand-blue" style="width: ${competitiveness}%"></div>
          </div>
        </button>`;
    })
    .join("");

  document.querySelectorAll(".bank-rate-card").forEach((card) => {
    card.addEventListener("click", () => {
      selectedBankName = card.dataset.bankName === selectedBankName ? "" : card.dataset.bankName;
      renderAll();
    });
  });

  const selected = selectedBankName ? banks.find((bank) => bank.name === selectedBankName) : bestBankForBorrower();
  if (selected) {
    details.innerHTML = `
      <div class="rounded-lg border border-brand-line bg-brand-mist p-4">
        <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <h3 class="font-heading text-lg font-extrabold">${selected.name} details</h3>
          <span class="text-sm font-bold text-brand-blue">${selected.tag}</span>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-3">
          ${detail("Salaried start", `${Number(selected.salariedMin).toFixed(2)}%`)}
          ${detail("Self-employed start", `${Number(selected.selfMin).toFixed(2)}%`)}
          ${detail("Rate range", `${Number(selected.minRate).toFixed(2)}% - ${Number(selected.maxRate).toFixed(2)}%`)}
          ${detail("Max tenure", selected.tenure)}
          ${detail("Max loan", selected.maxLoan)}
          ${detail("Processing fee", selected.processing)}
        </div>
      </div>`;
  }

  const recommended = bestBankForBorrower();
  if (recommended) {
    const typeLabel = selectedBorrowerType === "self" ? "self-employed" : "salaried";
    recommendation.innerHTML = `<strong>${recommended.name}</strong> looks best for a ${typeLabel} borrower on this product right now because it has the lowest displayed starting rate at ${displayRateForBank(recommended).toFixed(2)}% p.a.`;
  }
}

function displayRateForBank(bank) {
  return Number(selectedBorrowerType === "self" ? bank.selfMin : bank.salariedMin);
}

function bestBankForBorrower() {
  if (!bankRates || !bankRates.banks || !bankRates.banks.length) return null;
  return [...bankRates.banks].sort((a, b) => displayRateForBank(a) - displayRateForBank(b))[0];
}

function detail(label, value) {
  return `<div class="rounded-md bg-white p-3"><p class="text-xs font-bold uppercase text-slate-500">${label}</p><p class="mt-1 font-heading font-bold">${value}</p></div>`;
}

function shareUrl() {
  return `${window.location.origin}/${configs[state.loan_type].slug}?state=${btoa(encodeURIComponent(JSON.stringify(state)))}`;
}

async function copyShareLink() {
  await navigator.clipboard.writeText(shareUrl());
}

function shareWhatsApp() {
  const message = `LoanCheck result: eligible up to ${compactINR(result.max_loan)} at ${result.interest_rate.toFixed(2)}%. ${shareUrl()}`;
  window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, "_blank", "noopener,noreferrer");
}

document.querySelector("#nextBtn").addEventListener("click", () => {
  if (currentStep < 3) currentStep += 1;
  updateStep();
  calculate();
});

document.querySelector("#backBtn").addEventListener("click", () => {
  if (currentStep > 1) currentStep -= 1;
  updateStep();
});

form.addEventListener("input", calculate);
form.addEventListener("change", calculate);

document.querySelectorAll("[data-loan-card]").forEach((card) => {
  card.addEventListener("click", () => {
    form.elements.loan_type.value = card.dataset.loanCard;
    history.pushState(null, "", `/${configs[card.dataset.loanCard].slug}`);
    calculate();
  });
});

document.querySelectorAll(".tool-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tool-tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tool-panel").forEach((panel) => panel.classList.add("hidden"));
    tab.classList.add("active");
    document.querySelector(`[data-tool-panel="${tab.dataset.tool}"]`).classList.remove("hidden");
  });
});

for (const id of ["scenarioTenure", "btOutstanding", "btCurrent", "btNew", "affordEmi"]) {
  document.querySelector(`#${id}`).addEventListener("input", renderTools);
}

document.querySelector("#closeModal").addEventListener("click", () => document.querySelector("#expertModal").classList.replace("grid", "hidden"));

document.querySelector("#refreshBankRates").addEventListener("click", () => loadBankRates(true));

document.querySelectorAll(".borrower-toggle").forEach((button) => {
  button.addEventListener("click", () => {
    selectedBorrowerType = button.dataset.borrower;
    selectedBankName = "";
    renderAll();
  });
});

document.querySelector("#language").addEventListener("change", (event) => {
  const lang = event.target.value;
  document.querySelectorAll("[data-label-en]").forEach((element) => {
    element.textContent = element.dataset[`label${lang[0].toUpperCase()}${lang.slice(1)}`];
  });
});

setInitialValues();
updateStep();
renderAll();
loadBankRates();
