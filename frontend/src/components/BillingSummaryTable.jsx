function fmt(n) {
  return `$${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function BillingSummaryTable({ summary }) {
  if (!summary || summary.rows.length === 0) {
    return (
      <div className="empty-state">
        <p>Upload a contract to build the billing sheet.</p>
      </div>
    );
  }

  return (
    <div className="billing-table-wrap">
      <table className="billing-table">
        <thead>
          <tr>
            <th>No.</th>
            <th>Cost Code</th>
            <th>Task Description</th>
            <th>Fee Type</th>
            <th>Contract Value</th>
            <th>Prior Billed</th>
            <th>Billed This Period</th>
            <th>Billed To Date</th>
            <th>% Billed</th>
            <th>Remaining</th>
          </tr>
        </thead>
        <tbody>
          {summary.rows.map((r) => (
            <tr key={r.task_number} className={!r.is_active ? "inactive" : ""}>
              <td>{r.task_number}</td>
              <td>{r.cost_code || "—"}</td>
              <td className="wrap">{r.description}</td>
              <td>{r.fee_type === "lump_sum" ? "Lump Sum" : "T&M"}</td>
              <td>{fmt(r.estimated_fee)}</td>
              <td>{fmt(r.prior_billed)}</td>
              <td>{fmt(r.billed_this_period)}</td>
              <td>{fmt(r.billed_to_date)}</td>
              <td className={`pct-cell ${r.flag_level || ""}`}>{(r.pct_billed * 100).toFixed(1)}%</td>
              <td>{fmt(r.remaining)}</td>
            </tr>
          ))}
          <tr className="total-row">
            <td colSpan={4}>CONTRACT TOTAL</td>
            <td>{fmt(summary.contract_total)}</td>
            <td />
            <td />
            <td>{fmt(summary.total_billed_to_date)}</td>
            <td />
            <td>{fmt(summary.total_remaining)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
