import { useCallback, useRef, useState } from "react";

export default function UploadDropzone({ label, sublabel, onUpload, compact }) {
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState(null); // "uploading" | "error" | null
  const [message, setMessage] = useState("");
  const inputRef = useRef(null);

  const handleFile = useCallback(
    async (file) => {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (![".pdf", ".docx"].includes(ext)) {
        setStatus("error");
        setMessage("Only PDF and DOCX files are supported.");
        return;
      }
      setStatus("uploading");
      setMessage("");
      try {
        await onUpload(file);
        setStatus(null);
      } catch (err) {
        setStatus("error");
        setMessage(err.message || "Upload failed.");
      }
    },
    [onUpload]
  );

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onInputChange = (e) => {
    const file = e.target.files[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  return (
    <div>
      <div
        className={`upload-zone ${compact ? "compact" : ""} ${dragOver ? "drag-over" : ""}`}
        onClick={() => status !== "uploading" && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && status !== "uploading") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <input ref={inputRef} type="file" accept=".pdf,.docx" onChange={onInputChange} disabled={status === "uploading"} />
        <p className="upload-label">{status === "uploading" ? "Uploading…" : label}</p>
        <p>{sublabel}</p>
      </div>
      {status === "error" && (
        <div className="status-bar error" style={{ marginTop: "var(--fs-space-1)" }}>
          {message}
        </div>
      )}
    </div>
  );
}
