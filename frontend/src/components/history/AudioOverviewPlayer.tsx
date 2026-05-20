import { useEffect, useRef, useState, type SyntheticEvent } from 'react'
import type { AudioOverviewDocument } from '../../types'
import type { AudioOverviewUrl } from '../../services/audioOverviewService'

const AUDIO_URL_REFRESH_WINDOW_MS = 60_000

export interface AudioPlaybackState {
  currentTime: number
  duration: number | null
  playing: boolean
}

interface AudioOverviewPlayerProps {
  document: AudioOverviewDocument
  className?: string
  onRefreshAudioUrl?: (document: AudioOverviewDocument) => Promise<AudioOverviewUrl | null>
  playbackState?: AudioPlaybackState
  activePlayerId?: string | null
  playerId?: string
  onPlaybackStateChange?: (documentId: string, state: AudioPlaybackState) => void
  onActivePlayerChange?: (playerId: string | null) => void
}

export function AudioOverviewPlayer({
  document,
  className,
  onRefreshAudioUrl,
  playbackState,
  activePlayerId,
  playerId = document.id,
  onPlaybackStateChange,
  onActivePlayerChange,
}: AudioOverviewPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const refreshingRef = useRef(false)
  const skipTimeReportRef = useRef(false)
  const [refreshing, setRefreshing] = useState(false)
  const [localAudio, setLocalAudio] = useState<(AudioOverviewUrl & { id: string }) | null>(null)
  const currentAudio = localAudio?.id === document.id ? localAudio : null
  const audioUrl = currentAudio?.audioUrl ?? document.audioUrl ?? ''
  const expiresAt = currentAudio?.expiresAt ?? document.audioUrlExpiresAt ?? 0
  const isActivePlayer = !activePlayerId || activePlayerId === playerId

  useEffect(() => {
    const audioElement = audioRef.current
    if (!audioElement || !playbackState) {
      return
    }

    if (Math.abs(audioElement.currentTime - playbackState.currentTime) > 1) {
      skipTimeReportRef.current = true
      try {
        audioElement.currentTime = playbackState.currentTime
      } catch {
        skipTimeReportRef.current = false
      }
    }

    if (playbackState.playing && isActivePlayer) {
      if (audioElement.paused) {
        void audioElement.play().catch(() => undefined)
      }
      return
    }

    if (!isActivePlayer || !playbackState.playing) {
      audioElement.pause()
    }
  }, [isActivePlayer, playbackState])

  const reportPlaybackState = (audioElement: HTMLAudioElement, playing: boolean) => {
    onPlaybackStateChange?.(document.id, {
      currentTime: audioElement.currentTime,
      duration: Number.isFinite(audioElement.duration) ? audioElement.duration : null,
      playing,
    })
  }

  if (document.status !== 'completed' || (!audioUrl && !onRefreshAudioUrl)) {
    return null
  }

  const handlePlay = async (event: SyntheticEvent<HTMLAudioElement>) => {
    onActivePlayerChange?.(playerId)
    const shouldRefresh = !audioUrl || !expiresAt || expiresAt - Date.now() <= AUDIO_URL_REFRESH_WINDOW_MS
    if (!onRefreshAudioUrl || !shouldRefresh || refreshingRef.current) {
      reportPlaybackState(event.currentTarget, true)
      return
    }

    const audioElement = event.currentTarget
    const resumeAt = audioElement.currentTime
    audioElement.pause()
    refreshingRef.current = true
    setRefreshing(true)

    try {
      const refreshedAudio = await onRefreshAudioUrl(document)
      if (!refreshedAudio) {
        return
      }

      setLocalAudio({ ...refreshedAudio, id: document.id })
      if (audioRef.current) {
        audioRef.current.src = refreshedAudio.audioUrl
        try {
          audioRef.current.currentTime = resumeAt
        } catch {
          audioRef.current.currentTime = 0
        }
        await audioRef.current.play().catch(() => undefined)
        reportPlaybackState(audioRef.current, true)
      }
    } finally {
      refreshingRef.current = false
      setRefreshing(false)
    }
  }

  return (
    <audio
      ref={audioRef}
      controls
      preload="metadata"
      src={audioUrl || undefined}
      onPlay={(event) => {
        void handlePlay(event)
      }}
      onPause={(event) => {
        if (activePlayerId && activePlayerId !== playerId) {
          return
        }
        reportPlaybackState(event.currentTarget, false)
        if (activePlayerId === playerId) {
          onActivePlayerChange?.(null)
        }
      }}
      onEnded={(event) => {
        if (activePlayerId && activePlayerId !== playerId) {
          return
        }
        reportPlaybackState(event.currentTarget, false)
        if (activePlayerId === playerId) {
          onActivePlayerChange?.(null)
        }
      }}
      onTimeUpdate={(event) => {
        if (activePlayerId && activePlayerId !== playerId) {
          return
        }
        if (skipTimeReportRef.current) {
          skipTimeReportRef.current = false
          return
        }
        reportPlaybackState(event.currentTarget, !event.currentTarget.paused)
      }}
      onLoadedMetadata={(event) => {
        if (playbackState && Math.abs(event.currentTarget.currentTime - playbackState.currentTime) > 1) {
          try {
            event.currentTarget.currentTime = playbackState.currentTime
          } catch {
            // The browser can reject seeking before enough media data is available.
          }
        }
        if (activePlayerId && activePlayerId !== playerId) {
          return
        }
        reportPlaybackState(event.currentTarget, !event.currentTarget.paused)
      }}
      className={className}
      aria-busy={refreshing || undefined}
    />
  )
}
