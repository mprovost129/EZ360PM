(function(){
  // Prevent double-initialization if base.html is included multiple times
  if (window.__EZ360PM_TIMER_INIT__) return;
  window.__EZ360PM_TIMER_INIT__ = true;

  function csrftoken() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function fmt(sec){
    sec = Math.max(0, parseInt(sec||0,10));
    const h = String(Math.floor(sec/3600)).padStart(2,'0');
    const m = String(Math.floor((sec%3600)/60)).padStart(2,'0');
    const s = String(sec%60).padStart(2,'0');
    return `${h}:${m}:${s}`;
  }
  async function post(url, payload){
    const body = new URLSearchParams(payload || {});
    const r = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {"X-CSRFToken": csrftoken(), "Content-Type":"application/x-www-form-urlencoded"},
      body
    });
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); if (j.error) msg = j.error; } catch {}
      throw new Error(msg || "Request failed");
    }
    return r.json();
  }

  function initTimerWidget(){
    const root = document.getElementById('timerWidget');
    if (!root) return; // topbar not present on this page

    const urls = {
      status: root.dataset.urlStatus,
      start:  root.dataset.urlStart,
      stop:   root.dataset.urlStop,
      save:   root.dataset.urlSave,
      delBase: (root.dataset.urlDelPrefix || "").replace(/0\/?$/, "") // ends with '/delete/'
    };

    const dd   = document.getElementById('timerDropdown');
    const dot  = document.getElementById('timerDot');
    const lbl  = document.getElementById('timerLabel');
    const idle = document.getElementById('timerIdle');
    const run  = document.getElementById('timerRunning');
    const projSelect = document.getElementById('timerProject');
    const notesIdle  = document.getElementById('timerNotesIdle');
    const notesRun   = document.getElementById('timerNotes');
    const projNameEl = document.getElementById('timerProjectName');
    const elapsedEl  = document.getElementById('elapsedText');

    const btnStart   = document.getElementById('btnStart');
    const btnStop    = document.getElementById('btnStopSave');
    const btnSave    = document.getElementById('btnSaveNotes');
    const btnDelete  = document.getElementById('btnDelete');

    let current = null; // {entry_id, project_name, start_time, elapsed_seconds}
    let tickId = null;

    function setRunningUI(running){
      dot.classList.toggle('d-none', !running);
      lbl.textContent = running ? 'Running' : 'Timer';
      idle.classList.toggle('d-none', running);
      run.classList.toggle('d-none', !running);
    }

    async function refresh(){
      try {
        const r = await fetch(urls.status, {credentials:'same-origin'});
        const data = await r.json();
        if(!data.running){
          current = null;
          if (tickId) { clearInterval(tickId); tickId = null; }
          setRunningUI(false);
          return;
        }
        current = data;
        projNameEl.textContent = data.project_name;
        notesRun.value = data.notes || "";
        elapsedEl.textContent = fmt(data.elapsed_seconds);
        setRunningUI(true);
        if (!tickId){
          tickId = setInterval(()=> {
            if (!current) return;
            current.elapsed_seconds += 1;
            elapsedEl.textContent = fmt(current.elapsed_seconds);
          }, 1000);
        }
      } catch (e) {
        // fail silently in UI
      }
    }

    btnStart && btnStart.addEventListener('click', async ()=>{
      const pid = projSelect.value;
      if(!pid){ alert("Select a project."); return; }
      await post(urls.start, {project_id: pid, notes: (notesIdle.value||"")});
      notesIdle.value = "";
      await refresh();
    });

    btnStop && btnStop.addEventListener('click', async ()=>{
      await post(urls.stop, {notes: (notesRun.value||"")});
      await refresh();
    });

    btnSave && btnSave.addEventListener('click', async ()=>{
      if (!current) return;
      await post(urls.save, {entry_id: current.entry_id, notes: (notesRun.value||"")});
    });

    btnDelete && btnDelete.addEventListener('click', async ()=>{
      if (!current) return;
      if (!confirm("Delete this time entry?")) return;
      await post(urls.delBase + current.entry_id + "/", {});
      await refresh();
    });

    document.addEventListener('shown.bs.dropdown', (e)=>{
      if (e.target === dd) refresh();
    });
    // First load
    refresh();
  }

  document.addEventListener('DOMContentLoaded', initTimerWidget);
})();
