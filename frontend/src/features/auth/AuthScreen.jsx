import { useState } from 'react'
import { loginUser, registerUser } from '../../api/auth'


function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [account, setAccount] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isRegister = mode === 'register'

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (isRegister && password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }

    setLoading(true)
    try {
      const data = isRegister
        ? await registerUser({ username, email, password })
        : await loginUser({ account, password })
      onAuthenticated(data.user)
    } catch (err) {
      setError(err.message || '登录失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand">
          <h1>AI 文档学习助手</h1>
          <p>{isRegister ? '创建账号后保存你的学习进度' : '登录后继续你的文档学习'}</p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="登录方式">
          <button
            type="button"
            className={mode === 'login' ? 'active' : ''}
            onClick={() => {
              setMode('login')
              setError('')
            }}
          >
            登录
          </button>
          <button
            type="button"
            className={mode === 'register' ? 'active' : ''}
            onClick={() => {
              setMode('register')
              setError('')
            }}
          >
            注册
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {isRegister && (
            <label>
              <span>用户名</span>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                minLength={2}
                maxLength={128}
                required
              />
            </label>
          )}

          <label>
            <span>{isRegister ? '邮箱' : '账号或邮箱'}</span>
            <input
              type={isRegister ? 'email' : 'text'}
              value={isRegister ? email : account}
              onChange={e => {
                if (isRegister) setEmail(e.target.value)
                else setAccount(e.target.value)
              }}
              required
            />
          </label>

          <label>
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              minLength={isRegister ? 6 : 1}
              required
            />
          </label>

          {isRegister && (
            <label>
              <span>确认密码</span>
              <input
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                minLength={6}
                required
              />
            </label>
          )}

          {error && <div className="auth-error">{error}</div>}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? '处理中...' : isRegister ? '创建账号' : '登录'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default AuthScreen
