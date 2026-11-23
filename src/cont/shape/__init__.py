"""C5 형상: 치수(매개변수)에서 형상 명세를 만들고, 명세에서 화면용 메시를 만든다.

LLM은 형상을 직접 그리지 않는다. 대화는 치수만 바꾸고, 형상은 치수에서 다시 만들어진다.
명세(spec)는 도구에 묶이지 않는다. 화면용 메시는 이 저장소 안에서 만들고, CAD 파일(STEP)은 뒤에 CAD 엔진을 붙여 같은 명세에서 만든다.
"""
from cont.shape.mesh import Mesh, assembly_mesh, part_mesh, revolve, volume
from cont.shape.spec import Assembly, Part

__all__ = ["Assembly", "Mesh", "Part", "assembly_mesh", "part_mesh", "revolve", "volume"]
