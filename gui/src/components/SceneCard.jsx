import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
};

export default function SceneCard({ scene, position, selected, onSelect }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: scene.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`scene-card${selected ? " scene-card--selected" : ""}`}
      onClick={() => onSelect(scene)}
    >
      <div className="scene-drag-handle" {...attributes} {...listeners}>
        <span className="scene-position">#{position}</span>
        <span className="drag-icon">⠿</span>
      </div>
      <img
        className="scene-thumb"
        src={`/api/thumbnail/${scene.id}`}
        alt={`Scene ${scene.id}`}
        draggable={false}
      />
      <div className="scene-meta">
        <div className="scene-times">
          {fmt(scene.start_ts)} – {fmt(scene.end_ts)}
        </div>
        <div className="scene-desc">{scene.description}</div>
      </div>
    </div>
  );
}
