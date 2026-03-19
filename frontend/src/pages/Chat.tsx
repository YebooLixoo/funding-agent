import { useEffect, useState, useRef, useCallback } from 'react'
import { chatApi, type ChatMessage, type Action } from '../api/chat'

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(scrollToBottom, [messages])

  const fetchHistory = useCallback(async () => {
    if (!sessionId) return
    try {
      const res = await chatApi.history(sessionId)
      setMessages(res.data)
    } catch { /* ignore */ }
  }, [sessionId])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || sending) return

    const userMsg = input.trim()
    setInput('')
    setSending(true)

    // Optimistic: show user message immediately
    const tempMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      session_id: sessionId || '',
      role: 'user',
      content: userMsg,
      suggested_actions: null,
      actions_applied: false,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, tempMsg])

    try {
      const res = await chatApi.send(userMsg, sessionId)
      if (!sessionId) setSessionId(res.data.session_id)

      const assistantMsg: ChatMessage = {
        id: `resp-${Date.now()}`,
        session_id: res.data.session_id,
        role: 'assistant',
        content: res.data.reply,
        suggested_actions: res.data.suggested_actions,
        actions_applied: false,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev.filter(m => m.id !== tempMsg.id), tempMsg, assistantMsg])
    } catch {
      setMessages(prev => prev.filter(m => m.id !== tempMsg.id))
    } finally {
      setSending(false)
    }
  }

  const handleApplyActions = async (msgId: string) => {
    try {
      await chatApi.applyActions(msgId)
      setMessages(prev =>
        prev.map(m => m.id === msgId ? { ...m, actions_applied: true } : m)
      )
    } catch { /* ignore */ }
  }

  const handleNewSession = () => {
    setSessionId(undefined)
    setMessages([])
  }

  const renderActions = (actions: Action[]) => (
    <div className="mt-2 space-y-1">
      {actions.map((a, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className={`px-1.5 py-0.5 rounded font-medium ${
            a.type === 'add' ? 'bg-green-100 text-green-700' :
            a.type === 'remove' ? 'bg-red-100 text-red-700' :
            'bg-yellow-100 text-yellow-700'
          }`}>
            {a.type}
          </span>
          <span className="text-gray-700">{a.keyword}</span>
          <span className="text-gray-400">({a.category})</span>
        </div>
      ))}
    </div>
  )

  // Remove markdown JSON blocks from display text
  const cleanContent = (content: string) => {
    return content.replace(/```json[\s\S]*?```/g, '').trim()
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">AI Keyword Assistant</h1>
        <button
          onClick={handleNewSession}
          className="px-3 py-1.5 border border-gray-300 rounded-md text-sm hover:bg-gray-50"
        >
          New conversation
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-white rounded-lg shadow p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 py-12">
            <p className="text-lg mb-2">Chat with the AI to refine your keyword profile</p>
            <p className="text-sm">Try: "I'm interested in reinforcement learning for robotics"</p>
            <p className="text-sm">Or: "Remove anything related to biomedical research"</p>
            <p className="text-sm">Or: "Suggest keywords for autonomous driving research"</p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-[80%] rounded-lg px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-brand-600 text-white'
                : 'bg-gray-100 text-gray-900'
            }`}>
              <p className="text-sm whitespace-pre-wrap">{cleanContent(msg.content)}</p>
              {msg.suggested_actions?.actions && msg.suggested_actions.actions.length > 0 && (
                <div className="mt-3 bg-white rounded-md p-3 border border-gray-200">
                  <p className="text-xs font-semibold text-gray-600 mb-1">Suggested changes:</p>
                  {renderActions(msg.suggested_actions.actions)}
                  {!msg.actions_applied ? (
                    <button
                      onClick={() => handleApplyActions(msg.id)}
                      className="mt-2 px-3 py-1 bg-brand-600 text-white rounded text-xs font-medium hover:bg-brand-700"
                    >
                      Apply changes
                    </button>
                  ) : (
                    <p className="mt-2 text-xs text-green-600 font-medium">Changes applied!</p>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSend} className="mt-4 flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe your research interests or ask for keyword suggestions..."
          disabled={sending}
          className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="px-6 py-3 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50"
        >
          {sending ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  )
}
