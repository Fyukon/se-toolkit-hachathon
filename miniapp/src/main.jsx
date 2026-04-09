import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";


class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Mini App crashed", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <main
          style={{
            minHeight: "100vh",
            margin: 0,
            padding: 24,
            fontFamily: '"Segoe UI", "Helvetica Neue", sans-serif',
            background: "#fff7f5",
            color: "#4a1e13",
          }}
        >
          <h1 style={{ marginTop: 0 }}>Mini App crashed</h1>
          <p style={{ lineHeight: 1.6 }}>
            При рендере произошла ошибка JavaScript. Это уже не белый экран: ниже видно исходную причину.
          </p>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              padding: 16,
              borderRadius: 16,
              background: "#fff",
              border: "1px solid #efc6bd",
            }}
          >
            {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
          </pre>
        </main>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>,
);
