export default function Header({ user, onLogout }) {
  return (
    <header className="fs-header">
      <div className="fs-header-inner">
        <a
          href="https://fifthspace.com"
          target="_blank"
          rel="noopener noreferrer"
          className="fs-logo"
          aria-label="Fifth Space"
        >
          <img
            src="https://fifthspace.com/wp-content/uploads/Asset-1-1.svg"
            alt="Fifth Space"
            className="fs-logo-img"
          />
        </a>
        <div className="fs-header-right">
          <span className="fs-header-tag">Invoice Agent</span>
          {user && (
            <div className="fs-header-user">
              <span className="fs-header-email">{user.email}</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={onLogout}>
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
