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

})();