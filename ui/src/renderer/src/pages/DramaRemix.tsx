import { useState } from 'react'
import { api } from '../lib/api'

export default function DramaRemix(): JSX.Element {
  const [path, setPath] = useState('')
  const [title, setTitle] = useState('')
  const [captions, setCaptions] = useState(true)
  const [targetMin, setTargetMin] = useState(180)
  const [targetMax, setTargetMax] = useState(240)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const chooseVideo = async (): Promise<void> => {
    const picked = await window.studio.pickVideoFiles()
    if (!picked || picked.length === 0) return
    const p = picked[0]
    setPath(p)
    setTitle((p.split(/[\\/]/).pop() ?? p).replace(/\.[^.]+$/, ''))
    setError('')
  }

  const start = async (): Promise<void> => {
    if (!path || busy) return
    setBusy(true)
    setError('')
    try {
      await api.addLocalVideo({
        path,
        title,
        captions,
        force: true,
        drama: {
          target_min_seconds: targetMin,
          target_max_seconds: targetMax
        }
      })
      window.dispatchEvent(new Event('open-queue'))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const invalid = targetMin < 30 || targetMax <= targetMin || targetMax > 900

  return (
    <div className="p-6 max-w-4xl w-full space-y-5">
      <div>
        <h1 className="text-2xl font-bold">短剧一键二创</h1>
        <p className="text-sm text-muted mt-1">
          一条原片 → 自动压缩剧情 → 保持故事连续 → 9:16 → 字幕 → 只输出一条完整成片
        </p>
      </div>

      <div className="card space-y-5">
        <div>
          <p className="label mb-2">1. 选择原视频</p>
          <div className="flex items-center gap-3 flex-wrap">
            <button className="btn-accent" onClick={chooseVideo}>选择视频文件</button>
            <span className="text-sm text-muted break-all">
              {path ? (path.split(/[\\/]/).pop() ?? path) : '还没有选择视频'}
            </span>
          </div>
        </div>

        <div>
          <p className="label mb-2">2. 目标成片时长</p>
          <div className="flex items-center gap-2 text-sm">
            <input
              className="input !w-24"
              type="number"
              min={30}
              max={900}
              value={targetMin}
              onChange={(e) => setTargetMin(Number(e.target.value))}
            />
            <span>秒 ～</span>
            <input
              className="input !w-24"
              type="number"
              min={35}
              max={900}
              value={targetMax}
              onChange={(e) => setTargetMax(Number(e.target.value))}
            />
            <span className="text-muted">（默认 180～240 秒，也就是 3～4 分钟）</span>
          </div>
          {invalid && <p className="text-sm text-error mt-2">结束时长必须大于开始时长。</p>}
        </div>

        <div>
          <p className="label mb-2">3. 输出</p>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="size-4 accent-[#38BDF8]"
              checked={captions}
              onChange={(e) => setCaptions(e.target.checked)}
            />
            自动生成字幕
          </label>
          <p className="text-xs text-muted mt-2">
            输出固定为抖音竖屏 9:16。AI 会删掉重复、停顿和低价值镜头，但默认保持剧情时间顺序，避免把故事剪乱。
          </p>
        </div>

        <button
          className="btn-accent text-base px-6 py-3"
          disabled={!path || invalid || busy}
          onClick={start}
        >
          {busy ? '正在加入任务…' : '开始一键二创'}
        </button>

        {error && <div className="text-sm text-error break-words">{error}</div>}
      </div>

      <div className="card text-sm text-muted leading-6">
        <strong className="text-ink">这个模式只生成一条视频。</strong>
        {' '}不会像原来的 Clips Kitty 那样把一集拆成多个精彩片段。
      </div>
    </div>
  )
}
