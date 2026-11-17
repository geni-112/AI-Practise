export function normalizeDisplayName(value) {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > 80 || /[\u0000-\u001f\u007f]/u.test(value)) {
    throw Object.assign(new Error('展示名须为 1–80 个字符的单行文字'), {status:400});
  }
  return value.trim();
}
