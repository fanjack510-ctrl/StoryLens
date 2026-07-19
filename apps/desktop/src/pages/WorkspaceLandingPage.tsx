import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { booksApi } from "../services/booksApi";
import { Empty } from "../components/common/States";
export function WorkspaceLandingPage() {
  const books = useQuery({ queryKey: ["books"], queryFn: booksApi.list });
  return (
    <section className="page">
      <div className="page-title">
        <div>
          <p className="eyebrow">分析工作台</p>
          <h1>选择一本书</h1>
          <p>进入三栏工作台阅读正文、场景和证据。</p>
        </div>
      </div>
      <div className="panel">
        {books.data?.map((b) => (
          <Link className="list-row" key={b.id} to={`/books/${b.id}`}>
            <b>{b.title}</b>
            <span>打开 ›</span>
          </Link>
        ))}
        {!books.data?.length && <Empty text="还没有可分析的书籍" />}
      </div>
    </section>
  );
}
