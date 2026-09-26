const menuBtn = document.getElementById('menu-btn');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.hidden = false;
}

function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.hidden = true;
}

menuBtn.addEventListener('click', openSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

sidebar.querySelectorAll('a').forEach(link => link.addEventListener('click', closeSidebar));
