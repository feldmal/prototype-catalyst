const menu = document.querySelector(".menu");
const links = document.querySelector(".links");
if (menu && links) menu.addEventListener("click", () => {
  const open = links.classList.toggle("open");
  menu.setAttribute("aria-expanded", String(open));
});

const form = document.querySelector("#quote-form");
if (form) form.addEventListener("submit", async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;

  const status = document.querySelector(".formstatus");
  const button = form.querySelector('button[type="submit"]');
  const data = Object.fromEntries(new FormData(form).entries());
  status.textContent = "Sending your inquiry…";
  button.disabled = true;

  try {
    const response = await fetch("/api/quote", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Unable to send your inquiry.");

    form.reset();
    status.textContent = "Thanks — your inquiry has been sent. We'll be in touch.";
  } catch (error) {
    status.textContent = error.message || "We couldn't send your inquiry. Please try again.";
  } finally {
    button.disabled = false;
  }
});
