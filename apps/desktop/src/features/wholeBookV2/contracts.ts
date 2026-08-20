export type Availability="available"|"partial"|"unavailable"|"legacy";
export type EvidenceRef={evidence_id:string;snapshot_id:number;revision_hash:string;chapter_id:number;chapter_index:number;chapter_title:string;start_offset:number;end_offset:number;quote_or_excerpt:string;reason:string};
export type ArcStage={chapter:number;chapter_end:number;stage_name:string;entry_state:string;goal:string;major_events:string[];conflict:string;choice:string;cost_paid:string[];gain_received:string[];ability_change:string;relationship_change:string;status_change:string;internal_belief_change:string;exit_state:string;next_stage_trigger:string;evidence:string[]};
export type GrowthPoint={chapter:number;stage_name:string;state:string;cost_paid:string[];gain_received:string[];evidence:string[]};
/** What "up" means on the protagonist-journey chart. Chosen by the engine from the book's
 *  profile; the client renders whatever it is told and never picks the axis itself. */
export type JourneyAxis="cognition"|"ladder"|"screen_time"|"none";
export type JourneyPoint={chapter:number;value:number;label:string;kind:string;who:string;note:string;load_bearing:boolean;evidence:string[]};
export type ScreenTimeBand={name:string;share:number[];first_chapter:number;last_chapter:number;chapters:number;total:number};
export type LedgerMeeting={chapter:number;name:string;relation:string};
export type LedgerEvent={chapter:number;text:string};
/** One stage's 遇见谁 / 做了什么 / 得到 / 失去. The `*_total` counts are the full tally; the
 *  arrays are what fits on screen. */
export type StageLedger={stage_name:string;chapter_start:number;chapter_end:number;met:LedgerMeeting[];met_total:number;did:LedgerEvent[];did_total:number;gained:string[];gained_total:number;lost:string[];lost_total:number};
export type JourneyResult={availability:Availability;axis:JourneyAxis;axis_label:string;lead:string;ticks:string[];points:JourneyPoint[];bands:ScreenTimeBand[];bins:number;caveat:string;ledger?:StageLedger[]};

export type WholeBookAnalysisV2={
 schema_version:"whole-book-analysis-v2.0";
 book_metadata:{book_id:number;snapshot_id:number;revision_hash:string;title:string;chapter_count:number;character_count:number};
 type_profile:{primary_genre:string;secondary_genres:string[];narrative_drivers:string[];narrative_traits:string[];genre_confidence:number;analysis_focus:string[];genre_expectations?:string[];evidence:string[]};
 overview:{one_sentence_story:string;full_summary:string;protagonist:string;initial_state:string;final_state:string;core_goal:string;goal_evolution:string[];core_conflict:string;conflict_evolution:string[];core_question:string;major_storylines:string[];major_turning_points:Array<{chapter_start:number;chapter_end:number;title:string;description:string;evidence:string[]}>;major_suspense:string[];final_climax:string;ending_resolution:string[];ending_open_questions:string[];story_skeleton:string[];evidence:string[]};
 story:{availability:Availability;structure_stages:Array<{stage_id:string;chapter_start:number;chapter_end:number;title:string;summary:string;stage_goal:string;core_conflict:string;major_choice:string;cost_paid:string[];gain_received:string[];evidence:string[];
  /* Sent by the engine since the stage interpreter landed; declared optional so documents
     stored before it keep loading. Verified present on run 18 of 《系统豪横》. */
  protagonist_state?:string;turning_point?:string;ending_state?:string;next_question?:string;key_events?:string[];major_characters?:string[]}>;storylines:Array<{storyline_id:string;name:string;type:"main"|"subplot";chapter_start:number;chapter_end:number;status:string;resolution?:string;relationship_to_mainline?:string;evidence:string[];nodes?:Array<{chapter:number;event:string;evidence?:string[]}>}>;causal_chain:string[];chronology:Array<{event_id:string;story_order:number;narrative_order:number;chapter:number;description:string;evidence:string[]}>};
 characters:{availability:Availability;protagonist:{initial_identity:string;initial_goal:string;final_goal:string;final_identity:string;stages:ArcStage[];external_status_track:GrowthPoint[];ability_track:GrowthPoint[];internal_belief_track:GrowthPoint[];relationship_track:GrowthPoint[];overall_cost?:string[];overall_gain?:string[];core_transformation?:string;arc_summary?:string};major_characters:Array<{character_id:string;name:string;role:string;character_arc:string;identity?:string;initial_goal?:string;final_goal?:string;key_events?:string[];relationship_to_protagonist?:string;relationship_changes?:string[];major_choice?:string;cost_paid?:string[];gain_received?:string[];ending?:string;evidence:string[]}>;relationships:Array<{person_a:string;person_b:string;relationship_type:string;evolution?:string[];final_state?:string;chapter_start:number;chapter_end:number;evidence:string[]}>};
 suspense:{availability:Availability;lifecycles:Array<{suspense_id:string;question:string;chapter_start:number;chapter_end:number;status:string;events:Array<{chapter:number;type:string;description:string}>;payoff:string;evidence:string[]}>};
 pacing:{availability:Availability;points:Array<{chapter_start:number;chapter_end:number;chapter_id?:number|null;chapter_index?:number|null;chapter_title?:string|null;plot_progress:number;emotion:number;hook_density:number;tension?:number|null;reading_drive?:number|null;pace_speed?:number|null;dominant_events:string[];reason:string;story_consequence:string}>;event_markers:Array<{chapter:number;title:string;event:string;effect_on_pacing:string;evidence:string[];marker_type?:string}>;pacing_regions:Array<{chapter_start:number;chapter_end:number;type:string;reason:string;diagnosis:string}>};
 chapters:{availability:Availability;aggregation_size:number;functions:Array<{chapter_id:number;chapter_index:number;title:string;primary_function:string;secondary_functions:string[];summary:string;importance:number;evidence:string[]}>;heatmap:Array<{chapter_start:number;chapter_end:number;mainline_progress:number;character_development:number;conflict:number;suspense:number;transition:number;foreshadow?:number|null;payoff?:number|null}>};
 assessment:{overall_summary:string;overall_assessment?:string;dimensions:Array<{dimension:string;rating:string;conclusion:string;supporting_metrics:string[];evidence:string[]}>;strengths:Array<{title:string;why_good:string;chapter_start:number;chapter_end:number;evidence:string[]}>;issues:Array<{issue_id:string;priority:"P0"|"P1"|"P2";category:string;chapter_start:number;chapter_end:number;symptom:string;root_cause:string;reader_impact:string;supporting_metrics:string[];evidence:string[];possible_direction:string;dimension?:string;problem?:string;cause?:string;recommended_direction?:string}>;issue_map:unknown[];revision_priorities:unknown[];preserve_list:string[]};
 /** 拆文 only. A diagnostic run leaves this absent; a 拆文 run fills every field and leaves
  *  `overview` and `assessment` mostly empty, because those are the diagnostic reading's
  *  sections and 拆文 never produces them. */
 story_breakdown?:{
  version?:string;
  availability?:Availability;
  four_beats:Array<{beat:string;title:string;summary:string;chapter_start:number;chapter_end:number;evidence:string[]}>;
  standout_moments:Array<{rank:number;title:string;quote:string;why_it_lands:string;chapter:number;evidence:string[]}>;
  moment_count_rationale?:string;
  chapter_hooks:Array<{chapter:number;question:string;evidence:string[]}>;
  reusable_techniques:Array<{name:string;what_it_is:string;why_it_works:string;transfers_to:string}>;
  supporting_cast:Array<{name:string;function:string;stays_in_lane?:string|null;evidence:string[]}>;
  cast_note?:string;
 };
 evidence_index:Record<string,EvidenceRef>;
 /** Optional: absent on every document produced before the journey section existed. */
 journey?:JourneyResult;
 analysis_metadata:{run_id:number;provider_name:string;model_name:string;module_availability:Record<string,Availability>;real_provider_calls:number;result_origin?:V2ResultOrigin;pipeline_version?:string};
};
export type V2ResultOrigin="real_provider"|"deterministic_local_merge"|"deterministic_test"|"fixture"|"mock"|"legacy_migration"|"unknown";
export type WholeBookV2ProductFlags={is_real_provider_result:boolean;needs_reanalysis:boolean;scaffold_detected:boolean};
export type WholeBookProgressV2={schema_version:"whole-book-progress-v2.0";overall_percent:number;current_stage:string;stage_percent:number;current_window:number;total_windows:number;current_chapter:number;total_chapters:number;provider_calls_completed:number;provider_calls_estimated:number;successful_calls:number;failed_calls:number;retry_calls:number;repair_calls:number;elapsed_seconds:number;estimated_remaining_seconds:number;estimated_cost:number;estimated_actual_cost:number;provider:string;model:string;last_completed_action:string;current_action:string;last_activity_at:string};
export const V2_PROGRESS_STAGES=[
 "prepare_source","parse_chapters","plan_windows","extract_windows",
 "consolidate_story","consolidate_relationships","build_protagonist_arc",
 "consolidate_characters","merge_suspense","compute_pacing","chapter_functions",
 "generate_overview","generate_assessment","evidence_validation","materialize_report","complete",
] as const;
export const V2_PROGRESS_LABELS:Record<string,string>={
 prepare_source:"准备小说",parse_chapters:"解析章节",plan_windows:"规划分析窗口",
 extract_windows:"抽取窗口",consolidate_story:"整理故事结构",
 consolidate_relationships:"整理人物关系",build_protagonist_arc:"构建主角历程",
 consolidate_characters:"整理人物",merge_suspense:"合并悬念",compute_pacing:"计算章节节奏",
 chapter_functions:"整理章节功能",generate_overview:"生成全书总结",
 generate_assessment:"生成综合诊断",evidence_validation:"校验证据链",
 materialize_report:"物化报告",complete:"完成",
};
