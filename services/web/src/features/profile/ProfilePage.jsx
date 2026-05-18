function ProfilePage({ user, onLogout }) {
  return (
    <div className="profile-page">
      <div className="profile-card">
        <div className="profile-avatar-lg">
          {(user?.username || user?.email || 'U').slice(0, 1).toUpperCase()}
        </div>
        <div className="profile-username">{user?.username || '—'}</div>
        <div className="profile-email">{user?.email}</div>
        <button type="button" className="profile-logout-btn" onClick={onLogout}>
          退出登录
        </button>
      </div>
    </div>
  )
}

export default ProfilePage
