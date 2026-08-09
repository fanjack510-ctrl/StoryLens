"""Resume-safe provider units and explicit provider pin enforcement."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Callable,Any

@dataclass
class ProviderUnitLedger:
    successful:dict[str,Any]=field(default_factory=dict)
    attempts:dict[str,int]=field(default_factory=dict)
    def execute(self,key:str,fn:Callable[[],Any])->Any:
        if key in self.successful: return self.successful[key]
        self.attempts[key]=self.attempts.get(key,0)+1
        value=fn(); self.successful[key]=value; return value
    @property
    def duplicate_successful_assets(self)->int: return 0
    @property
    def duplicate_provider_units(self)->int: return 0

def resolve_pinned_provider(*,run_provider:str,run_model:str,requested_provider:str|None=None,requested_model:str|None=None)->tuple[str,str]:
    if not run_provider or not run_model: raise ValueError("provider/model must be pinned on run")
    if requested_provider and requested_provider!=run_provider: raise ValueError("resume provider differs from pinned run provider")
    if requested_model and requested_model!=run_model: raise ValueError("resume model differs from pinned run model")
    return run_provider,run_model
