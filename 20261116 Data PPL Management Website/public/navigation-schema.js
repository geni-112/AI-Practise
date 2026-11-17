// Stable IDs keep one workspace order across languages, roles and future menu additions.
const workspaceMenus = [
  {id:'practices', label:'最佳实践', en:'Best practices', permissions:['practice.read']},
  {id:'home', label:'工作台总览', en:'Overview', permissions:['project.read.all','project.read.own']},
  {id:'projects', label:'项目运作', en:'Projects', permissions:['project.read.all','project.read.own']},
  {id:'poc', label:'POC 中心', en:'POC center', permissions:['project.read.all','project.read.own']},
  {id:'library', label:'资料库', en:'Resources', permissions:['resource.read']},
  {id:'reports', label:'报表中心', en:'Reports', permissions:['report.view']},
  {id:'admin', label:'成员与角色', en:'Members & roles', permissions:['member.manage','role.manage']},
  {id:'maas', label:'设置', en:'Settings', adminOnly:true},
  {id:'audit', label:'操作记录', en:'Activity log', permissions:['audit.view']}
];
const workspaceMenuIds = workspaceMenus.map(menu=>menu.id);
function orderedWorkspaceMenus(saved) {
  const ids=new Set([...(Array.isArray(saved)?saved:[]),...workspaceMenuIds]);
  return [...ids].map(id=>workspaceMenus.find(menu=>menu.id===id)).filter(Boolean);
}
function canSeeWorkspaceMenu(user,menu) {
  return menu.adminOnly ? user.roleId==='admin' : menu.permissions.some(p=>user.permissions.includes(p));
}
