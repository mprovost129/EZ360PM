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
  function openSidebar(){ document.body.classList.add("sidebar-open"); }
  function closeSidebar(){ document.body.classList.remove("sidebar-open"); }
  function toggleSidebar(){ document.body.classList.toggle("sidebar-open"); }

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
})();
