// OCR references are local to a single image. Keep the original record for audit and
// derive the reader's text and its source labels together for both report languages.
const practiceCitations = (() => {
  const atom = 'L[1-9]\\d{0,2}(?![A-Za-z0-9_])';
  const endNumber = '[1-9]\\d{0,2}';
  const rangeSeparator = '\\s*(?:[-–—~～至到]|\\bto\\b)\\s*L?';
  const range = atom + '(?:' + rangeSeparator + endNumber + '(?![A-Za-z0-9_]))*';
  const sequence = range + '(?:\\s*(?:[/／,，、;；&]|\\band\\b|和|及|与)\\s*' + range + ')*';
  const technicalTerm = /^\s*(?:[- ]?(?:cach(?:e|es|ing)|network(?:ing)?|switch(?:es|ing)?|rout(?:e|er|ing)|load[- ]balanc\w*|vpn|support|regulari[sz]ation|norm|protocol|traffic)\b|(?:层)?(?:缓存|交换|路由|网络|负载均衡|协议|技术支持|正则化))/i;

  function index(evidence) {
    return new Map((evidence?.labels || []).map(label => [label.id, label]));
  }

  function expand(group) {
    const ids = new Set();
    for (const match of group.matchAll(new RegExp(range, 'g'))) {
      const numbers = match[0].match(/\d+/g).map(Number);
      const [first, last] = numbers;
      if (numbers.length === 2 && last > first && last - first < 100) {
        for (let i = first; i <= last; i++) ids.add('L' + i);
      } else {
        // A chain of three or more named points records those points individually.
        numbers.forEach(number => ids.add('L' + number));
      }
    }
    return [...ids];
  }

  function describe(ids, labels, lang) {
    const names = [...new Set(ids.map(id => labels.get(id)?.text).filter(Boolean))];
    if (!names.length) return lang === 'en' ? 'an unverified diagram label' : '待核对的原图标注';
    const quoted = names.slice(0, 5).map(name => '“' + name + '”');
    const rest = names.length - quoted.length;
    if (rest) quoted.push(lang === 'en' ? rest + ' other diagram labels' : '另外' + rest + '处原图标注');
    return lang === 'en' ? new Intl.ListFormat('en', {type:'conjunction'}).format(quoted) : quoted.join('、');
  }

  function format(source, labels, lang) {
    if (typeof source !== 'string' || !labels.size || !/L[1-9]/.test(source)) return {text: source, ids: []};
    const groups = [], ids = new Set();
    // Use a delimiter absent from the source so diagram text cannot impersonate a reference.
    let mark = '\uE000';
    while (source.includes(mark)) mark += '\uE000';
    const marker = mark + '(\\d+)' + '\uE001';
    const tokenOnly = new RegExp('^(?:(?:OCR\\s+)?(?:labels?|IDs?)\\s*[:：]?\\s*|(?:e\\.g\\.|see(?: also)?|for example)\\s*[,，]?\\s*|(?:例如|如|参见|见|标注|标签|编号)\\s*[:：]?\\s*)*' + marker + '$', 'i');
    const pattern = new RegExp('(?<![A-Za-z0-9_])' + sequence, 'g');
    let text = source.replace(pattern, (group, offset) => {
      const before = source.slice(0, offset), after = source.slice(offset + group.length);
      if (technicalTerm.test(after) || /[A-Za-z0-9_][._-]$/.test(before) || /^[-_.][A-Za-z0-9_]/.test(after)) return group;
      const references = expand(group);
      const explicit = /(?:[（(\[]\s*|(?:labels?|IDs?|标注|证据|编号)\s*[:：]?\s*)$/i.test(before);
      if (!explicit && !references.some(id => labels.has(id))) return group;
      references.forEach(id => ids.add(id));
      return mark + (groups.push(references) - 1) + '\uE001';
    });
    if (!ids.size) return {text: source, ids: []};

    // Remove a citation-only clause, preserving other text such as "low confidence".
    text = text.replace(/\(([^()（）]*)\)|（([^()（）]*)）/g, (whole, latin, chinese) => {
      const inside = latin ?? chinese;
      if (!inside.includes(mark)) return whole;
      if (tokenOnly.test(inside.trim())) return '';
      const parts = inside.split(/(\s*[,，、;；]\s*)/);
      let remaining = '';
      for (let i = 0; i < parts.length; i += 2) {
        if (!parts[i].trim() || tokenOnly.test(parts[i].trim())) continue;
        remaining += (remaining ? parts[i - 1] : '') + parts[i];
      }
      return remaining ? whole[0] + remaining.trim() + whole.at(-1) : '';
    });
    // A neighboring quoted name already conveys the observation. Keep the name once.
    text = text.replace(new RegExp(marker + '\\s*(?=[“‘"\u0027「『])', 'g'), '');
    text = text.replace(new RegExp('((?:区域|位置|\\barea|\\bregion))\\s*' + marker, 'gi'), '$1');
    text = text.replace(new RegExp(marker, 'g'), (_, i) => describe(groups[Number(i)], labels, lang));
    text = text.replace(/[ \t]{2,}/g, ' ').replace(/[ \t]+([,.;:!?，。、；：）)])/g, '$1').trim();
    return {text: text || describe([...ids], labels, lang), ids: [...ids]};
  }

  return {index, format};
})();

if (typeof module === 'object' && module.exports) module.exports = practiceCitations;
