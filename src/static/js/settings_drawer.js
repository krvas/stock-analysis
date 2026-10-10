// Settings drawer: open from the gear, open on load after a refused save,
// and submit the instant form as soon as one of its fields changes.

function main() {
  const dialog = document.getElementById("settings-drawer");
  if (!dialog) {
    return;
  }
  document.querySelectorAll("[data-settings-open]").forEach((button) => {
    button.addEventListener("click", () => dialog.showModal());
  });
  dialog.querySelectorAll("[data-submit-on-change]").forEach((field) => {
    field.addEventListener("change", () => field.form.requestSubmit());
  });
  if (dialog.hasAttribute("data-open-on-load")) {
    dialog.showModal();
  }
}

main();
