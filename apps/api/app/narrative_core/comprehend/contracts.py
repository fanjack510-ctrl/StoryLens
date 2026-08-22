"""「读懂」的产出形状。

用途决定形状：读者没时间读、或读不动原文的语言，他要的是**不读原文也知道这本书说了什么**。
所以每一节的产出不是「摘要」，而是四件可以被检验的东西：

    主张   这一节断定了什么 —— 是判断，不是话题。「讨论了颜色原理」不算主张，
           「分类数据应当用色相区分，类别数不超过 12」才算。
    依据   凭什么这么说 —— 实验、原理，还是某人的权威意见，带上作者年份。
    做法   读者能照着做的动作。没有就明说没有，不许编。
    术语   原文词 + 中文，只收这一节真正定义或反复使用的。

再加一条**没回答的问题**：一份诚实的摘要要让读者知道边界在哪，否则他会以为书里没写的东西
不存在。

每条产出都带节号和页码。对知识类书来说这不是锦上添花：读者拿摘要替代原文，**能不能翻回去
核对，就是这份东西可不可信的分界线**。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SectionDigest", "ChapterDigest", "BookDigest", "ComprehendResult"]


@dataclass
class SectionDigest:
    """一次调用读完之后，关于那一节（或几节）的产出。"""

    label: str
    section_numbers: list[str] = field(default_factory=list)
    book_pages: list[int] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    #: 这一片是不是因为超长被切开的（「1/3」）。读者要能看出来。
    part: int = 1
    part_count: int = 1
    #: 调用失败时记下来。失败的节必须留痕——静默跳过等于让内容消失。
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.claims)


@dataclass
class ChapterDigest:
    chapter: str
    title: str
    summary: str = ""
    through_line: str = ""
    sections: list[SectionDigest] = field(default_factory=list)
    error: str = ""


@dataclass
class BookDigest:
    one_paragraph: str = ""
    argument: str = ""
    who_should_read: str = ""
    what_you_get: str = ""
    error: str = ""


@dataclass
class ComprehendResult:
    """一次「读懂」的全部产出，外加它自己的可信度账。"""

    book: BookDigest = field(default_factory=BookDigest)
    chapters: list[ChapterDigest] = field(default_factory=list)
    #: 大纲里一共多少节，最终有多少节的内容真的进了报告。
    sections_total: int = 0
    sections_covered: int = 0
    provider_calls: int = 0
    failures: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if not self.sections_total else self.sections_covered / self.sections_total

    @property
    def trustworthy(self) -> bool:
        """低于九成覆盖，这份摘要就不该被当作「读过这本书」。

        小说漏一段，报告读起来仍然完整；知识类书漏一节，读者不会知道自己漏了什么。
        所以这里给一个明确的阈值，而不是让界面自己去解释一个百分比。
        """
        return self.coverage >= 0.9 and not self.book.error
