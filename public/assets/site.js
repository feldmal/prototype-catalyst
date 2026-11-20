const menu = document.querySelector(".menu");
const links = document.querySelector(".links");
if (menu && links) {
  menu.addEventListener("click", () => {
    const open = links.classList.toggle("open");
    menu.setAttribute("aria-expanded", String(open));
  });
  links.addEventListener("click", event => {
    if (event.target.closest("a")) {
      links.classList.remove("open");
      menu.setAttribute("aria-expanded", "false");
    }
  });
}

const form = document.querySelector("#quote-form");
if (form) form.addEventListener("submit", async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;

  const status = document.querySelector(".formstatus");
  const button = form.querySelector('button[type="submit"]');
  const originalButtonText = button.textContent;
  const data = Object.fromEntries(new FormData(form).entries());
  status.textContent = "Sending your inquiry…";
  button.disabled = true;
  button.textContent = "Sending…";

  try {
    const response = await fetch("/api/quote", {
      method: "POST",
      headers: { "content-type": "application/json", "accept": "application/json" },
      body: JSON.stringify(data),
      credentials: "same-origin"
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok) throw new Error(result.error || "We couldn't send your inquiry. Please try again later.");
    form.reset();
    status.textContent = "Thanks — your inquiry has been sent. We'll be in touch.";
  } catch (error) {
    status.textContent = error instanceof TypeError
      ? "We couldn't reach the inquiry service. Check your connection and try again."
      : (error.message || "We couldn't send your inquiry. Please try again later.");
  } finally {
    button.disabled = false;
    button.textContent = originalButtonText;
  }
});
