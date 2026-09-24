document.getElementById("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("button");
  const error = document.getElementById("error");
  button.disabled = true;
  error.textContent = "";
  try { await window.caseLensSetup.save(document.getElementById("address").value); }
  catch (failure) { error.textContent = failure instanceof Error ? failure.message : "连接失败，请检查地址"; }
  finally { button.disabled = false; }
});
