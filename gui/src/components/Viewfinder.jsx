import { useEffect, useRef } from "react";

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const sec = String(Math.floor(s % 60)).padStart(2, "0");
  const ms = String(Math.floor((s % 1) * 10));
  return `${m}:${sec}.${ms}`;
};

export default function Viewfinder({ scene }) {
  const videoRef = useRef(null);

  // When scene changes, seek to its start and play.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !scene) return;

    video.currentTime = scene.start_ts;
    video.play().catch(() => {});

    const onTimeUpdate = () => {
      if (video.currentTime >= scene.end_ts) {
        video.pause();
        video.currentTime = scene.start_ts;
      }
    };

    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, [scene]);

  return (
    <div className="viewfinder">
      <div className="viewfinder-player">
        <video
          ref={videoRef}
          src="/api/video"
          className="viewfinder-video"
          controls
          playsInline
        />
        {!scene && (
          <div className="viewfinder-empty">
            Click a scene to preview it
          </div>
        )}
      </div>

      {scene && (
        <div className="viewfinder-meta">
          <div className="viewfinder-header">
            <span className="viewfinder-id">Scene {scene.id}</span>
            <span className="viewfinder-ts">
              {fmt(scene.start_ts)} – {fmt(scene.end_ts)}
            </span>
          </div>
          <p className="viewfinder-desc">{scene.description}</p>
        </div>
      )}
    </div>
  );
}
