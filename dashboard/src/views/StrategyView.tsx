import { Presentation, Scale } from 'lucide-react'

export default function StrategyView() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <Presentation size={24} className="text-indigo-400" />
        <div>
          <h2 className="text-xl font-bold text-white">策略库</h2>
          <p className="text-slate-400 text-sm">
            策略迭代流程 · 评分标准
          </p>
        </div>
      </div>

      {/* Strategy iteration flow diagram */}
      <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
        <h3 className="text-white font-semibold mb-4 text-sm flex items-center gap-2">
          <Presentation size={15} className="text-indigo-400" />
          策略迭代流程
        </h3>
        <img src="./data/strategy/iteration_flow.svg" alt="策略迭代流程" className="w-full" />
      </div>

      {/* Scoring standards diagram */}
      <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
        <h3 className="text-white font-semibold mb-4 text-sm flex items-center gap-2">
          <Scale size={15} className="text-indigo-400" />
          评分标准
        </h3>
        <img src="./data/strategy/scoring_standards.svg" alt="评分标准" className="w-full" />
      </div>
    </div>
  )
}
