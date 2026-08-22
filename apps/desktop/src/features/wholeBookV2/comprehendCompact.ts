/** 把「读懂」的产出收到能读完的长度。
 *
 *  第一版实测：48,168 字，是原书的 10.5%——**跟正文差不多长，就等于没摘要**。读者要它，恰恰
 *  是因为没时间读原文。
 *
 *  量下来长度花在哪：
 *
 *      依据  15,435 字 (32%)  257 条   ← 最大的一块
 *      术语  10,324 字 (21%)  446 条
 *      主张  10,106 字 (21%)  216 条
 *      做法   6,097 字 (13%)  114 条
 *      存疑   3,966 字 ( 8%)   76 条
 *
 *  所以按「这一条为谁服务」来收，而不是一刀切按比例砍：
 *
 *  **依据只留引了谁。** 「Palmer & Schloss (2010) 的色彩偏好实验」里，读者真正用得上的是
 *  `Palmer & Schloss 2010`——那是他翻回原文的抓手；后面那句描述是原文里就有的东西，摘要
 *  重述一遍只是变长。压缩之后**可核对性一点没丢，字数掉了八成**。
 *
 *  **术语封顶。** 446 条摊到 76 节，每节六个上下已经够用；再多是词表，不是摘要。
 *
 *  **存疑收起来。** 它是模型的推测，不是书里的东西——有价值，但不该跟书的主张抢同一屏。
 *
 *  一条都不删数据，只是默认不摊开：删掉的东西读者不知道自己没看到，收起来的他知道。
 */

export const TERMS_SHOWN = 6;

/** 从一段依据里抠出「谁 + 哪一年」。 */
const CITE = /([A-Z][\w.'’-]*(?:\s*(?:&|and|与|、)\s*[A-Z][\w.'’-]*)*(?:\s+et\s+al\.?)?)\s*[（(]?\s*((?:19|20)\d{2}[a-z]?)/g;
/** 中文著作常写成「张三（2019）」或「《某书》」。 */
const CN_CITE = /([一-鿿]{2,6})\s*[（(]\s*((?:19|20)\d{2})/g;

/**
 * 把一节的依据压成一行「引了谁」。
 *
 * 抠不出任何引用时返回第一条原文并截断——原文写的是「基于人眼视锥细胞的生理机制」这类没有
 * 出处的依据，那也是依据，不能因为不带年份就当它不存在。
 */
export function citationsOf(evidence: string[] | undefined, limit = 6): string[] {
  if (!evidence?.length) return [];
  const keys: string[] = [];
  const seen = new Set<string>();
  for (const line of evidence) {
    for (const re of [CITE, CN_CITE]) {
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(line)) !== null) {
        const key = `${m[1].replace(/\s+/g, " ").trim()} ${m[2]}`;
        if (!seen.has(key)) {
          seen.add(key);
          keys.push(key);
        }
      }
    }
  }
  if (keys.length) return keys.slice(0, limit);
  const first = (evidence[0] || "").trim();
  return first ? [first.length > 40 ? `${first.slice(0, 39)}…` : first] : [];
}

/** 一节收完之后长什么样。`extra` 是收起来的部分——存在，但不摊开。 */
export type CompactSection = {
  claims: string[];
  actions: string[];
  citations: string[];
  terms: string[];
  hiddenTerms: number;
  openQuestions: string[];
  fullEvidence: string[];
};

export function compactSection(section: {
  claims?: string[];
  evidence?: string[];
  actions?: string[];
  terms?: string[];
  open_questions?: string[];
}): CompactSection {
  const terms = section.terms ?? [];
  return {
    claims: section.claims ?? [],
    actions: section.actions ?? [],
    citations: citationsOf(section.evidence),
    terms: terms.slice(0, TERMS_SHOWN),
    hiddenTerms: Math.max(0, terms.length - TERMS_SHOWN),
    openQuestions: section.open_questions ?? [],
    fullEvidence: section.evidence ?? [],
  };
}
