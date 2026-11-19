// Confirm before submitting any form marked with data-confirm="message"
document.addEventListener("submit", function (e) {
  var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) { e.preventDefault(); }
});
