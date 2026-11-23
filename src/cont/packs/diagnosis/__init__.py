"""진단 물리 팩: 설비 공통 이상진단 (구동계, 압력·유동계, 열관리계, 공정 동작·사이클)."""
from cont.packs import register
from cont.packs.diagnosis.equipment import EquipmentDiagnosis, diagnose_equipment, load_site, site_special
from cont.packs.diagnosis.guidance import Guidance, guide
from cont.packs.diagnosis.pack import Diagnosis, DiagnosisPack, diagnose
from cont.packs.diagnosis.trend import Trend, trend

PACK = register(DiagnosisPack())

__all__ = ["Diagnosis", "DiagnosisPack", "EquipmentDiagnosis", "Guidance", "PACK", "Trend", "diagnose", "diagnose_equipment",
           "guide", "load_site", "site_special", "trend"]
