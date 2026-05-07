import { useState } from "react";

export default function TracePanel({ trace, feedbackCount, onRevise, onPropose, loading }) {
  const [feedback, setFeedback] = useState("");
  const [prompt, setPrompt] = useState("");

  const hasTrace = trace && trace.thesis;

  const handleRevise = () => {
    if (!feedback.trim()) return;
    onRevise(feedback.trim());
    setFeedback("");
  };

  const handlePropose = () => {
    if (!prompt.trim()) return;
    onPropose(prompt.trim());
    setPrompt("");
  };

  return (
    <div className="trace-panel">
      <div className="trace-header">
        <span>Trace</span>
        {feedbackCount > 0 && (
          <span className="revision-badge">{feedbackCount} revision{feedbackCount !== 1 ? "s" : ""}</span>
        )}
      </div>

      <div className="trace-body">
        {hasTrace ? (
          <>
            <div className="trace-thesis">{trace.thesis}</div>

            <div className="trace-transitions">
              {Object.entries(trace.transitions || {}).map(([arrow, justification]) => (
                <div key={arrow} className="trace-transition">
                  <span className="trace-arrow">{arrow}</span>
                  <span className="trace-justification">{justification}</span>
                </div>
              ))}
            </div>

            <div className="trace-cut">
              cut: [{trace.cut?.join(", ")}]
            </div>
          </>
        ) : (
          <p className="muted">No trace yet. Use propose to generate an edit.</p>
        )}
      </div>

      {!hasTrace && (
        <div className="panel-section">
          <label className="panel-label">Artistic prompt</label>
          <textarea
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Open with the wide establishing shot. Build toward the emotional peak..."
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handlePropose(); }}
          />
          <button
            className="primary"
            onClick={handlePropose}
            disabled={loading || !prompt.trim()}
          >
            {loading ? "Working…" : "Propose edit"}
          </button>
        </div>
      )}

      {hasTrace && (
        <div className="panel-section">
          <label className="panel-label">Feedback — target a transition arrow</label>
          <textarea
            rows={4}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="The 0 → 1 transition doesn't work, they feel too similar."
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRevise(); }}
          />
          <button
            className="primary"
            onClick={handleRevise}
            disabled={loading || !feedback.trim()}
          >
            {loading ? "Revising…" : "Revise edit"}
          </button>
        </div>
      )}
    </div>
  );
}
