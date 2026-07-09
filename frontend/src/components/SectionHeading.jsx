export default function SectionHeading({ label, number }) {
  return (
    <div className="fs-section-heading">
      <svg className="fs-dot" xmlns="http://www.w3.org/2000/svg" width="6" height="6" viewBox="0 0 6 6" fill="none" aria-hidden="true">
        <circle cx="3" cy="3" r="3" fill="currentColor" />
      </svg>
      {number != null && <span className="fs-section-number">{String(number).padStart(2, "0")}</span>}
      <h2 className="fs-section-label">{label}</h2>
    </div>
  );
}
