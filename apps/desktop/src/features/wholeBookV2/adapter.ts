import type{WholeBookAnalysisV2,WholeBookProgressV2}from"./contracts";
const obj=(x:unknown):x is Record<string,unknown>=>Boolean(x)&&typeof x==="object"&&!Array.isArray(x);
export function parseWholeBookV2(raw:unknown):WholeBookAnalysisV2{
 if(!obj(raw)||raw.schema_version!=="whole-book-analysis-v2.0")throw new Error("WHOLE_BOOK_V2_SCHEMA_INVALID");
 for(const key of ["book_metadata","type_profile","overview","story","characters","suspense","pacing","chapters","assessment","evidence_index","analysis_metadata"])if(!obj(raw[key]))throw new Error(`WHOLE_BOOK_V2_${key.toUpperCase()}_INVALID`);
 const r=raw as unknown as WholeBookAnalysisV2;
 if(!Array.isArray(r.characters.protagonist.stages)||!Array.isArray(r.pacing.points)||!Array.isArray(r.suspense.lifecycles)||!Array.isArray(r.chapters.heatmap)||!Array.isArray(r.assessment.dimensions))throw new Error("WHOLE_BOOK_V2_COLLECTION_INVALID");
 for(const [id,e] of Object.entries(r.evidence_index))if(id!==e.evidence_id||e.chapter_id===e.chapter_index)throw new Error("WHOLE_BOOK_V2_EVIDENCE_IDENTITY_INVALID");
 return r;
}
export function parseProgressV2(raw:unknown):WholeBookProgressV2{if(!obj(raw)||raw.schema_version!=="whole-book-progress-v2.0"||typeof raw.overall_percent!=="number"||typeof raw.current_action!=="string")throw new Error("WHOLE_BOOK_V2_PROGRESS_INVALID");return raw as unknown as WholeBookProgressV2}
export const sevenModules=["overview","story","characters","suspense","pacing","chapters","assessment"] as const;
