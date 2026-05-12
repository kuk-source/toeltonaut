import { getMetricsCsvUrl } from '../api/client'

interface Props {
  jobId: string
}

export default function VideoActions({ jobId }: Props) {
  return (
    <a
      href={getMetricsCsvUrl(jobId)}
      download
      aria-label="Analyse-Metriken als CSV herunterladen"
      className="text-geysirweiss/40 hover:text-geysirweiss/70 text-xs border border-geysirweiss/15 hover:border-geysirweiss/30 px-2 py-1 rounded-lg transition-colors"
    >
      CSV
    </a>
  )
}
