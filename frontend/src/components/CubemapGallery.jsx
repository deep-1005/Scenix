import { useEffect, useState } from "react";
import { listImages, API } from "../api";

export default function CubemapGallery({ jobId }) {
  const [images, setImages] = useState([]);

  useEffect(() => {
    if (!jobId) return;
    listImages(jobId).then((d) => setImages(d.images || []));
  }, [jobId]);

  if (images.length === 0)
    return <p className="muted">No cube faces yet for this scene.</p>;

  return (
    <div className="gallery">
      {images.map((src) => (
        <div className="thumb" key={src}>
          <img src={`${API}${src}`} alt="cube face" loading="lazy" />
          <span>{src.split("/").pop()}</span>
        </div>
      ))}
    </div>
  );
}
