import fs from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const i18nPath = new URL("static/i18n.js", root);
const sourcePaths = [
  new URL("static/app.js", root),
  new URL("static/metadata.js", root),
];

const i18nSource = fs.readFileSync(i18nPath, "utf8");
const initPosition = i18nSource.lastIndexOf("  init();");
const auditSource = `${i18nSource.slice(0, initPosition)}${i18nSource.slice(initPosition + "  init();".length)}`;
const context = {
  navigator: { language: "en" },
  localStorage: {
    getItem: () => "en",
    setItem: () => {},
  },
  window: {},
};
vm.runInNewContext(auditSource, context);

const hasHan = /[\u3400-\u9fff]/;
const exactSources = [];
for (const path of sourcePaths) {
  const lines = fs.readFileSync(path, "utf8").split(/\r?\n/);
  lines.forEach((line, index) => {
    const patterns = [
      /"([^"\n]*[\u3400-\u9fff][^"\n]*)"/g,
      /'([^'\n]*[\u3400-\u9fff][^'\n]*)'/g,
      /`([^`\n]*[\u3400-\u9fff][^`\n]*)`/g,
    ];
    patterns.forEach((pattern) => {
      for (const match of line.matchAll(pattern)) {
        if (!match[1].includes("${")) {
          exactSources.push({ path: path.pathname, line: index + 1, text: match[1] });
        }
      }
    });
  });
}

const dynamicSamples = [
  "Cloud checks passed. 通过率 100%，得分 55/55。",
  "MaaS prompt 策略：4 个",
  "失败样本：3 个",
  "3 个样本可用于回放。",
  "对照评测：Passed",
  "创建真实资源前门禁：Passed",
  "Schema dataarts.factory.import.v1alpha1 已通过；云上执行：Locked。",
  "已验证 8 个云参数映射，生成解析后的 DataArts 导入预览；云上执行：Locked。",
  "文件已通过",
  "mrs_transform.py 当前状态：Approved。生产执行仍需云上部署确认。",
  "加载失败: HTTP 500",
];

const failures = [];
for (const entry of exactSources) {
  const translated = context.window.i18n.t(entry.text);
  if (translated === entry.text || hasHan.test(translated)) {
    failures.push(`${entry.path}:${entry.line}: ${entry.text}`);
  }
}
for (const sample of dynamicSamples) {
  const translated = context.window.i18n.t(sample);
  if (translated === sample || hasHan.test(translated)) {
    failures.push(`dynamic sample: ${sample}`);
  }
}

if (failures.length) {
  throw new Error(`Missing English translations:\n${failures.join("\n")}`);
}

console.log(`i18n coverage passed: ${exactSources.length} exact strings and ${dynamicSamples.length} dynamic samples`);
