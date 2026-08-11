"""Whole-Book V2 provider-independent, evidence-first result contract."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "whole-book-analysis-v2.0"
class M(BaseModel): model_config=ConfigDict(extra="forbid")
class Availability(StrEnum):
    AVAILABLE="available"; PARTIAL="partial"; UNAVAILABLE="unavailable"; LEGACY="legacy"

class EvidenceRef(M):
    evidence_id:str; snapshot_id:int; revision_hash:str; chapter_id:int; chapter_index:int=Field(ge=1); chapter_title:str; start_offset:int=Field(ge=0); end_offset:int=Field(ge=0); quote_or_excerpt:str; reason:str
    @model_validator(mode="after")
    def range_ok(self):
        if self.end_offset < self.start_offset: raise ValueError("invalid evidence range")
        return self
class TypeProfile(M):
    version:str="2.0"; primary_genre:str; secondary_genres:list[str]; narrative_drivers:list[str]; narrative_traits:list[str]; genre_confidence:float=Field(ge=0,le=1); analysis_focus:list[str]; genre_expectations:list[str]=Field(default_factory=list); evidence:list[str]
class Ranged(M):
    chapter_start:int=Field(ge=1); chapter_end:int=Field(ge=1); evidence:list[str]=Field(default_factory=list)
    @model_validator(mode="after")
    def ordered(self):
        if self.chapter_end < self.chapter_start: raise ValueError("chapter range reversed")
        return self
class TurningPoint(Ranged): title:str; description:str
class StoryStage(Ranged):
    stage_id:str; title:str; summary:str; protagonist_state:str; stage_goal:str; core_conflict:str; major_characters:list[str]; key_events:list[str]; major_choice:str; cost_paid:list[str]; gain_received:list[str]; turning_point:str; ending_state:str; next_question:str
class StorylineNode(M): chapter:int=Field(ge=1); event:str; evidence:list[str]
class Storyline(Ranged):
    storyline_id:str; name:str; type:Literal["main","subplot"]; importance:float=Field(ge=0,le=1); participants:list[str]; nodes:list[StorylineNode]; turning_points:list[str]; relationship_to_mainline:str; status:Literal["active","resolved","open","abandoned"]; resolution:str
class ChronologyEvent(M):
    event_id:str; story_order:int=Field(ge=1); narrative_order:int=Field(ge=1); chapter:int=Field(ge=1); description:str; evidence:list[str]
class StoryResult(M): version:str="2.0"; availability:Availability=Availability.AVAILABLE; structure_stages:list[StoryStage]; storylines:list[Storyline]; causal_chain:list[str]; chronology:list[ChronologyEvent]
class ArcStage(M):
    chapter:int=Field(ge=1); chapter_end:int=Field(ge=1); stage_name:str; entry_state:str; goal:str; major_events:list[str]; conflict:str; choice:str; cost_paid:list[str]; gain_received:list[str]; ability_change:str; relationship_change:str; status_change:str; internal_belief_change:str; exit_state:str; next_stage_trigger:str; evidence:list[str]
    external_conflict:str=""; internal_conflict:str=""; obstacles:list[str]=Field(default_factory=list); turning_point:str=""; identity_change:str=""
class GrowthTrackPoint(M):
    chapter:int=Field(ge=1); stage_name:str; state:str; cost_paid:list[str]; gain_received:list[str]; evidence:list[str]
class ProtagonistArc(M):
    initial_identity:str; initial_goal:str; final_goal:str; final_identity:str; stages:list[ArcStage]; external_status_track:list[GrowthTrackPoint]; ability_track:list[GrowthTrackPoint]; internal_belief_track:list[GrowthTrackPoint]; relationship_track:list[GrowthTrackPoint]
    overall_cost:list[str]=Field(default_factory=list); overall_gain:list[str]=Field(default_factory=list); core_transformation:str=""; arc_summary:str=""
class MajorCharacter(M):
    character_id:str; name:str; aliases:list[str]; importance:float=Field(ge=0,le=1); identity:str; role:str; initial_goal:str; final_goal:str; character_arc:str; key_events:list[str]; relationship_to_protagonist:str; relationship_changes:list[str]; major_choice:str; cost_paid:list[str]; gain_received:list[str]; ending:str; evidence:list[str]
class Relationship(Ranged):
    person_a:str; person_b:str; relationship_type:str; initial_state:str; evolution:list[str]; major_turning_points:list[str]; final_state:str
class CharactersResult(M): version:str="2.0"; availability:Availability=Availability.AVAILABLE; protagonist:ProtagonistArc; major_characters:list[MajorCharacter]; relationships:list[Relationship]
SuspenseType=Literal["hook","question","clue","foreshadow","misdirection","partial_reveal","reveal","twist","payoff"]
class SuspenseEvent(M): chapter:int=Field(ge=1); type:SuspenseType; description:str; information_added:str; evidence:list[str]
class SuspenseLifecycle(Ranged):
    suspense_id:str; question:str; importance:float=Field(ge=0,le=1); reader_initial_knowledge:str; truth:str; events:list[SuspenseEvent]; clues:list[str]; misdirections:list[str]; partial_reveals:list[str]; twist:str; payoff:str; storyline_effect:str; status:Literal["unresolved","partial","resolved","long_term"]
class SuspenseResult(M): version:str="2.0"; availability:Availability=Availability.AVAILABLE; lifecycles:list[SuspenseLifecycle]
class PacingPoint(M):
    chapter_start:int=Field(ge=1); chapter_end:int=Field(ge=1); plot_progress:float=Field(ge=0,le=100); tension:float=Field(ge=0,le=100); emotion:float=Field(ge=0,le=100); reading_drive:float=Field(ge=0,le=100); hook_density:float=Field(ge=0,le=100); pace_speed:float=Field(ge=0,le=100); dominant_events:list[str]; reason:str; story_consequence:str
    chapter_id:int|None=None; chapter_index:int|None=Field(default=None,ge=1); chapter_title:str|None=None
class PacingMarker(M):
    chapter:int=Field(ge=1); title:str; event:str; importance:float=Field(ge=0,le=1); effect_on_pacing:str; evidence:list[str]
    marker_type:Literal["story_stage","major_event","turning_point","climax"]="turning_point"
class PacingRegion(Ranged): type:Literal["fatigue","climax","acceleration","slow_build","high_pressure","transition"]; reason:str; related_events:list[str]; diagnosis:str
class PacingResult(M): version:str="2.0"; availability:Availability=Availability.AVAILABLE; points:list[PacingPoint]; event_markers:list[PacingMarker]; pacing_regions:list[PacingRegion]
class ChapterFunction(M): chapter_id:int; chapter_index:int=Field(ge=1); title:str; primary_function:str; secondary_functions:list[str]; summary:str; importance:float=Field(ge=0,le=1); evidence:list[str]
class HeatmapBin(M): chapter_start:int; chapter_end:int; mainline_progress:float; character_development:float; conflict:float; suspense:float; foreshadow:float; payoff:float; transition:float
class ChaptersResult(M): version:str="2.0"; availability:Availability=Availability.AVAILABLE; functions:list[ChapterFunction]; heatmap:list[HeatmapBin]; aggregation_size:int=50
class OverviewResult(M):
    version:str="2.0"; one_sentence_story:str; full_summary:str; protagonist:str; initial_state:str; final_state:str; core_goal:str; goal_evolution:list[str]; core_conflict:str; conflict_evolution:list[str]; core_question:str; major_storylines:list[str]; major_turning_points:list[TurningPoint]; major_suspense:list[str]; final_climax:str; ending_resolution:list[str]; ending_open_questions:list[str]; story_skeleton:list[str]; evidence:list[str]
class AssessmentDimension(M): dimension:Literal["story_structure","protagonist_growth","character_relationships","suspense_payoff","pacing","chapter_efficiency"]; rating:Literal["A","A-","B+","B","B-","C","D"]; conclusion:str; supporting_metrics:list[str]; evidence:list[str]
class Strength(Ranged): title:str; why_good:str
class AssessmentIssue(Ranged):
    issue_id:str; priority:Literal["P0","P1","P2"]; category:str; symptom:str; root_cause:str; reader_impact:str; supporting_metrics:list[str]; possible_direction:str
    dimension:str=""; problem:str=""; cause:str=""; recommended_direction:str=""
class RevisionPriority(M): priority:Literal["first","second","third"]; chapter_ranges:list[list[int]]; direction:str; preserve:list[str]
class AssessmentResult(M):
    version:str="2.0"; overall_summary:str; dimensions:list[AssessmentDimension]; strengths:list[Strength]; issues:list[AssessmentIssue]; issue_map:list[AssessmentIssue]; revision_priorities:list[RevisionPriority]; preserve_list:list[str]
    overall_assessment:str=""
class BookMetadata(M): book_id:int; snapshot_id:int; revision_hash:str; title:str; chapter_count:int=Field(ge=1); character_count:int=Field(ge=0)
RESULT_ORIGINS=Literal[
    "real_provider",
    "deterministic_local_merge",
    "deterministic_test",
    "fixture",
    "mock",
    "legacy_migration",
    "unknown",
]
class AnalysisMetadata(M):
    run_id:int
    schema_version:str=SCHEMA_VERSION
    engine_version:str
    provider_name:str
    model_name:str
    generated_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    module_availability:dict[str,Availability]
    provider_calls_completed:int=0
    real_provider_calls:int=0
    # CHG-080: formal product must distinguish real provider vs scaffold/local merge.
    result_origin:RESULT_ORIGINS="unknown"
    pipeline_version:str="whole_book_v2_hierarchical/2.1.0"
    source_revision:str=""
class WholeBookAnalysisV2(M):
    schema_version:str=SCHEMA_VERSION; book_metadata:BookMetadata; type_profile:TypeProfile; overview:OverviewResult; story:StoryResult; characters:CharactersResult; suspense:SuspenseResult; pacing:PacingResult; chapters:ChaptersResult; assessment:AssessmentResult; evidence_index:dict[str,EvidenceRef]; analysis_metadata:AnalysisMetadata

# Provider synthesis is deliberately split.  These DTOs are the validation and
# persistence boundary; the monolithic result is only assembled locally.
class OverviewTypeSynthesisUnit(M): type_profile:TypeProfile; overview:OverviewResult
class StorySynthesisUnit(M): story:StoryResult
class CharactersSynthesisUnit(M): characters:CharactersResult
class SuspenseSynthesisUnit(M): suspense:SuspenseResult
class PacingSynthesisUnit(M): pacing:PacingResult; chapters:ChaptersResult
class AssessmentSynthesisUnit(M): assessment:AssessmentResult

# CHG-086: `pacing` used to demand PacingResult + all N ChapterFunction rows in a
# single bounded response. For a 542-chapter book that can never fit one
# max_output_tokens window, so the unit is split: the provider returns pacing
# curves here, and chapter functions arrive as bounded batches (below).
class PacingCoreSynthesisUnit(M): pacing:PacingResult
class ChapterFunctionBatchUnit(M): functions:list[ChapterFunction]
class ProgressV2(M):
    schema_version:str="whole-book-progress-v2.0"; overall_percent:float=Field(ge=0,le=100); current_stage:str; stage_percent:float=Field(ge=0,le=100); current_window:int; total_windows:int; current_chapter:int; total_chapters:int; provider_calls_completed:int; provider_calls_estimated:int; successful_calls:int; failed_calls:int; retry_calls:int; repair_calls:int; elapsed_seconds:int; estimated_remaining_seconds:int; estimated_cost:float; estimated_actual_cost:float; provider:str; model:str; last_completed_action:str; current_action:str; last_activity_at:datetime
V2_STAGES=[
    "prepare_source","parse_chapters","plan_windows","extract_windows",
    "consolidate_story","consolidate_relationships","build_protagonist_arc",
    "consolidate_characters","merge_suspense","compute_pacing","chapter_functions",
    "generate_overview","generate_assessment","evidence_validation","materialize_report","complete",
]
# Human-readable progress labels for UI (aligned with product stages).
V2_STAGE_LABELS={
    "prepare_source":"准备小说","parse_chapters":"解析章节","plan_windows":"规划分析窗口",
    "extract_windows":"抽取窗口","consolidate_story":"整理故事结构",
    "consolidate_relationships":"整理人物关系","build_protagonist_arc":"构建主角历程",
    "consolidate_characters":"整理人物","merge_suspense":"合并悬念","compute_pacing":"计算章节节奏",
    "chapter_functions":"整理章节功能","generate_overview":"生成全书总结",
    "generate_assessment":"生成综合诊断","evidence_validation":"校验证据链",
    "materialize_report":"物化报告","complete":"完成",
}
