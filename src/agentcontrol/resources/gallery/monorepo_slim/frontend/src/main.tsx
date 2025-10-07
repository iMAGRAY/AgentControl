import React from "react";
import ReactDOM from "react-dom/client";

function App() {
  const [message, setMessage] = React.useState("loading…");

  React.useEffect(() => {
    fetch("http://localhost:8000/api/info")
      .then((response) => response.json())
      .then((data) => setMessage(data.message ?? "unknown"))
      .catch(() => setMessage("backend unavailable"));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>Monorepo Frontend</h1>
      <p>{message}</p>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
