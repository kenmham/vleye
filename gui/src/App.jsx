import { useEffect, useState, useCallback } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import SceneCard from "./components/SceneCard.jsx";
import Viewfinder from "./components/Viewfinder.jsx";
import TracePanel from "./components/TracePanel.jsx";
import "./App.css";

const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

export default function App() {
  const [scenes, setScenes] = useState([]);
  const [order, setOrder] = useState([]);
  const [trace, setTrace] = useState("");
  const [feedbackCount, setFeedbackCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedScene, setSelectedScene] = useState(null);

  const loadState = useCallback(async () => {
    try {
      const data = await api.get("/api/state");
      setScenes(data.scenes);
      setOrder(data.scenes.map((s) => s.id));
      setTrace(data.trace || "");
      setFeedbackCount(data.feedback_count || 0);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { loadState(); }, [loadState]);

  const orderedScenes = order
    .map((id) => scenes.find((s) => s.id === id))
    .filter(Boolean);

  const sensors = useSensors(useSensor(PointerSensor));

  const handleDragEnd = async ({ active, over }) => {
    if (!over || active.id === over.id) return;
    const oldIndex = order.indexOf(active.id);
    const newIndex = order.indexOf(over.id);
    const newOrder = arrayMove(order, oldIndex, newIndex);
    setOrder(newOrder);
    try {
      await api.post("/api/reorder", { order: newOrder });
    } catch (e) {
      setError(e.message);
      setOrder(order);
    }
  };

  const handlePropose = async (prompt) => {
    setLoading(true);
    setError("");
    try {
      const data = await api.post("/api/propose", { prompt });
      setOrder(data.order);
      setTrace(data.trace);
      await loadState();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRevise = async (feedback) => {
    setLoading(true);
    setError("");
    try {
      const data = await api.post("/api/revise", { feedback });
      setOrder(data.order);
      setTrace(data.trace);
      setFeedbackCount((n) => n + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <span className="logo">vleye</span>
        {error && <span className="error-banner">{error}</span>}
      </header>

      <main className="app-body">
        <section className="timeline-panel">
          <div className="panel-title">
            Timeline — {orderedScenes.length} scene{orderedScenes.length !== 1 ? "s" : ""}
          </div>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={order} strategy={verticalListSortingStrategy}>
              <div className="scene-list">
                {orderedScenes.map((scene, i) => (
                  <SceneCard
                    key={scene.id}
                    scene={scene}
                    position={i + 1}
                    selected={selectedScene?.id === scene.id}
                    onSelect={setSelectedScene}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </section>

        <Viewfinder scene={selectedScene} />

        <TracePanel
          trace={trace}
          feedbackCount={feedbackCount}
          onPropose={handlePropose}
          onRevise={handleRevise}
          loading={loading}
        />
      </main>
    </div>
  );
}
