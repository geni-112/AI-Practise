// Shared by the browser, report generator and template so their counts agree.
function projectInProgress(project) {
  return !project.archivedAt && project.status !== '挂起' && project.status !== '丢单' && project.stage < 8;
}
function isActivePoc(project) {
  return projectInProgress(project) && (project.stage === 3 || project.stage === 4);
}
function needsProjectAttention(project) {
  return !project.archivedAt && project.status !== '丢单' && project.stage < 8 && (project.status === '挂起' || !!project.risk);
}
function projectStatusLabel(project) {
  if (project.archivedAt) return '已归档';
  if (project.status === '丢单' || project.status === '挂起') return project.status;
  if (project.stage === 8) return '已完成';
  return project.risk ? '存在阻塞' : '正常';
}
