import { useState } from "react";

const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${backendUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  return response.json();
}

function SummaryCard({ title, payload }) {
  if (!payload) {
    return null;
  }

  return (
    <section style={styles.card}>
      <h2 style={styles.cardTitle}>{title}</h2>
      <p style={styles.summaryText}>{payload.summary}</p>
      <p style={styles.meta}>Tasks: {payload.task_count}</p>
      <ul style={styles.list}>
        {payload.tasks.map((task) => (
          <li key={task.id} style={styles.listItem}>
            <strong>{task.title}</strong>
            <span>{task.when ? new Date(task.when).toLocaleString() : "без даты"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function App() {
  const tgUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
  const [telegramId, setTelegramId] = useState(tgUserId ? String(tgUserId) : "");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("Не подключено");
  const [daySummary, setDaySummary] = useState(null);
  const [weekSummary, setWeekSummary] = useState(null);
  const [busy, setBusy] = useState(false);

  async function connectAccount() {
    setBusy(true);
    try {
      const result = await request("/auth/connect", {
        method: "POST",
        body: JSON.stringify({
          telegram_id: telegramId || null,
          singularity_api_token: token || null,
          timezone: "Europe/Moscow",
        }),
      });
      setStatus(result.connected ? "Аккаунт подключен" : "Профиль создан, но токен не сохранен");
    } catch (error) {
      setStatus(`Ошибка подключения: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function syncData() {
    setBusy(true);
    try {
      const result = await request("/sync/full", {
        method: "POST",
        body: JSON.stringify({
          telegram_id: telegramId || null,
          timezone: "Europe/Moscow",
        }),
      });
      setStatus(`Синхронизация завершена. Задач: ${result.tasks_synced}.`);
    } catch (error) {
      setStatus(`Ошибка синхронизации: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadSummary(period) {
    setBusy(true);
    try {
      const result = await request(`/summary/${period}?telegram_id=${encodeURIComponent(telegramId || "")}`);
      if (period === "day") {
        setDaySummary(result);
      } else {
        setWeekSummary(result);
      }
      setStatus(`Summary ${period} загружена.`);
    } catch (error) {
      setStatus(`Ошибка загрузки summary: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={styles.page}>
      <section style={styles.hero}>
        <p style={styles.eyebrow}>SingularityApp x Telegram</p>
        <h1 style={styles.title}>SE Toolkit Mini App</h1>
        <p style={styles.subtitle}>
          Подключи API token, синхронизируй задачи и получи сводку дня или недели.
        </p>
      </section>

      <section style={styles.panel}>
        <label style={styles.label}>
          Telegram user id
          <input
            value={telegramId}
            onChange={(event) => setTelegramId(event.target.value)}
            placeholder="Например, 123456789"
            style={styles.input}
          />
        </label>

        <label style={styles.label}>
          Singularity API token
          <input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Вставь token из SingularityApp"
            style={styles.input}
          />
        </label>

        <div style={styles.actions}>
          <button onClick={connectAccount} disabled={busy} style={styles.primaryButton}>
            Connect
          </button>
          <button onClick={syncData} disabled={busy} style={styles.secondaryButton}>
            Sync
          </button>
          <button onClick={() => loadSummary("day")} disabled={busy} style={styles.secondaryButton}>
            Day
          </button>
          <button onClick={() => loadSummary("week")} disabled={busy} style={styles.secondaryButton}>
            Week
          </button>
        </div>

        <p style={styles.status}>{status}</p>
      </section>

      <SummaryCard title="Day Summary" payload={daySummary} />
      <SummaryCard title="Week Summary" payload={weekSummary} />
    </main>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    margin: 0,
    padding: "32px 20px 48px",
    fontFamily: '"Segoe UI", "Helvetica Neue", sans-serif',
    background:
      "radial-gradient(circle at top left, rgba(30,144,255,0.18), transparent 32%), linear-gradient(180deg, #f3f7fb 0%, #ffffff 100%)",
    color: "#102033",
  },
  hero: {
    maxWidth: 760,
    margin: "0 auto 24px",
  },
  eyebrow: {
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.14em",
    fontSize: 12,
    color: "#2f6cab",
  },
  title: {
    margin: "10px 0 8px",
    fontSize: "clamp(32px, 6vw, 56px)",
    lineHeight: 1,
  },
  subtitle: {
    margin: 0,
    maxWidth: 620,
    fontSize: 18,
    lineHeight: 1.5,
    color: "#425466",
  },
  panel: {
    maxWidth: 760,
    margin: "0 auto 24px",
    padding: 24,
    borderRadius: 24,
    background: "rgba(255, 255, 255, 0.9)",
    boxShadow: "0 18px 50px rgba(16, 32, 51, 0.12)",
    backdropFilter: "blur(12px)",
  },
  label: {
    display: "block",
    marginBottom: 14,
    fontSize: 14,
    fontWeight: 600,
  },
  input: {
    display: "block",
    width: "100%",
    marginTop: 8,
    padding: "14px 16px",
    borderRadius: 14,
    border: "1px solid #d6dfeb",
    fontSize: 15,
    boxSizing: "border-box",
  },
  actions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
    marginTop: 20,
  },
  primaryButton: {
    border: 0,
    borderRadius: 999,
    padding: "12px 18px",
    background: "#0b6bcb",
    color: "#fff",
    fontWeight: 700,
    cursor: "pointer",
  },
  secondaryButton: {
    border: "1px solid #0b6bcb",
    borderRadius: 999,
    padding: "12px 18px",
    background: "#fff",
    color: "#0b6bcb",
    fontWeight: 700,
    cursor: "pointer",
  },
  status: {
    margin: "18px 0 0",
    fontSize: 14,
    color: "#425466",
  },
  card: {
    maxWidth: 760,
    margin: "0 auto 20px",
    padding: 24,
    borderRadius: 24,
    background: "#ffffff",
    boxShadow: "0 16px 40px rgba(16, 32, 51, 0.08)",
  },
  cardTitle: {
    margin: "0 0 12px",
    fontSize: 24,
  },
  summaryText: {
    margin: "0 0 12px",
    fontSize: 16,
    lineHeight: 1.6,
  },
  meta: {
    margin: "0 0 16px",
    color: "#6a7a89",
  },
  list: {
    listStyle: "none",
    padding: 0,
    margin: 0,
    display: "grid",
    gap: 10,
  },
  listItem: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    padding: "12px 14px",
    borderRadius: 14,
    background: "#f5f8fc",
    fontSize: 14,
  },
};
