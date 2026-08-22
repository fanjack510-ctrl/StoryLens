import{api}from"../../services/apiClient";import{parseProgressV2,parseWholeBookV2}from"./adapter";
export async function getWholeBookV2(runId:number){return parseWholeBookV2(await api<unknown>(`/api/v1/whole-book-runs/${runId}/v2`))}
export async function getWholeBookV2Progress(runId:number){return parseProgressV2(await api<unknown>(`/api/v1/whole-book-runs/${runId}/v2/progress`))}

/** 「读懂」的结果。单独一个口，不并进 v2：那份契约回答的是别的问题（结构、节奏、人物、悬念），
 *  而这份是主张 / 依据 / 做法 / 术语 / 存疑。共用一个口，读的人会以为它们是同一种东西。 */
export async function getComprehendResult(runId: number) {
  const { api } = await import("../../services/apiClient");
  return api<import("../../services/wholeBookFreeProductApi").ComprehendResult>(
    `/api/v1/whole-book-runs/${runId}/comprehend`,
  );
}
