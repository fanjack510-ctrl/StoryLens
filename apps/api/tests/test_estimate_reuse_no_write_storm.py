"""「准备全书分析」是个用来看的页面，不该每次打开都往库里写一行。"""
from sqlalchemy.orm import sessionmaker

from app.db.models import ProviderConfiguration, WholeBookCostEstimate
from app.narrative_core.services.whole_book_cost_estimate_service import (
    estimate_whole_book_analysis,
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
