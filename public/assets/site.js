
const menu = document.querySelector(".menu");
const links = document.querySelector(".links");
if (menu && links) menu.addEventListener("click", () => {
  const open = links.classList.toggle("open");
  menu.setAttribute("aria-expanded", String(open));
});
const form = document.querySelector("#quote-form");
if (form) form.addEventListener("submit", event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const status = document.querySelector(".formstatus");
  status.textContent = "The form is working locally, but submissions are not connected yet. No information was sent or stored.";
});
