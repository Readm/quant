import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { AlertTriangle, Loader2 } from 'lucide-react'

// ── Load all .mmd files at build time ──────────────────────
const mermaidFiles: Record<string, string> = {}
try {
  const rawModules = import.meta.glob('../data/**/*.mmd', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>
  for (const [path, content] of Object.entries(rawModules)) {
    // path looks like: ../data/strategy/iteration_flow.mmd
    const key = path.replace(/^\.\.\/data\//, '').replace(/\.mmd$/, '')
    mermaidFiles[key] = content
  }
} catch (e) {
  console.warn('[MermaidDiagram] Failed to load .mmd files:', e)
}

// ── Props ──────────────────────────────────────────────────
interface MermaidDiagramProps {
  fileKey: string        // e.g. "strategy/iteration_flow"
  title: string
  className?: string
}

// ── Component ──────────────────────────────────────────────
export default function MermaidDiagram({ fileKey, title, className = '' }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const renderId = useRef(`mermaid-${Math.random().toString(36).slice(2, 9)}`)

  const raw = mermaidFiles[fileKey]

  useEffect(() => {
    if (!raw) {
      setStatus('error')
      setErrorMsg(`未找到 ${fileKey}.mmd`)
      return
    }

    let cancelled = false
    setStatus('loading')
    setErrorMsg('')

    ;(async () => {
      try {
        // Initialize mermaid once
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          themeVariables: {
            background: '#0f172a',
            primaryColor: '#6366f1',
            secondaryColor: '#1e293b',
            tertiaryColor: '#0f172a',
            mainBkg: '#1e293b',
            lineColor: '#475569',
            borderColor: '#334155',
            clusterBkg: '#0f172a',
            clusterBorder: '#334155',
            nodeBorder: '#475569',
            nodeTextColor: '#e2e8f0',
            titleColor: '#94a3b8',
            edgeLabelBackground: '#1e293b',
            edgeLabelColor: '#94a3b8',
          },
        })

        const { svg } = await mermaid.render(renderId.current, raw)

        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg
          setStatus('ready')
        }
      } catch (err: any) {
        if (!cancelled) {
          setStatus('error')
          setErrorMsg(err?.message || String(err))
        }
      }
    })()

    return () => { cancelled = true }
  }, [raw, fileKey])

  const borderColor = status === 'error' ? 'border-red-800/50' : 'border-slate-700'

  return (
    <div className={`bg-slate-800 rounded-xl p-5 border ${borderColor} ${className}`}>
      {/* Title */}
      {title && (
        <h3 className="text-white font-semibold mb-4 text-sm flex items-center gap-2">
          {status === 'error' ? (
            <AlertTriangle size={15} className="text-red-400" />
          ) : (
            <span className="w-2 h-2 rounded-full bg-indigo-400 inline-block" />
          )}
          {title}
        </h3>
      )}

      {/* Content area */}
      {status === 'loading' && (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <Loader2 size={20} className="animate-spin mr-2" />
          渲染中...
        </div>
      )}

      {status === 'error' && (
        <div className="bg-red-900/20 border border-red-800/30 rounded-lg p-4">
          <div className="text-red-400 text-xs font-medium mb-1">Mermaid 渲染失败</div>
          <pre className="text-[10px] text-slate-400 whitespace-pre-wrap font-mono leading-relaxed">{errorMsg}</pre>
        </div>
      )}

      {/* Mermaid SVG container */}
      <div
        ref={containerRef}
        className="mermaid-diagram-svg overflow-auto"
        style={{ minHeight: status === 'ready' ? undefined : 0 }}
      />
    </div>
  )
}
