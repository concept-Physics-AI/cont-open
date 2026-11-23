"""C4 표현: 답변 묶음을 화면으로. 외부 자원 없이 한 파일로 열리는 HTML을 만든다."""
from cont.view.fastening_html import render_fastening
from cont.view.fastening_live import render_live
from cont.view.diagnosis_html import Section, render_diagnosis, render_equipment, render_special

__all__ = ["Section", "render_fastening", "render_live", "render_diagnosis", "render_equipment", "render_special"]
