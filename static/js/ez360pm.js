/* EZ360PM UI behaviors:
   - theme toggle (light/dark) persisted in localStorage
   - mobile sidebar open/close
   - topbar actions menu open/close on mobile
*/
(function(){
  const THEME_KEY = "ez360pm.theme";
  const html = document.documentElement;

  function applyTheme(theme){
    const t = (theme === "dark") ? "dark" : "light";
    html.setAttribute("data-theme", t);
    try{ localStorage.setItem(THEME_KEY, t); }catch(e){}
    const btn = document.getElementById("themeToggleBtn");
    if (btn){
      btn.setAttribute("aria-label", t === "dark" ? "Switch to light mode" : "Switch to dark mode");
      const icon = btn.querySelector("i");
      if (icon){
        icon.className = (t === "dark") ? "bi bi-sun" : "bi bi-moon-stars";
      }
    }
  }

  function initTheme(){
    let theme = null;
    try{ theme = localStorage.getItem(THEME_KEY); }catch(e){}
    if (!theme){
      // Prefer OS, default light
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) theme="dark";
      else theme="light";
    }
    applyTheme(theme);
  }

  // Sidebar
  function openSidebar(){ document.body.classList.add("sidebar-open"); document.body.classList.add("no-scroll"); }
  function closeSidebar(){ document.body.classList.remove("sidebar-open"); document.body.classList.remove("no-scroll"); }
  function toggleSidebar(){ document.body.classList.toggle("sidebar-open"); document.body.classList.toggle("no-scroll"); }

  // Topbar actions (mobile)
  function openActions(){ actions?.classList.add("is-open"); }
  function closeActions(){ actions?.classList.remove("is-open"); }
  function toggleActions(){ actions?.classList.toggle("is-open"); }

  // Wire up
  initTheme();

  const themeBtn = document.getElementById("themeToggleBtn");
  if (themeBtn){
    themeBtn.addEventListener("click", function(e){
      e.preventDefault();
      const cur = html.getAttribute("data-theme") || "light";
      applyTheme(cur === "dark" ? "light" : "dark");
    });
  }

  const sidebarBtn = document.getElementById("sidebarToggleBtn");
  if (sidebarBtn){
    sidebarBtn.addEventListener("click", function(e){
      e.preventDefault();
      toggleSidebar();
    });
  }
  const overlay = document.getElementById("sidebarOverlay");
  if (overlay){
    overlay.addEventListener("click", function(){ closeSidebar(); });
  }

  // Close sidebar on navigation click (mobile/tablet)
  const sidebar = document.querySelector(".app-sidebar");
  if (sidebar){
    sidebar.addEventListener("click", function(e){
      const a = e.target.closest("a");
      if (!a) return;
      if (window.matchMedia("(max-width: 991.98px)").matches){
        closeSidebar();
      }
    });
  }

  // Ensure mobile drawers close when switching to desktop
  window.addEventListener("resize", function(){
    if (window.matchMedia("(min-width: 992px)").matches){
      closeSidebar();
      closeActions();
    }
  });

  const actionsBtn = document.getElementById("topbarActionsToggleBtn");
  const actions = document.getElementById("topbarActions");
  if (actionsBtn && actions){
    actionsBtn.addEventListener("click", function(e){
      e.preventDefault();
      e.stopPropagation();
      toggleActions();
    });
    document.addEventListener("click", function(){ closeActions(); });
    actions.addEventListener("click", function(e){ e.stopPropagation(); });
  }

  // ESC closes both
  document.addEventListener("keydown", function(e){
    if (e.key === "Escape"){
      closeSidebar();
      closeActions();
    }
  });

  // When resizing to desktop, ensure we don't stay open
  window.addEventListener("resize", function(){
    if (window.innerWidth >= 992){
      closeSidebar();
      closeActions();
    }
  });

  // EZ dropdown helper (Bootstrap-independent)
  function initEzDropdown(toggleId, menuId){
    const toggle = document.getElementById(toggleId);
    const menu = document.getElementById(menuId);
    if(!toggle || !menu) return;
    if(!toggle.getAttribute('aria-controls')) toggle.setAttribute('aria-controls', menuId);

    const dropdown = toggle.closest('.dropdown');

    function close(){
      if(dropdown) dropdown.classList.remove('show');
      menu.classList.remove('show');
      toggle.setAttribute('aria-expanded','false');
    }
    function open(){
      if(dropdown) dropdown.classList.add('show');
      menu.classList.add('show');
      toggle.setAttribute('aria-expanded','true');
      // focus first actionable item for keyboard users
      const first = menu.querySelector('a, button, input, [tabindex]:not([tabindex="-1"])');
      if(first) { try { first.focus(); } catch(e){} }
    }

    toggle.addEventListener('click', function(e){
      e.preventDefault();
      e.stopPropagation();
      if(menu.classList.contains('show')) close(); else open();
    });


    toggle.addEventListener('keydown', function(e){
      if(e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' '){
        e.preventDefault();
        if(!menu.classList.contains('show')) open();
      }
      if(e.key === 'ArrowUp'){
        e.preventDefault();
        if(!menu.classList.contains('show')) open();
      }
    });

    document.addEventListener('click', function(){
      if(menu.classList.contains('show')) close();
    });

    document.addEventListener('keydown', function(e){
      if(e.key === 'Escape') close();
    });
  }

  initEzDropdown('companyDropdownToggle', 'companyDropdownMenu');

  // Sidebar active link highlighting (Phase 8 UI polish)
  (function markActiveSidebarLink(){
    const links = Array.from(document.querySelectorAll('.app-sidebar a.sidebar-link[href]'));
    if (!links.length) return;

    const path = window.location.pathname || '/';

    function normalize(p){
      if (!p) return '/';
      // strip query/hash handled by browser for pathname already
      if (p.length > 1 && p.endsWith('/')) return p.slice(0, -1);
      return p;
    }

    const cur = normalize(path);

    // Prefer the longest matching prefix link (most specific)
    let best = null;
    let bestLen = -1;

    for (const a of links){
      const href = a.getAttribute('href') || '';
      if (!href || href === '#' || href.startsWith('javascript:')) continue;
      if (a.hasAttribute('data-bs-toggle')) continue;
      // ignore external links
      if (href.startsWith('http://') || href.startsWith('https://')) continue;

      const target = normalize(href);
      if (target === '/') continue;

      if (cur === target || cur.startsWith(target + '/')){
        if (target.length > bestLen){
          best = a;
          bestLen = target.length;
        }
      }
    }

    if (!best) return;
    best.classList.add('active');

    // If link is inside a collapsed group, open it
    const collapse = best.closest('.collapse');
    if (collapse && !collapse.classList.contains('show')){
      collapse.classList.add('show');
    }
  })();

  // ---------------------------------------------------------------------------
  // Phase 8F: Micro-interactions
  // ---------------------------------------------------------------------------

  // Auto-dismiss Django flash messages (Bootstrap alerts) after a short delay.
  (function initAutoDismissAlerts(){
    const alerts = Array.from(document.querySelectorAll('.alert.alert-dismissible'));
    if (!alerts.length) return;

    // Errors/warnings should stay until dismissed.
    function isPersistent(el){
      const cls = (el.className || '').toLowerCase();
      if (el.hasAttribute('data-ez-persist')) return true;
      return cls.includes('alert-danger') || cls.includes('alert-warning');
    }

    const delayMs = 4500;
    alerts.forEach(function(el){
      if (isPersistent(el)) return;
      window.setTimeout(function(){
        try{
          if (window.bootstrap && bootstrap.Alert){
            bootstrap.Alert.getOrCreateInstance(el).close();
          }else{
            el.remove();
          }
        }catch(e){
          try{ el.remove(); }catch(_e){}
        }
      }, delayMs);
    });
  })();

  // Confirmation helper for destructive actions.
  // Usage:
  //   <a data-ez-confirm="Delete this?" ...>
  //   <form data-ez-confirm="Void invoice?" ...>
  (function initConfirmations(){
    function clickHandler(e){
      const el = e.target.closest('[data-ez-confirm]');
      if (!el) return;
      // If it's a form, submit handler will catch it.
      if (el.tagName && el.tagName.toLowerCase() === 'form') return;
      const msg = el.getAttribute('data-ez-confirm') || 'Are you sure?';
      if (!window.confirm(msg)){
        e.preventDefault();
        e.stopPropagation();
      }
    }

    document.addEventListener('click', clickHandler, true);

    document.addEventListener('submit', function(e){
      const form = e.target;
      if (!form || !form.matches || !form.matches('form[data-ez-confirm]')) return;
      const msg = form.getAttribute('data-ez-confirm') || 'Are you sure?';
      if (!window.confirm(msg)){
        e.preventDefault();
        e.stopPropagation();
      }
    }, true);
  })();

  // Disable submit buttons on submit to prevent double-posts and show a spinner.
  // Opt-out per form with: data-ez-no-disable
  (function initSubmitGuards(){
    function isGetForm(form){
      const m = (form.getAttribute('method') || '').toLowerCase();
      return !m || m === 'get';
    }

    function addSpinner(btn){
      if (!btn) return;
      if (btn.getAttribute('data-ez-loading') === '1') return;
      btn.setAttribute('data-ez-loading', '1');
      btn.setAttribute('data-ez-orig-html', btn.innerHTML);
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' + btn.innerHTML;
    }

    function disableButton(btn){
      if (!btn) return;
      btn.disabled = true;
      btn.setAttribute('aria-disabled', 'true');
    }

    document.addEventListener('submit', function(e){
      const form = e.target;
      if (!form || !form.matches || !form.matches('form')) return;
      if (form.hasAttribute('data-ez-no-disable')) return;
      if (isGetForm(form)) return;

      const submitter = e.submitter || null;
      const buttons = Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"]'));

      // If we know the submitter, prefer spinning that button.
      if (submitter && submitter.tagName && submitter.tagName.toLowerCase() === 'button'){
        addSpinner(submitter);
        disableButton(submitter);
      }else{
        const firstBtn = buttons.find(b => (b.tagName || '').toLowerCase() === 'button') || null;
        if (firstBtn){
          addSpinner(firstBtn);
          disableButton(firstBtn);
        }
      }

      // Always disable all submit buttons to prevent double-submits.
      buttons.forEach(disableButton);
    }, true);
  })();

})();