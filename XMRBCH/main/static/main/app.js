const API = (window.BASE_PATH || '') + '/api';

const App = {
  direction: 'bch_to_xmr',
  rates: null,
  swapId: null,
  pollTimer: null,
  countdownTimer: null,
  expiresAt: null,

  // ── Init ───────────────────────────────────────────────────────────────
  init() {
    this.fetchRates();
    setInterval(() => this.fetchRates(), 30000);
    // Resume a swap after reload / from a bookmark: #swap=<uuid>
    const m = location.hash.match(/swap=([0-9a-f-]{36})/i);
    if (m) this.resumeSwap(m[1]);
  },

  async resumeSwap(swapId) {
    try {
      const resp = await fetch(`${API}/swap/${swapId}/`);
      if (!resp.ok) { history.replaceState(null, '', location.pathname); return; }
      const data = await resp.json();
      this.swapId = swapId;
      this.showDepositPanel({
        ...data,
        deposit_amount: data.deposit_amount_expected,
      });
      this.handleStatus(data);
      if (!['complete', 'failed'].includes(data.status)) this.startPolling();
    } catch(e) { /* ignore */ }
  },

  // ── Rates ──────────────────────────────────────────────────────────────
  async fetchRates() {
    try {
      const r = await fetch(`${API}/rates/`).then(res => res.json());
      if (r.error) return;
      this.rates = r;
      this.updateRatesBar();
      this.updateFormRates();
    } catch(e) { /* network error, ignore */ }
  },

  updateRatesBar() {
    const r = this.rates;
    const fmt = (n, d=2) => n != null ? '$' + Number(n).toFixed(d) : '—';
    document.getElementById('rb-bch-usd').textContent = fmt(r.bch_usd);
    document.getElementById('rb-xmr-usd').textContent = fmt(r.xmr_usd);
    document.getElementById('rb-bch-xmr').textContent = r.spot_bch_to_xmr ? Number(r.spot_bch_to_xmr).toFixed(4) : '—';
    document.getElementById('rb-xmr-bch').textContent = r.spot_xmr_to_bch ? Number(r.spot_xmr_to_bch).toFixed(4) : '—';
    document.getElementById('rates-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
  },

  updateFormRates() {
    if (!this.rates) return;
    const r = this.rates;
    const d = this.direction;
    const isBchToXmr = d === 'bch_to_xmr';

    // Max hint
    const maxOut = isBchToXmr ? r.xmr_balance : r.bch_balance;
    const outCur = isBchToXmr ? 'XMR' : 'BCH';
    const hint = document.getElementById('max-hint');
    if (maxOut != null) {
      let text = `Max available: ${Number(maxOut).toFixed(6)} ${outCur}`;
      if (isBchToXmr && r.xmr_locked_balance != null) {
        text += ` (Locked ${Number(r.xmr_locked_balance).toFixed(6)} XMR)`;
      }
      hint.textContent = text;
    } else {
      hint.textContent = 'Max available: wallet offline';
    }

    // Rate info
    const ourRate = isBchToXmr ? r.our_bch_to_xmr : r.our_xmr_to_bch;
    const inCur   = isBchToXmr ? 'BCH' : 'XMR';
    document.getElementById('rate-info').innerHTML =
      `Our rate: <span>1 ${inCur} = ${Number(ourRate).toFixed(6)} ${outCur}</span>` +
      ` &nbsp;|&nbsp; Fee: <span>${r.fee_percent}%</span>`;

    this.onAmountChange();
  },

  // ── Direction toggle ───────────────────────────────────────────────────
  setDirection(dir) {
    this.direction = dir;
    document.getElementById('btn-bch-xmr').classList.toggle('active', dir === 'bch_to_xmr');
    document.getElementById('btn-xmr-bch').classList.toggle('active', dir === 'xmr_to_bch');
    const isBchToXmr = dir === 'bch_to_xmr';
    document.getElementById('send-currency').textContent    = isBchToXmr ? 'BCH' : 'XMR';
    document.getElementById('receive-currency').textContent = isBchToXmr ? 'XMR' : 'BCH';
    document.getElementById('addr-label').textContent       = isBchToXmr ? 'Your XMR Address' : 'Your BCH Address';
    document.getElementById('receiving-address').placeholder =
      isBchToXmr ? 'Enter your Monero (XMR) address' : 'Enter your Bitcoin Cash (BCH) address';
    document.getElementById('amount-input').value = '';
    document.getElementById('receive-amount').textContent = '—';
    this.hideError();
    this.updateFormRates();
  },

  // ── Amount calculation ─────────────────────────────────────────────────
  onAmountChange() {
    if (!this.rates) return;
    const amount = parseFloat(document.getElementById('amount-input').value) || 0;
    const r = this.rates;
    const ourRate = this.direction === 'bch_to_xmr' ? r.our_bch_to_xmr : r.our_xmr_to_bch;
    if (amount > 0 && ourRate) {
      document.getElementById('receive-amount').textContent = (amount * ourRate).toFixed(8);
    } else {
      document.getElementById('receive-amount').textContent = '—';
    }
  },

  setMax() {
    if (!this.rates) return;
    const r = this.rates;
    const isBchToXmr = this.direction === 'bch_to_xmr';
    // Max input = max output wallet balance / our rate
    const maxOut  = isBchToXmr ? r.xmr_balance : r.bch_balance;
    const ourRate = isBchToXmr ? r.our_bch_to_xmr : r.our_xmr_to_bch;
    if (maxOut != null && ourRate) {
      const maxIn = maxOut / ourRate;
      document.getElementById('amount-input').value = maxIn.toFixed(8);
      this.onAmountChange();
    }
  },

  // ── Swap init ──────────────────────────────────────────────────────────
  async initSwap() {
    this.hideError();
    const amount  = parseFloat(document.getElementById('amount-input').value);
    const address = document.getElementById('receiving-address').value.trim();

    if (!amount || amount <= 0) return this.showError('Please enter an amount to send.');
    if (!address)               return this.showError('Please enter your receiving address.');

    const btn = document.getElementById('btn-swap');
    btn.disabled = true;
    btn.textContent = 'Creating swap…';

    try {
      const resp = await fetch(`${API}/swap/init/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          direction: this.direction,
          amount: amount,
          receiving_address: address,
        }),
      }).then(r => r.json());

      if (resp.error) {
        this.showError(resp.error);
        return;
      }
      this.swapId = resp.swap_id;
      history.replaceState(null, '', `#swap=${resp.swap_id}`);
      this.showDepositPanel(resp);
      this.updateStatusBadge('pending');
      this.startPolling();

    } catch(e) {
      this.showError('Network error. Please try again.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'SWAP NOW';
    }
  },

  // ── Deposit panel ──────────────────────────────────────────────────────
  showDepositPanel(data) {
    document.getElementById('swap-panel').style.display    = 'none';
    document.getElementById('deposit-panel').style.display = 'block';

    document.getElementById('dp-amount').textContent   = data.deposit_amount;
    document.getElementById('dp-currency').textContent  = data.from_currency.toUpperCase();
    document.getElementById('dp-address').textContent   = data.deposit_address;
    document.getElementById('dp-order-id').textContent  = data.order_number || data.swap_id.split('-')[0].toUpperCase();
    document.getElementById('dp-receive').textContent   = `≈ ${Number(data.send_amount).toFixed(8)} ${data.to_currency.toUpperCase()}`;
    document.getElementById('dp-rate').textContent      = `1 ${data.from_currency.toUpperCase()} = ${Number(data.rate).toFixed(6)} ${data.to_currency.toUpperCase()}`;

    // QR code
    document.getElementById('qr-code').innerHTML = '';
    new QRCode(document.getElementById('qr-code'), {
      text: data.deposit_address,
      width: 200, height: 200,
      colorDark: '#000000', colorLight: '#ffffff',
    });

    // Countdown
    this.expiresAt = new Date(data.expires_at);
    this.startCountdown();
  },

  copyAddress() {
    const addr = document.getElementById('dp-address').textContent;
    navigator.clipboard.writeText(addr).then(() => {
      document.getElementById('copy-hint').textContent = 'Copied!';
      setTimeout(() => document.getElementById('copy-hint').textContent = 'Click address to copy', 2000);
    });
  },

  startCountdown() {
    if (this.countdownTimer) clearInterval(this.countdownTimer);
    const update = () => {
      const secs = Math.max(0, Math.round((this.expiresAt - Date.now()) / 1000));
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = secs % 60;
      document.getElementById('countdown').textContent =
        secs > 0
          ? `Expires in ${h}h ${String(m).padStart(2,'0')}m ${String(s).padStart(2,'0')}s`
          : 'Expired';
    };
    update();
    this.countdownTimer = setInterval(update, 1000);
  },

  // ── Status polling ─────────────────────────────────────────────────────
  startPolling() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => this.pollStatus(), 10000);
  },

  async pollStatus() {
    if (!this.swapId) return;
    try {
      const data = await fetch(`${API}/swap/${this.swapId}/`).then(r => r.json());
      this.handleStatus(data);
    } catch(e) { /* ignore */ }
  },

  handleStatus(data) {
    this.updateStatusBadge(data.status, data);
    if (data.status !== 'pending') {
      clearInterval(this.countdownTimer);
      document.getElementById('countdown').textContent = '';
    }
    if (['complete', 'failed'].includes(data.status)) {
      clearInterval(this.pollTimer);
      this.showCompletePanel(data);
    }
    // "expired" keeps polling: a late deposit is still processed.
  },

  updateStatusBadge(status, data = {}) {
    const badge = document.getElementById('status-badge');
    const text  = document.getElementById('status-text');
    const dot   = badge.querySelector('.dot');
    const labels = {
      pending:    'Waiting for deposit…',
      confirming: `Deposit seen (${data.deposit_amount_received || ''} ${data.from_currency || ''}) — waiting for confirmations…`,
      received:   data.notes || 'Deposit received — processing…',
      sending:  'Sending funds…',
      complete: 'Complete!',
      failed:   'Swap failed. Please contact support.',
      expired:  'Expired — no deposit received. If you already sent funds, they will still be processed.',
    };
    badge.className = `status-badge status-${status}`;
    text.textContent = labels[status] || status;
    dot.className = 'dot' + (['pending','confirming','received','sending'].includes(status) ? ' pulse' : '');
  },

  // ── Complete panel ─────────────────────────────────────────────────────
  showCompletePanel(data) {
    document.getElementById('swap-panel').style.display     = 'none';
    document.getElementById('deposit-panel').style.display  = 'none';
    document.getElementById('complete-panel').style.display = 'block';

    const ok = data.status === 'complete';
    document.getElementById('complete-icon').textContent  = ok ? '✓' : '✗';
    document.getElementById('complete-title').textContent = ok ? 'Swap Complete!' : 'Swap Failed';
    document.getElementById('complete-sub').textContent   = ok
      ? 'Funds sent to your address.'
      : `Please contact support with order # ${data.order_number}.`;
    document.getElementById('cp-sent').textContent  = data.send_amount ? `${Number(data.send_amount).toFixed(8)} ${data.to_currency.toUpperCase()}` : '—';
    document.getElementById('cp-addr').textContent  = data.receiving_address;
    document.getElementById('cp-txhash').textContent = data.send_tx_hash || '—';
  },

  // ── Reset ──────────────────────────────────────────────────────────────
  reset() {
    this.swapId = null;
    history.replaceState(null, '', location.pathname);
    if (this.pollTimer)     clearInterval(this.pollTimer);
    if (this.countdownTimer) clearInterval(this.countdownTimer);
    document.getElementById('amount-input').value = '';
    document.getElementById('receiving-address').value = '';
    document.getElementById('receive-amount').textContent = '—';
    document.getElementById('qr-code').innerHTML = '';
    document.getElementById('complete-panel').style.display = 'none';
    document.getElementById('deposit-panel').style.display  = 'none';
    document.getElementById('swap-panel').style.display    = 'block';
    this.fetchRates();
  },

  // ── Errors ─────────────────────────────────────────────────────────────
  showError(msg) {
    const el = document.getElementById('form-error');
    el.textContent = msg;
    el.style.display = 'block';
  },
  hideError() {
    document.getElementById('form-error').style.display = 'none';
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
