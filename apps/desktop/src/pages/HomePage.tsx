import { Navigate } from "react-router-dom";

/** Home redirects to library; old "/" route retained via redirect. */
export function HomePage() {
  return <Navigate to="/library" replace />;
}
