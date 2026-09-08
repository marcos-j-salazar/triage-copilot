const menuBtn = document.getElementById('menu-btn');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

function openSidebar() {
  sidebar.hidden = false;
  sidebarOverlay.hidden = false;
  requestAnimationFrame(() => {
    sidebar.classList.add('open');
  });
}

function closeSidebar() {
  sidebar.classList.remove('open');
  setTimeout(() => {
    sidebar.hidden = true;
    sidebarOverlay.hidden = true;
  }, 200);
}

menuBtn.addEventListener('click', openSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);