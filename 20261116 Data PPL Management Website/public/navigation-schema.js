// Stable IDs keep one workspace order across languages, roles and future menu additions.
const workspaceMenus = [
  {id:'practices', icon:'◇', label:'最佳实践', en:'Best practices', permissions:['practice.read']},
  {id:'home', icon:'◫', label:'工作台总览', en:'Overview', permissions:['project.read.all','project.read.own']},
  {id:'projects', icon:'▤', label:'项目运作', en:'Projects', permissions:['project.read.all','project.read.own']},
  {id:'poc', icon:'◉', label:'POC 中心', en:'POC center', permissions:['project.read.all','project.read.own']},
  {id:'library', icon:'▧', label:'资料库', en:'Resources', permissions:['resource.read']},
  {id:'reports', icon:'▥', label:'报表中心', en:'Reports', permissions:['report.view']},
  {id:'admin', icon:'⚙', label:'成员与角色', en:'Members & roles', permissions:['member.manage','role.manage']},
  {id:'maas', icon:'⚙', label:'架构分析设置', en:'Architecture AI settings', adminOnly:true},
  {id:'audit', icon:'◷', label:'操作记录', en:'Activity log', permissions:['audit.view']}
];
const workspaceMenuIds = workspaceMenus.map(menu=>menu.id);
function orderedWorkspaceMenus(saved) {
  const ids=new Set([...(Array.isArray(saved)?saved:[]),...workspaceMenuIds]);
  return [...ids].map(id=>workspaceMenus.find(menu=>menu.id===id)).filter(Boolean);
}
function canSeeWorkspaceMenu(user,menu) {
  return menu.adminOnly ? user.roleId==='admin' : menu.permissions.some(p=>user.permissions.includes(p));
}
