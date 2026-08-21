"""「准备全书分析」是个用来看的页面，不该每次打开都往库里写一行。"""
from sqlalchemy.orm import sessionmaker

from app.db.models import ProviderConfiguration, WholeBookCostEstimate
from app.narrative_core.services.whole_book_cost_estimate_service import (
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_hierarchical_estimate_v1 import (
    estimate_hierarchical_whole_book_analysis_v1,
)
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book

DEEPSEEK_MODEL_FLASH = "deepseek-v4-flash"


def _seed_provider(session) -> ProviderConfiguration:
    row = ProviderConfiguration(
        provider_name="deepseek",
        enabled=True,
        disconnected=False,
        plus_model=DEEPSEEK_MODEL_FLASH,
        max_model=DEEPSEEK_MODEL_FLASH,
        flash_model=DEEPSEEK_MODEL_FLASH,
        base_url="https://api.deepseek.com",
        credential_reference="keyring:deepseek",
    )
    session.add(row)
    session.flush()
    return row


def test_repeated_prepare_reuses_one_estimate_row(tmp_path) -> None:
    """页面在有任务跑着时每 3 秒轮询一次；每调一次插一行，它就成了写入方。

    结果是一个纯粹用来看的页面跟正在跑的分析抢同一把写锁——日志里 84 次
    `database is locked` 全是它，最后连它自己都 500，屏幕上显示「本地分析服务暂时不可用」。
    """
    engine = make_engine(tmp_path, "estimate-reuse.db")
    with sessionmaker(bind=engine)() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_provider(session)

        first = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        rows_after_first = session.query(WholeBookCostEstimate).count()

        for _ in range(5):
            again = estimate_whole_book_analysis(
                session, book.id, "whole_book_native", provider.id
            )
            assert again.id == first.id, "同一本书、同一读法、同一模型，预估应当复用同一行"

        assert session.query(WholeBookCostEstimate).count() == rows_after_first, (
            "轮询五次不该多出五行"
        )


def test_prepare_path_reuses_one_estimate_row(tmp_path) -> None:
    """上面那条测的是旧的估算函数，而 prepare 根本不走它。

    我第一次「修好」这个写入风暴时，改的是 estimate_whole_book_analysis，测试也只盯着它，
    于是测试通过、页面照旧每打开一次多一行——直到把打包版跑起来数了一遍行数才发现。
    prepare 真正调的是 estimate_hierarchical_whole_book_analysis_v1，这条盯的是它。
    """
    engine = make_engine(tmp_path, "estimate-reuse-hier.db")
    with sessionmaker(bind=engine)() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_provider(session)

        first, _plan = estimate_hierarchical_whole_book_analysis_v1(
            session, book.id, "whole_book_native", provider.id, provider_name="deepseek"
        )
        session.flush()
        rows_after_first = session.query(WholeBookCostEstimate).count()

        for _ in range(5):
            again, _p = estimate_hierarchical_whole_book_analysis_v1(
                session, book.id, "whole_book_native", provider.id, provider_name="deepseek"
            )
            assert again.id == first.id, "同一本书、同一版本、同一读法、同一模型，应当复用同一行"

        assert session.query(WholeBookCostEstimate).count() == rows_after_first, (
            "轮询五次不该多出五行——这正是那 84 次 database is locked 的来源"
        )
