/* static/js/document_composer.js

Document Composer (Phase 9)
- Paper-style editable document surface
- Django inline formset add-line
- Catalog autofill (service/product) via /catalog/<id>/json/
- Live totals (subtotal, tax, total)
- Auto tax for taxable lines using doc-level sales_tax_percent
- Optional deposit (invoice only): percent or fixed dollars

Server remains the source of truth on save.
*/

(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function moneyToCents(raw) {
    if (raw === null || raw === undefined) return 0;
    var s = String(raw).trim();
    if (!s) return 0;
    s = s.replace(/[$,]/g, '');
    var v = parseFloat(s);
    if (isNaN(v)) return 0;
    return Math.round(v * 100);
  }

  function centsToMoney(cents) {
    cents = Math.max(0, parseInt(cents || 0, 10) || 0);
    return '$' + (cents / 100).toFixed(2);
  }

  function floatVal(el) {
    if (!el) return 0;
    var v = parseFloat(String(el.value || '').trim());
    if (isNaN(v)) return 0;
    return v;
  }

  function setup() {
    var root = qs('[data-doc-composer="1"]');
    if (!root) return;
    var form = qs('form[data-doc-form="1"]');
    if (!form) return;

    var tbody = qs('#ezLineItemsBody', root);
    var addBtn = qs('#ezAddLineBtn', root);
    var templateRow = qs('#ezLineItemEmptyRow', root);
    var totalFormsEl = qs('input[name$="-TOTAL_FORMS"]', form);

    var subtotalOut = qs('[data-ez-total="subtotal"]', root);
    var taxOut = qs('[data-ez-total="tax"]', root);
    var totalOut = qs('[data-ez-total="total"]', root);
    var depositOut = qs('[data-ez-total="deposit"]', root);
    var balanceOut = qs('[data-ez-total="balance"]', root);

    var taxPercentEl = qs('input[name="sales_tax_percent"]', root);
    var depositTypeEl = qs('select[name="deposit_type"]', root);
    var depositValueEl = qs('input[name="deposit_value"]', root);
    var depositLabelEl = qs('[data-ez-deposit-label="1"]', root);
    var depositWrap = qs('[data-ez-deposit-value="1"]', root);

    var catalogJsonBase = root.getAttribute('data-catalog-json-base') || '';

    function rowEls(row) {
      return {
        qty: qs('input[name$="-qty"]', row),
        unit: qs('input[name$="-unit_price_cents"]', row),
        tax: qs('input[name$="-tax_cents"]', row),
        taxable: qs('input[name$="-is_taxable"]', row),
        catalog: qs('select[name$="-catalog_item"]', row),
        name: qs('input[name$="-name"]', row),
        desc: qs('textarea[name$="-description"]', row),
        del: qs('input[name$="-DELETE"]', row),
        lineTotal: qs('[data-ez-line-total="1"]', row)
      };
    }

    function calcLine(row) {
      var els = rowEls(row);
      if (els.del && els.del.checked) {
        return { sub: 0, tax: 0, total: 0 };
      }
      var qty = floatVal(els.qty);
      var unitCents = moneyToCents(els.unit ? els.unit.value : '');
      var sub = Math.round(qty * unitCents);

      // Auto tax using doc-level percent
      var taxPct = floatVal(taxPercentEl);
      var taxCents = 0;
      if (els.taxable && els.taxable.checked && taxPct > 0) {
        taxCents = Math.round(sub * (taxPct / 100.0));
      }

      // Write computed tax into the tax input (keeps server consistent)
      if (els.tax) {
        els.tax.value = (taxCents / 100).toFixed(2);
      }

      var total = sub + taxCents;
      if (els.lineTotal) els.lineTotal.textContent = centsToMoney(total);
      return { sub: sub, tax: taxCents, total: total };
    }

    function computeTotals() {
      var subtotal = 0;
      var tax = 0;
      var total = 0;

      qsa('tr[data-ez-line="1"]', tbody).forEach(function (row) {
        var c = calcLine(row);
        subtotal += c.sub;
        tax += c.tax;
        total += c.total;
      });

      if (subtotalOut) subtotalOut.textContent = centsToMoney(subtotal);
      if (taxOut) taxOut.textContent = centsToMoney(tax);
      if (totalOut) totalOut.textContent = centsToMoney(total);

      // Deposit display (invoice only)
      if (depositTypeEl && depositValueEl && depositOut && balanceOut) {
        var dtype = String(depositTypeEl.value || 'none');
        var dep = 0;
        var dval = floatVal(depositValueEl);
        if (dtype === 'percent') {
          dep = Math.round(total * (dval / 100.0));
        } else if (dtype === 'fixed') {
          dep = moneyToCents(depositValueEl.value);
        }
        if (dep > total) dep = total;
        depositOut.textContent = centsToMoney(dep);
        balanceOut.textContent = centsToMoney(Math.max(0, total - dep));
      }
    }

    function syncDepositUI() {
      if (!depositTypeEl || !depositValueEl) return;
      var dtype = String(depositTypeEl.value || 'none');
      if (depositWrap) depositWrap.style.display = (dtype === 'none') ? 'none' : '';
      if (depositLabelEl) {
        depositLabelEl.textContent = (dtype === 'percent') ? 'Deposit (%)' : 'Deposit ($)';
      }
      // Provide a helpful default display
      if (dtype === 'none') {
        depositValueEl.value = '0.00';
      } else if (!String(depositValueEl.value || '').trim()) {
        depositValueEl.value = '0.00';
      }
    }

    function wireRow(row) {
      var els = rowEls(row);
      ['change', 'input'].forEach(function (evt) {
        if (els.qty) els.qty.addEventListener(evt, computeTotals);
        if (els.unit) els.unit.addEventListener(evt, computeTotals);
        if (els.taxable) els.taxable.addEventListener(evt, computeTotals);
        if (els.del) els.del.addEventListener(evt, computeTotals);
      });

      // Catalog autofill
      if (els.catalog) {
        els.catalog.addEventListener('change', function () {
          var id = String(els.catalog.value || '').trim();
          if (!id) {
            computeTotals();
            return;
          }

          var url = '';
          if (catalogJsonBase) {
            url = catalogJsonBase.replace(/0\/json\/$/, id + '/json/');
          } else {
            url = '/catalog/' + id + '/json/';
          }

          fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (els.name && (!els.name.value || els.name.value.trim() === '')) {
                els.name.value = data.name || '';
              }
              if (els.desc && (!els.desc.value || els.desc.value.trim() === '')) {
                els.desc.value = data.description || '';
              }
              if (els.unit) {
                var cents = parseInt(data.unit_price_cents || 0, 10) || 0;
                els.unit.value = (cents / 100).toFixed(2);
              }
              if (els.taxable) {
                els.taxable.checked = !!data.is_taxable;
              }
              computeTotals();
            })
            .catch(function () { computeTotals(); });
        });
      }
    }

    function addRow() {
      if (!templateRow || !tbody || !totalFormsEl) return;
      var total = parseInt(totalFormsEl.value || '0', 10) || 0;
      var html = templateRow.innerHTML.replace(/__prefix__/g, String(total));
      var tr = document.createElement('tr');
      tr.setAttribute('data-ez-line', '1');
      tr.innerHTML = html;
      tbody.appendChild(tr);
      totalFormsEl.value = String(total + 1);
      wireRow(tr);
      computeTotals();
    }

    if (addBtn) {
      addBtn.addEventListener('click', function (e) {
        e.preventDefault();
        addRow();
      });
    }

    // Wire existing rows
    qsa('tr[data-ez-line="1"]', tbody).forEach(wireRow);

    // Global controls
    if (taxPercentEl) {
      ['change', 'input'].forEach(function (evt) {
        taxPercentEl.addEventListener(evt, computeTotals);
      });
    }

    if (depositTypeEl) {
      depositTypeEl.addEventListener('change', function () {
        syncDepositUI();
        computeTotals();
      });
    }
    if (depositValueEl) {
      ['change', 'input'].forEach(function (evt) {
        depositValueEl.addEventListener(evt, computeTotals);
      });
    }

    syncDepositUI();
    computeTotals();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();
