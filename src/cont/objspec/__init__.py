"""공통 대상 명세 (Y9): 이미지·3D·4D·그래프가 같은 부품 ID로 같은 대상을 가리키게 한다."""
from .check import Report, Representation, affected, check
from .spec import ObjectSpec, ObjectSpecError, ObjPart, Pose, Stage, ViewState
from .image import SpecImage, generate_image, image_prompt, image_request
from .scene import Segment, Timeline, load_playback
from .select import EditResult, Selection, SelectionError, edit_selection, overlaps, select, select_region
from .templates import hybrid_bonding_stack

__all__ = ["EditResult", "ObjectSpec", "ObjectSpecError", "ObjPart", "Pose", "Report", "Representation", "Segment", "Selection", "SelectionError", "SpecImage", "Stage", "Timeline", "load_playback", "ViewState",
           "affected", "check", "edit_selection", "overlaps", "select", "select_region", "generate_image", "image_prompt", "image_request", "hybrid_bonding_stack"]
