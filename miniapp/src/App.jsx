import React, { useEffect, useState } from "react";

const backendUrl =
  import.meta.env.VITE_BACKEND_URL ||
  (typeof window !== "undefined" ? `${window.location.origin}/api` : "http://localhost:8000");

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

function getTelegramUserId() {
  try {
    if (typeof window === "undefined") {
      return "";
    }

    const id = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
    return id ? String(id) : "";
  } catch (error) {
    console.error("Failed to read Telegram user id", error);
    return "";
  }
}

function formatWhen(value) {
  if (!value) return "без даты";
  try {
    return new Date(value).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function formatPriority(priority) {
  const mapping = {
    high: "высокий",
    normal: "обычный",
    low: "низкий",
  };
  return mapping[(priority || "").toLowerCase()] || "не указан";
}

function formatStatus(status) {
  const mapping = {
    open: "активна",
    completed: "выполнена",
    done: "выполнена",
    scheduled: "запланирована",
    draft: "черновик",
    applied: "применено",
    cancelled: "отменено",
    clarification_required: "нужно уточнение",
    validation_failed: "ошибка валидации",
  };
  return mapping[(status || "").toLowerCase()] || status || "неизвестно";
}

function SummaryCard({ title, payload }) {
  if (!payload) return null;
  const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];

  return (
    <section style={styles.card}>
      <div style={styles.cardHeader}>
        <div>
          <p style={styles.kicker}>Summary</p>
          <h2 style={styles.cardTitle}>{title}</h2>
        </div>
        <div style={styles.badge}>{payload.task_count ?? tasks.length} задач</div>
      </div>
      <p style={styles.summaryText}>{payload.summary}</p>
      <div style={styles.taskGrid}>
        {tasks.map((task, index) => (
          <article key={task.id} style={styles.taskCard}>
            <strong style={styles.taskTitle}>{task.title || `Задача ${index + 1}`}</strong>
            <span style={styles.taskMeta}>{formatWhen(task.when)}</span>
            <span style={styles.taskMeta}>Приоритет: {formatPriority(task.priority)}</span>
            <span style={styles.taskMeta}>Статус: {formatStatus(task.status)}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function CandidateList({ candidates, onSelectCandidate, busy }) {
  const items = Array.isArray(candidates) ? candidates : [];
  if (!items.length) return null;
  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Кандидаты</h3>
      <div style={styles.taskGrid}>
        {items.map((item, index) => (
          <article key={item.external_id || `${item.title || "candidate"}-${index}`} style={styles.taskCard}>
            <strong style={styles.taskTitle}>{item.title || `Кандидат ${index + 1}`}</strong>
            <span style={styles.taskMeta}>{formatWhen(item.when)}</span>
            <span style={styles.taskMeta}>Приоритет: {formatPriority(item.priority)}</span>
            <span style={styles.taskMeta}>Статус: {formatStatus(item.status)}</span>
            {typeof onSelectCandidate === "function" ? (
              <button
                type="button"
                onClick={() => onSelectCandidate(index)}
                disabled={busy}
                style={styles.choiceButton}
              >
                Выбрать
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}

function ValidationList({ errors }) {
  const items = Array.isArray(errors) ? errors : [];
  if (!items.length) return null;
  return (
    <div style={styles.warningBox}>
      <h3 style={styles.warningTitle}>Что требует внимания</h3>
      <ul style={styles.warningList}>
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function DraftCard({ draft, onConfirm, onCancel, onSelectCandidate, busy }) {
  if (!draft) return null;

  const action = draft.parsed_action || {};

  return (
    <section style={styles.card}>
      <div style={styles.cardHeader}>
        <div>
          <p style={styles.kicker}>Action Draft</p>
          <h2 style={styles.cardTitle}>Черновик #{draft.id}</h2>
        </div>
        <div style={styles.badge}>{formatStatus(draft.status)}</div>
      </div>

      <p style={styles.summaryText}>{draft.message}</p>

      <div style={styles.detailGrid}>
        <div style={styles.detailItem}>
          <span style={styles.detailLabel}>Интент</span>
          <strong>{draft.intent || "не определён"}</strong>
        </div>
        <div style={styles.detailItem}>
          <span style={styles.detailLabel}>Исходная команда</span>
          <strong>{draft.original_text}</strong>
        </div>
        {action.target_title ? (
          <div style={styles.detailItem}>
            <span style={styles.detailLabel}>Целевая задача</span>
            <strong>{action.target_title}</strong>
          </div>
        ) : null}
        {action.title ? (
          <div style={styles.detailItem}>
            <span style={styles.detailLabel}>Новая задача</span>
            <strong>{action.title}</strong>
          </div>
        ) : null}
        {action.current_when ? (
          <div style={styles.detailItem}>
            <span style={styles.detailLabel}>Старое время</span>
            <strong>{formatWhen(action.current_when)}</strong>
          </div>
        ) : null}
        {action.new_when ? (
          <div style={styles.detailItem}>
            <span style={styles.detailLabel}>Новое время</span>
            <strong>{formatWhen(action.new_when)}</strong>
          </div>
        ) : null}
      </div>

      <ValidationList errors={draft.validation_errors} />
      <CandidateList
        candidates={draft.candidates}
        onSelectCandidate={draft.status === "clarification_required" ? onSelectCandidate : undefined}
        busy={busy}
      />

      {draft.status === "draft" ? (
        <div style={styles.actions}>
          <button onClick={onConfirm} disabled={busy} style={styles.primaryButton}>
            Confirm
          </button>
          <button onClick={onCancel} disabled={busy} style={styles.secondaryButton}>
            Cancel
          </button>
        </div>
      ) : null}
    </section>
  );
}

export function App() {
  const [telegramId, setTelegramId] = useState(() => getTelegramUserId());
  const [token, setToken] = useState("");
  const [actionText, setActionText] = useState("перенеси лабу DSA на завтра 15:00");
  const [status, setStatus] = useState("Не подключено");
  const [daySummary, setDaySummary] = useState(null);
  const [weekSummary, setWeekSummary] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      window.Telegram?.WebApp?.ready?.();
    } catch (error) {
      console.error("Telegram WebApp ready() failed", error);
    }
  }, []);

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
      setStatus(result.connected ? "Аккаунт подключен" : "Профиль создан, но токен не сохранён");
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
      setStatus(`Сводка ${period === "day" ? "дня" : "недели"} загружена.`);
    } catch (error) {
      setStatus(`Ошибка загрузки summary: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function createDraft() {
    setBusy(true);
    try {
      const result = await request("/actions/parse", {
        method: "POST",
        body: JSON.stringify({
          telegram_id: telegramId || null,
          text: actionText,
        }),
      });
      setDraft(result);
      setStatus(`Draft #${result.id} создан.`);
    } catch (error) {
      setStatus(`Ошибка создания draft: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function selectCandidate(candidateIndex) {
    if (!draft?.id) return;
    setBusy(true);
    try {
      const result = await request(`/actions/${draft.id}/select-candidate`, {
        method: "POST",
        body: JSON.stringify({
          telegram_id: telegramId || null,
          candidate_index: candidateIndex,
        }),
      });
      setDraft(result);
      setStatus(`Вариант для draft #${result.id} выбран.`);
    } catch (error) {
      setStatus(`Ошибка выбора варианта: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function confirmDraft() {
    if (!draft?.id) return;
    setBusy(true);
    try {
      const result = await request(`/actions/${draft.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({
          telegram_id: telegramId || null,
        }),
      });
      setDraft(result);
      setStatus(`Draft #${result.id} применён.`);
      await Promise.all([loadSummary("day"), loadSummary("week")]);
    } catch (error) {
      setStatus(`Ошибка confirm: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancelDraft() {
    if (!draft?.id) return;
    setBusy(true);
    try {
      const result = await request(`/actions/${draft.id}/cancel`, {
        method: "POST",
        body: JSON.stringify({
          telegram_id: telegramId || null,
        }),
      });
      setDraft(result);
      setStatus(`Draft #${result.id} отменён.`);
    } catch (error) {
      setStatus(`Ошибка cancel: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={styles.page}>
      <section style={styles.hero}>
        <div style={styles.heroBadge}>Version 2</div>
        <p style={styles.eyebrow}>SingularityApp x Telegram x OpenRouter</p>
        <h1 style={styles.title}>SE Toolkit Planner</h1>
        <p style={styles.subtitle}>
          Подключи SingularityApp, синхронизируй задачи, получай сводки и управляй расписанием через команды на естественном языке.
        </p>
        <p style={styles.runtimeHint}>Backend: {backendUrl}</p>
      </section>

      <section style={styles.panel}>
        <div style={styles.columns}>
          <div>
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
          </div>

          <div style={styles.actionBox}>
            <p style={styles.kicker}>Action Studio</p>
            <h2 style={styles.boxTitle}>Сформулируй изменение</h2>
            <textarea
              value={actionText}
              onChange={(event) => setActionText(event.target.value)}
              placeholder="Например: перенеси лабу DSA на завтра 15:00"
              style={styles.textarea}
            />
            <div style={styles.actions}>
              <button onClick={createDraft} disabled={busy} style={styles.primaryButton}>
                Create Draft
              </button>
            </div>
          </div>
        </div>

        <p style={styles.status}>{status}</p>
      </section>

      <DraftCard
        draft={draft}
        onConfirm={confirmDraft}
        onCancel={cancelDraft}
        onSelectCandidate={selectCandidate}
        busy={busy}
      />
      <SummaryCard title="План на день" payload={daySummary} />
      <SummaryCard title="План на неделю" payload={weekSummary} />
    </main>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    margin: 0,
    padding: "36px 18px 64px",
    fontFamily: '"Segoe UI", "Helvetica Neue", sans-serif',
    background:
      "radial-gradient(circle at top left, rgba(20,109,182,0.14), transparent 26%), radial-gradient(circle at bottom right, rgba(244,121,32,0.14), transparent 32%), linear-gradient(180deg, #eef4f8 0%, #ffffff 100%)",
    color: "#102033",
  },
  hero: {
    maxWidth: 980,
    margin: "0 auto 28px",
  },
  heroBadge: {
    display: "inline-block",
    padding: "8px 14px",
    borderRadius: 999,
    background: "#102033",
    color: "#fff",
    fontSize: 12,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
  },
  eyebrow: {
    margin: "18px 0 0",
    textTransform: "uppercase",
    letterSpacing: "0.14em",
    fontSize: 12,
    color: "#2f6cab",
  },
  title: {
    margin: "10px 0 8px",
    fontSize: "clamp(32px, 6vw, 60px)",
    lineHeight: 0.98,
  },
  subtitle: {
    margin: 0,
    maxWidth: 780,
    fontSize: 18,
    lineHeight: 1.55,
    color: "#425466",
  },
  runtimeHint: {
    margin: "16px 0 0",
    fontSize: 13,
    color: "#607487",
  },
  panel: {
    maxWidth: 980,
    margin: "0 auto 24px",
    padding: 24,
    borderRadius: 28,
    background: "rgba(255, 255, 255, 0.92)",
    boxShadow: "0 18px 50px rgba(16, 32, 51, 0.10)",
    backdropFilter: "blur(12px)",
  },
  columns: {
    display: "grid",
    gridTemplateColumns: "1.15fr 1fr",
    gap: 20,
  },
  actionBox: {
    padding: 20,
    borderRadius: 24,
    background: "linear-gradient(180deg, #0f4f8a 0%, #16365e 100%)",
    color: "#fff",
  },
  boxTitle: {
    margin: "6px 0 12px",
    fontSize: 24,
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
  textarea: {
    width: "100%",
    minHeight: 140,
    resize: "vertical",
    boxSizing: "border-box",
    borderRadius: 18,
    border: "1px solid rgba(255,255,255,0.24)",
    background: "rgba(255,255,255,0.08)",
    color: "#fff",
    padding: 16,
    fontSize: 15,
    lineHeight: 1.5,
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
  choiceButton: {
    marginTop: 10,
    border: 0,
    borderRadius: 12,
    padding: "10px 12px",
    background: "#102033",
    color: "#fff",
    fontWeight: 700,
    cursor: "pointer",
  },
  status: {
    margin: "18px 0 0",
    fontSize: 14,
    color: "#425466",
  },
  card: {
    maxWidth: 980,
    margin: "0 auto 20px",
    padding: 24,
    borderRadius: 28,
    background: "#ffffff",
    boxShadow: "0 16px 40px rgba(16, 32, 51, 0.08)",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "flex-start",
  },
  kicker: {
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    fontSize: 11,
    opacity: 0.8,
  },
  cardTitle: {
    margin: "4px 0 0",
    fontSize: 28,
  },
  badge: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "#eef4fa",
    color: "#1f4f82",
    fontWeight: 700,
    whiteSpace: "nowrap",
  },
  summaryText: {
    margin: "18px 0 0",
    fontSize: 16,
    lineHeight: 1.6,
    color: "#2f3c4d",
  },
  taskGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 12,
    marginTop: 18,
  },
  taskCard: {
    display: "grid",
    gap: 6,
    padding: 16,
    borderRadius: 18,
    background: "#f6f9fc",
    border: "1px solid #e2ebf3",
  },
  taskTitle: {
    fontSize: 15,
    lineHeight: 1.35,
  },
  taskMeta: {
    fontSize: 13,
    color: "#536273",
  },
  detailGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 12,
    marginTop: 18,
  },
  detailItem: {
    display: "grid",
    gap: 6,
    padding: 16,
    borderRadius: 18,
    background: "#f6f9fc",
    border: "1px solid #e2ebf3",
  },
  detailLabel: {
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "#66788a",
  },
  subsection: {
    marginTop: 18,
  },
  subsectionTitle: {
    margin: "0 0 10px",
    fontSize: 18,
  },
  warningBox: {
    marginTop: 18,
    padding: 16,
    borderRadius: 18,
    background: "#fff6e8",
    border: "1px solid #f4d49b",
  },
  warningTitle: {
    margin: "0 0 8px",
    fontSize: 16,
  },
  warningList: {
    margin: 0,
    paddingLeft: 18,
    color: "#6f4e0b",
  },
};
