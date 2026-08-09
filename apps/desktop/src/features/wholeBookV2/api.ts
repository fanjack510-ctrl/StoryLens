import{api}from"../../services/apiClient";import{parseProgressV2,parseWholeBookV2}from"./adapter";
export async function getWholeBookV2(runId:number){return parseWholeBookV2(await api<unknown>(`/api/v1/whole-book-runs/${runId}/v2`))}
export async function getWholeBookV2Progress(runId:number){return parseProgressV2(await api<unknown>(`/api/v1/whole-book-runs/${runId}/v2/progress`))}
