import { StrictMode, Component } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  componentDidCatch(error, errorInfo) {
    this.setState({
      hasError: true,
      error: error,
      errorInfo: errorInfo
    })
    console.error("React Render Error Caught:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 30, background: '#1a080c', color: '#ff809b',
          fontFamily: 'monospace', height: '100vh', overflow: 'auto',
          border: '3px solid #ff4d6a', boxSizing: 'border-box'
        }}>
          <h2>🚨 React Render Crash Caught</h2>
          <p><strong>Error:</strong> {this.state.error && this.state.error.toString()}</p>
          <pre style={{ background: '#2b0c12', padding: 15, borderRadius: 6, color: '#ffb3c1', whiteSpace: 'pre-wrap' }}>
            {this.state.errorInfo && this.state.errorInfo.componentStack}
          </pre>
          <button 
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px', background: '#ff4d6a', color: '#fff',
              border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 'bold'
            }}
          >
            🔄 Reload Page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
