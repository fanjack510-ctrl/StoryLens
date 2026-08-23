"""这是小说，还是工具书。

导入面板问的一直是「整本 / 短篇」——那是关于**怎么切**的工程问题，提示里甚至写着「专著、
教材、工具书选整本」，等于让用户自己把书的类型翻译成切法。而类型才是这本书最要紧的属性：

* 它决定能用哪几种读法——小说走评测与拆文，工具书走读懂；
* 它决定章节识别该不该按小说的章号格式去校准——一本 1603 页的手册按节读，识别不到
  「第几章」根本不是问题，却照样挨了一整块小说校准的警告。

`NULL` 表示没人回答过。没回答就推断，所以老书行为不变。**推断出来的值不写库**——写了就
分不清「用户说的」和「程序猜的」，而这两者在界面上必须能分开：猜的要标「待确认」。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

__all__ = ["FICTION", "REFERENCE", "VALID_KINDS", "book_material_kind", "infer_material_kind"]

FICTION = "fiction"
REFERENCE = "reference"
VALID_KINDS = (FICTION, REFERENCE)

#: 结构直接读自原书目录时留下的标记。只有专著/工具书那条解析路径会产生它。
_FROM_BOOK_TOC = "结构来自原书目录"
#: 更早导入的书没有上面那个标记，但只要走过专著解析，规则里一定有这句。
_MONOGRAPH_TRACE = "精确定位"


def infer_material_kind(session: Session, book_id: int) -> str:
    """没人回答过时，猜一个。按证据由强到弱：

    1. **这本书已经跑过「读懂」。** 那条读法只做专著与工具书——跑过就是最硬的证据，比任何
       解析痕迹都可靠，而且不受导入时机影响。
    2. 解析时走了「章首目录 + 逐节定位」那条路。标记 `结构来自原书目录` 是后来才加的，所以
       更早导入的书要退回看它的解析规则——「小节 N 个，精确定位 N 个」同样只有那条路会写。
    3. 都没有，按小说算。绝大多数导入的是小说，而且猜错成小说的代价更小：用户在书库里改一下
       就是了，不会有人误以为自己的小说被当成教材读过。
    """
    ran_comprehend = session.execute(
        text(
            "SELECT 1 FROM whole_book_runs "
            "WHERE book_id = :book_id AND engine_id = 'comprehend_engine' LIMIT 1"
        ),
        {"book_id": int(book_id)},
    ).first()
    if ran_comprehend:
        return REFERENCE

    row = session.execute(
        text("SELECT import_diagnostics_json FROM books WHERE id = :book_id"),
        {"book_id": int(book_id)},
    ).first()
    diagnostics = (row[0] if row else "") or ""
    if _FROM_BOOK_TOC in diagnostics or _MONOGRAPH_TRACE in diagnostics:
        return REFERENCE
    return FICTION


def book_material_kind(session: Session, book_id: int) -> tuple[str, bool]:
    """(类型, 是不是用户亲口说的)。

    第二个值是给界面用的：程序猜的要标「待确认」，让人点一下就定。悄悄替他决定，等于把一个
    再也没人会去看的错误值固定下来——书名当年就是这么错的。
    """
    row = session.execute(
        text("SELECT material_kind FROM books WHERE id = :book_id"),
        {"book_id": int(book_id)},
    ).first()
    stored = str((row[0] if row else "") or "").strip()
    if stored in VALID_KINDS:
        return stored, True
    return infer_material_kind(session, book_id), False
