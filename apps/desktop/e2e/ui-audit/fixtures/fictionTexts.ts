/** Fictional import samples for UI audit — not real novel text. */

export const FICTION_TXT = `第一章　潮汐钟

守夜人推开潮汐钟房的门，空气里有旧纸与海盐的味道。
他摊开编年史，准备抄写今晚的航线记录。
窗外星港灯火次第亮起，像一张缓慢展开的地图。

第二章　星港夜航

玻璃鸟从桅杆滑下，停在潮汐钟的铜沿上。
抄写员说，三百年前也有人写过同样的句子。
没有人核对那些航线，但钟声依旧准时。

第三章　玻璃鸟

虚构的尾声：所有航线在晨雾中溶解，只留下一页空白。
`;

export const FICTION_SHORT = `第一章　短章

虚构短篇正文，仅用于审计截图。
`;

export function fictionFile(name: string, contents: string = FICTION_TXT): File {
  return new File([contents], name, { type: "text/plain" });
}
