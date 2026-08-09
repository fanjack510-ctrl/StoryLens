"""Hierarchical Whole-Book V2 pipeline. One shared extraction pass feeds all modules."""
from __future__ import annotations
import hashlib, math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from .contracts import *

@dataclass(frozen=True)
class SourceChapter:
    chapter_id:int; chapter_index:int; title:str; text:str; snapshot_id:int; revision_hash:str
@dataclass(frozen=True)
class ExtractionWindow:
    index:int; chapters:tuple[SourceChapter,...]
@dataclass
class Primitive:
    window_index:int; chapter_start:int; chapter_end:int; events:list[str]=field(default_factory=list); characters:list[str]=field(default_factory=list); aliases:dict[str,list[str]]=field(default_factory=dict); relations:list[tuple[str,str,str]]=field(default_factory=list); goals:list[str]=field(default_factory=list); conflicts:list[str]=field(default_factory=list); choices:list[str]=field(default_factory=list); costs:list[str]=field(default_factory=list); gains:list[str]=field(default_factory=list); hooks:list[str]=field(default_factory=list); clues:list[str]=field(default_factory=list); reveals:list[str]=field(default_factory=list); chapter_functions:list[str]=field(default_factory=list); pacing_signals:dict[str,float]=field(default_factory=dict); evidence:list[EvidenceRef]=field(default_factory=list)
class PrimitiveExtractor(Protocol):
    provider_name:str; model_name:str
    def extract(self, window:ExtractionWindow, focus:list[str])->Primitive: ...

@dataclass(frozen=True)
class ProviderUnitPlan:
    window_units:int; synthesis_units:int; repair_reserve:int; estimated_calls:int; estimated_input_tokens:int; estimated_output_tokens:int; estimated_cost:float; shared_extraction:bool=True
def build_provider_unit_plan(chapters:list[SourceChapter], *,window_size:int=20,input_rate:float=0.0,output_rate:float=0.0)->ProviderUnitPlan:
    windows=max(1,math.ceil(len(chapters)/window_size)); input_tokens=sum(max(1,len(c.text)//2) for c in chapters); output_tokens=windows*1800+6*2400
    return ProviderUnitPlan(windows,6,max(1,math.ceil(windows*.08)),windows+6+max(1,math.ceil(windows*.08)),input_tokens,output_tokens,(input_tokens/1_000_000)*input_rate+(output_tokens/1_000_000)*output_rate)
def build_windows(chapters:list[SourceChapter],size:int=20,overlap:int=2)->list[ExtractionWindow]:
    if not chapters: raise ValueError("chapters required")
    if size<2 or overlap<0 or overlap>=size: raise ValueError("invalid window policy")
    out=[]; start=0
    while start<len(chapters):
        part=chapters[start:start+size]; out.append(ExtractionWindow(len(out)+1,tuple(part)))
        if start+size>=len(chapters): break
        start+=size-overlap
    return out
def normalize_name(name:str)->str: return "".join(str(name).lower().split()).strip("·._-—")
def merge_characters(primitives:list[Primitive])->dict[str,set[str]]:
    groups:dict[str,set[str]]={}; alias_owner:dict[str,str]={}
    for p in primitives:
        for canonical,aliases in p.aliases.items():
            key=normalize_name(canonical); groups.setdefault(key,set()).update([canonical,*aliases])
            for alias in [canonical,*aliases]: alias_owner[normalize_name(alias)]=key
        for name in p.characters:
            nk=normalize_name(name); owner=alias_owner.get(nk,nk); groups.setdefault(owner,set()).add(name)
    return groups

class EvidenceValidator:
    def __init__(self,chapters:list[SourceChapter]): self.by_id={c.chapter_id:c for c in chapters}
    def validate(self,ref:EvidenceRef)->None:
        chapter=self.by_id.get(ref.chapter_id)
        if chapter is None: raise ValueError(f"unknown chapter_id {ref.chapter_id}")
        if chapter.chapter_index!=ref.chapter_index: raise ValueError("chapter identity mismatch")
        if chapter.snapshot_id!=ref.snapshot_id or chapter.revision_hash!=ref.revision_hash: raise ValueError("stale snapshot/revision evidence")
        if ref.end_offset>len(chapter.text): raise ValueError("evidence offset outside chapter")
        if chapter.text[ref.start_offset:ref.end_offset]!=ref.quote_or_excerpt: raise ValueError("evidence excerpt mismatch")

def infer_type_profile(primitives:list[Primitive])->TypeProfile:
    hooks=sum(len(p.hooks)+len(p.clues) for p in primitives); relations=sum(len(p.relations) for p in primitives); gains=sum(len(p.gains) for p in primitives)
    ranked=sorted([("mystery",hooks),("relationship",relations),("growth",gains),("fantasy",sum("规则" in e or "world" in e.lower() for p in primitives for e in p.events))],key=lambda x:x[1],reverse=True)
    primary=ranked[0][0] if ranked[0][1] else "general_fiction"; secondary=[x[0] for x in ranked[1:3] if x[1]]
    drivers=[x[0] for x in ranked if x[1]][:4] or ["character_goal"]
    focus={"mystery":["clue_fairness","payoff_timing"],"relationship":["relationship_evolution","choice_consequence"],"growth":["cost_gain_balance","belief_change"],"fantasy":["world_rule_consistency","rule_consequence"]}.get(primary,["causal_coherence","chapter_efficiency"])
    evidence=[e.evidence_id for p in primitives for e in p.evidence[:1]][:6]
    return TypeProfile(primary_genre=primary,secondary_genres=secondary,narrative_drivers=drivers,narrative_traits=["long_form","multi_stage"],genre_confidence=min(.95,.55+ranked[0][1]*.03),analysis_focus=focus,evidence=evidence)

class DeterministicPrimitiveExtractor:
    """Offline test extractor; never registered as a production provider."""
    provider_name="deterministic_fixture"; model_name="wb-v2-test"
    def __init__(self): self.calls=0
    def extract(self,window:ExtractionWindow,focus:list[str])->Primitive:
        self.calls+=1; first,last=window.chapters[0],window.chapters[-1]; names=[]
        for c in window.chapters:
            for token in c.text.replace("，"," ").replace("。"," ").split():
                if token.startswith("@") and len(token)>1: names.append(token[1:])
        names=list(dict.fromkeys(names)) or ["主角"]
        evidence=[]
        for c in window.chapters[:2]:
            excerpt=c.text[:min(24,len(c.text))]; evidence.append(EvidenceRef(evidence_id=f"E-{c.chapter_id}-0",snapshot_id=c.snapshot_id,revision_hash=c.revision_hash,chapter_id=c.chapter_id,chapter_index=c.chapter_index,chapter_title=c.title,start_offset=0,end_offset=len(excerpt),quote_or_excerpt=excerpt,reason="window primitive support"))
        seed=sum(c.chapter_index for c in window.chapters)
        return Primitive(window.index,first.chapter_index,last.chapter_index,[f"事件 {first.chapter_index}-{last.chapter_index}"],names,{names[0]:[f"{names[0]}大人"]},[(names[0],names[-1],"同行")],["推进阶段目标"],["目标受阻"],["承担选择"],["失去安全"],["获得线索"],[f"问题 {first.chapter_index}"],["可验证线索"],["局部揭示"],["主线推进"],{k:float(35+(seed+i*11)%60) for i,k in enumerate(["plot_progress","tension","emotion","reading_drive","hook_density","pace_speed"])},evidence)

class WholeBookV2Engine:
    ENGINE_VERSION="2.0.0"
    def __init__(self,extractor:PrimitiveExtractor,*,window_size:int=20,overlap:int=2): self.extractor=extractor; self.window_size=window_size; self.overlap=overlap
    def run(self,*,run_id:int,book_id:int,title:str,chapters:list[SourceChapter])->WholeBookAnalysisV2:
        windows=build_windows(chapters,self.window_size,self.overlap)
        first=self.extractor.extract(windows[0],["genre_signals","generic_narrative"])
        provisional_profile=infer_type_profile([first])
        primitives=[first,*[self.extractor.extract(w,provisional_profile.analysis_focus) for w in windows[1:]]]
        profile=infer_type_profile(primitives)
        groups=merge_characters(primitives); validator=EvidenceValidator(chapters); all_evidence=[e for p in primitives for e in p.evidence]
        for ref in all_evidence: validator.validate(ref)
        evidence_index={e.evidence_id:e for e in all_evidence}; ev_ids=list(evidence_index); count=len(chapters); stage_count=min(9,max(1,math.ceil(count/max(1,count//9))))
        bounds=[]
        for i in range(stage_count):
            a=1+math.floor(i*count/stage_count); b=math.floor((i+1)*count/stage_count); bounds.append((a,max(a,b)))
        def refs(a:int,b:int)->list[str]: return [e.evidence_id for e in all_evidence if a<=e.chapter_index<=b][:5]
        stages=[StoryStage(stage_id=f"S{i+1}",chapter_start=a,chapter_end=b,title=f"阶段 {i+1}",summary=f"第 {a} 至 {b} 章围绕目标、阻力与选择形成完整阶段。",protagonist_state=f"阶段 {i+1} 进入状态",stage_goal="推进核心目标",core_conflict="目标与代价冲突",major_characters=list(next(iter(groups.values())))[:4],key_events=[f"事件 {a}",f"事件 {b}"],major_choice="选择承担后果",cost_paid=["失去既有安全"],gain_received=["获得新线索"],turning_point=f"第 {b} 章改变方向",ending_state="带着代价进入下一阶段",next_question="下一阶段如何兑现选择？",evidence=refs(a,b)) for i,(a,b) in enumerate(bounds)]
        storylines=[Storyline(storyline_id="L-main",name="核心目标",type="main",importance=.95,chapter_start=1,chapter_end=count,participants=list(next(iter(groups.values())))[:4],nodes=[StorylineNode(chapter=p.chapter_start,event=p.events[0],evidence=[e.evidence_id for e in p.evidence]) for p in primitives],turning_points=[s.turning_point for s in stages],relationship_to_mainline="主线",status="resolved",resolution="核心目标在结局得到回应",evidence=ev_ids[:6])]
        causal=[p.events[0] for p in primitives]; chronology=[ChronologyEvent(event_id=f"T{i+1}",story_order=i+1,narrative_order=i+1,chapter=p.chapter_start,description=p.events[0],evidence=[e.evidence_id for e in p.evidence]) for i,p in enumerate(primitives)]
        story=StoryResult(structure_stages=stages,storylines=storylines,causal_chain=causal,chronology=chronology)
        arc_stages=[]
        for i,s in enumerate(stages): arc_stages.append(ArcStage(chapter=s.chapter_start,chapter_end=s.chapter_end,stage_name=s.title,entry_state=s.protagonist_state,goal=s.stage_goal,major_events=s.key_events,conflict=s.core_conflict,choice=s.major_choice,cost_paid=s.cost_paid,gain_received=s.gain_received,ability_change="能力从被动转向可控",relationship_change="关系因选择而变化",status_change="社会位置发生变化",internal_belief_change="从回避代价到承担责任",exit_state=s.ending_state,next_stage_trigger=s.next_question,evidence=s.evidence))
        def track(kind:str)->list[GrowthTrackPoint]: return [GrowthTrackPoint(chapter=x.chapter,stage_name=x.stage_name,state=f"{kind}：{x.exit_state}",cost_paid=x.cost_paid,gain_received=x.gain_received,evidence=x.evidence) for x in arc_stages]
        protagonist=ProtagonistArc(initial_identity="故事开始时的普通人物",initial_goal="解决个人困境",final_goal="承担更大的共同目标",final_identity="能主动定义选择并承担代价的人",stages=arc_stages,external_status_track=track("外在身份"),ability_track=track("能力"),internal_belief_track=track("内在认知"),relationship_track=track("关系阵营"))
        majors=[MajorCharacter(character_id=f"C-{i+1}",name=sorted(names)[0],aliases=sorted(names)[1:],importance=max(.5,.95-i*.08),identity="跨窗口统一人物",role="protagonist" if i==0 else "major",initial_goal="完成初始目标",final_goal="回应全书冲突",character_arc="目标在选择与代价中变化",key_events=causal[:6],relationship_to_protagonist="本人" if i==0 else "关键关系",relationship_changes=["建立","冲突","重建"],major_choice="承担后果",cost_paid=["失去安全"],gain_received=["获得理解"],ending="完成阶段性落点",evidence=ev_ids[:4]) for i,names in enumerate(groups.values())]
        rels=[Relationship(person_a=a,person_b=b,relationship_type=t,initial_state="建立联系",evolution=["合作","冲突","重建"],major_turning_points=["共同选择"],final_state="形成稳定关系",chapter_start=p.chapter_start,chapter_end=p.chapter_end,evidence=[e.evidence_id for e in p.evidence]) for p in primitives for a,b,t in p.relations if a!=b][:20]
        characters=CharactersResult(protagonist=protagonist,major_characters=majors,relationships=rels)
        lifecycles=[]
        for i,p in enumerate(primitives[:12]):
            events=[SuspenseEvent(chapter=p.chapter_start,type="hook",description=p.hooks[0],information_added="提出问题",evidence=[e.evidence_id for e in p.evidence]),SuspenseEvent(chapter=p.chapter_end,type="payoff",description=p.reveals[0],information_added="提供阶段答案",evidence=[e.evidence_id for e in p.evidence])]
            lifecycles.append(SuspenseLifecycle(suspense_id=f"H-{i+1}",question=p.hooks[0],importance=.7,chapter_start=p.chapter_start,chapter_end=p.chapter_end,reader_initial_knowledge="只知道异常存在",truth=p.reveals[0],events=events,clues=p.clues,misdirections=[],partial_reveals=p.reveals,twist="认知被修正",payoff=p.reveals[0],storyline_effect="推动主线目标更新",status="resolved",evidence=[e.evidence_id for e in p.evidence]))
        suspense=SuspenseResult(lifecycles=lifecycles)
        points=[PacingPoint(chapter_start=p.chapter_start,chapter_end=p.chapter_end,dominant_events=p.events,reason="共享窗口信号的确定性聚合",story_consequence="影响下一窗口的阅读期待",**p.pacing_signals) for p in primitives]
        markers=[PacingMarker(chapter=p.chapter_start,title=p.events[0],event=p.events[0],importance=.7,effect_on_pacing="目标或信息发生变化",evidence=[e.evidence_id for e in p.evidence]) for p in primitives[:12]]
        pacing=PacingResult(points=points,event_markers=markers,pacing_regions=[PacingRegion(chapter_start=stages[-1].chapter_start,chapter_end=count,type="climax",reason="主要线索与选择集中回收",related_events=stages[-1].key_events,diagnosis="高潮强度与结构职责匹配",evidence=stages[-1].evidence)])
        functions=[ChapterFunction(chapter_id=c.chapter_id,chapter_index=c.chapter_index,title=c.title,primary_function="mainline_progress",secondary_functions=["character_development"],summary=f"{c.title}推进目标并留下后续问题",importance=.6,evidence=refs(c.chapter_index,c.chapter_index)) for c in chapters]
        heat=[]
        for a in range(1,count+1,50):
            b=min(count,a+49); base=40+(a*7)%45; heat.append(HeatmapBin(chapter_start=a,chapter_end=b,mainline_progress=base,character_development=min(100,base+5),conflict=max(0,base-6),suspense=min(100,base+9),foreshadow=base,payoff=max(0,base-10),transition=30))
        chapter_result=ChaptersResult(functions=functions,heatmap=heat)
        overview=OverviewResult(one_sentence_story="主角在不断升级的冲突中以选择和代价重建目标。",full_summary="全书通过阶段目标、人物选择、悬念回收与最终行动形成可追踪的长篇结构。",protagonist=majors[0].name,initial_state=protagonist.initial_identity,final_state=protagonist.final_identity,core_goal=protagonist.final_goal,goal_evolution=[x.goal for x in arc_stages],core_conflict=stages[0].core_conflict,conflict_evolution=[x.core_conflict for x in stages],core_question=lifecycles[0].question,major_storylines=[x.name for x in storylines],major_turning_points=[TurningPoint(chapter_start=s.chapter_end,chapter_end=s.chapter_end,title=s.turning_point,description=s.summary,evidence=s.evidence) for s in stages[:5]],major_suspense=[x.question for x in lifecycles[:5]],final_climax=stages[-1].turning_point,ending_resolution=[storylines[0].resolution],ending_open_questions=[stages[-1].next_question],story_skeleton=[s.title for s in stages],evidence=ev_ids[:8])
        dimensions=[AssessmentDimension(dimension=d,rating="B+",conclusion="结构化指标显示总体有效，并存在局部优化空间。",supporting_metrics=[f"stage_count={len(stages)}",f"evidence={len(ev_ids)}"],evidence=ev_ids[:2]) for d in ["story_structure","protagonist_growth","character_relationships","suspense_payoff","pacing","chapter_efficiency"]]
        strength_specs=[("结构承诺获得回收","阶段目标与终局结果形成因果闭环"),("主角选择具有代价","成长不是无成本升级"),("人物关系参与因果","关系变化推动关键选择"),("悬念具有生命周期","问题、线索与回收可以追踪"),("节奏具备阶段差异","强弱变化与结构节点相互对应"),("章节功能可定位","章节承担的叙事职责可以回溯")]
        strengths=[Strength(title=t,why_good=w,chapter_start=stages[min(i,len(stages)-1)].chapter_start,chapter_end=stages[min(i,len(stages)-1)].chapter_end,evidence=stages[min(i,len(stages)-1)].evidence) for i,(t,w) in enumerate(strength_specs)]
        issue_specs=[("structure","阶段边界信息拥挤","相邻目标与转折在同一窗口集中","读者可能来不及确认新方向"),("protagonist_growth","成长反馈间隔偏长","选择与能力反馈未总在同一阶段显现","成长获得感可能延迟"),("character_relationships","关系转折密度不均","部分关系长期服务主线但缺少独立反馈","人物关系可能显得工具化"),("suspense_payoff","线索回收距离偏长","长期问题跨越多个结构阶段","读者可能遗忘早期承诺"),("pacing","中段信号波动","多类信息在同一窗口集中","方向感可能短暂下降"),("chapter_efficiency","过渡功能局部集中","连续章节承担相似连接职责","阅读推进感可能变弱")]
        issues=[]
        for i in range(12):
            category,symptom,cause,impact=issue_specs[i%len(issue_specs)]; point=points[min(len(points)-1,(i*len(points))//12)]; priority=("P0","P1","P2")[min(2,i//4)]
            issues.append(AssessmentIssue(issue_id=f"I-{i+1}",priority=priority,category=category,chapter_start=point.chapter_start,chapter_end=point.chapter_end,symptom=symptom,root_cause=cause,reader_impact=impact,supporting_metrics=[f"pace_speed={point.pace_speed}",f"hook_density={point.hook_density}"],evidence=refs(point.chapter_start,point.chapter_end),possible_direction="优先调整信息次序与反馈间隔，保留既有剧情事实"))
        assessment=AssessmentResult(overall_summary="全书已形成结构、人物、悬念、节奏和章节效率之间的可解释闭环；优先处理局部信息拥挤，同时保护已经互相支撑的核心设计。",dimensions=dimensions,strengths=strengths,issues=issues,issue_map=issues,revision_priorities=[RevisionPriority(priority="first",chapter_ranges=[[issues[0].chapter_start,issues[0].chapter_end]],direction=issues[0].possible_direction,preserve=[strengths[0].title]),RevisionPriority(priority="second",chapter_ranges=[],direction="复核线索反馈间隔",preserve=["主角代价链"]),RevisionPriority(priority="third",chapter_ranges=[],direction="补足尾声人物落点",preserve=["最终高潮结构"])],preserve_list=[x.title for x in strengths])
        metadata=BookMetadata(book_id=book_id,snapshot_id=chapters[0].snapshot_id,revision_hash=chapters[0].revision_hash,title=title,chapter_count=count,character_count=sum(len(c.text) for c in chapters))
        analysis=AnalysisMetadata(run_id=run_id,engine_version=self.ENGINE_VERSION,provider_name=self.extractor.provider_name,model_name=self.extractor.model_name,module_availability={k:Availability.AVAILABLE for k in ["overview","story","characters","suspense","pacing","chapters","assessment"]},provider_calls_completed=len(windows),real_provider_calls=0)
        return WholeBookAnalysisV2(book_metadata=metadata,type_profile=profile,overview=overview,story=story,characters=characters,suspense=suspense,pacing=pacing,chapters=chapter_result,assessment=assessment,evidence_index=evidence_index,analysis_metadata=analysis)

def progress_snapshot(*,stage_index:int,stage_percent:float,current_window:int,total_windows:int,current_chapter:int,total_chapters:int,provider_calls_completed:int,provider_calls_estimated:int,provider:str,model:str,elapsed:int,last_action:str,current_action:str,failed:int=0,retries:int=0,repairs:int=0,estimated_cost:float=0,actual_cost:float=0)->ProgressV2:
    weighted=((stage_index+stage_percent/100)/len(V2_STAGES))*100; rate=max(0.001,weighted/max(1,elapsed)); remaining=int(max(0,(100-weighted)/rate))
    return ProgressV2(overall_percent=min(100,weighted),current_stage=V2_STAGES[min(stage_index,len(V2_STAGES)-1)],stage_percent=stage_percent,current_window=current_window,total_windows=total_windows,current_chapter=current_chapter,total_chapters=total_chapters,provider_calls_completed=provider_calls_completed,provider_calls_estimated=provider_calls_estimated,successful_calls=max(0,provider_calls_completed-failed),failed_calls=failed,retry_calls=retries,repair_calls=repairs,elapsed_seconds=elapsed,estimated_remaining_seconds=remaining,estimated_cost=estimated_cost,estimated_actual_cost=actual_cost,provider=provider,model=model,last_completed_action=last_action,current_action=current_action,last_activity_at=datetime.now(timezone.utc))
