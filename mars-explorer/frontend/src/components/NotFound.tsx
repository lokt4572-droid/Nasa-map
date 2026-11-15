import { hrefFor, navigate } from "../routes";

export default function NotFound() {
  const go = (id: "home" | "map") => (e: React.MouseEvent) => {
    e.preventDefault();
    navigate(id);
  };
  return (
    <div className="not-found" role="main">
      <h1>Page not found</h1>
      <p>
        <a href={hrefFor("home")} onClick={go("home")}>
          Home
        </a>{" "}
        ·{" "}
        <a href={hrefFor("map")} onClick={go("map")}>
          Open the map
        </a>
      </p>
    </div>
  );
}
