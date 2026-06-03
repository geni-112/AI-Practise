const timeline = [
  "T-7: confirm DLI queue, OBS, IAM agency, Hudi compatibility",
  "T-1: package jobs, upload CDC data and scripts to OBS",
  "T0: run bronze Hudi jobs for 21 tables",
  "T0: run silver Hudi upsert/delete jobs after bronze success",
  "T+1h: collect DLI states, Hudi commits, notebook success rate"
];
const list = document.querySelector("#timeline");
timeline.forEach(item => {
  const li = document.createElement("li");
  li.textContent = item;
  list.appendChild(li);
});
