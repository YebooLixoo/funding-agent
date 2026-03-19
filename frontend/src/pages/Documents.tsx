import { useEffect, useState, useCallback, useRef } from 'react'
import { documentsApi, type Document } from '../api/documents'
import { keywordsApi } from '../api/keywords'

export default function Documents() {
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [fileType, setFileType] = useState('resume')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const fetchDocs = useCallback(async () => {
    try {
      const res = await documentsApi.list()
      setDocs(res.data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  // Poll for processing status
  useEffect(() => {
    const processing = docs.some(d => d.upload_status === 'pending' || d.upload_status === 'processing')
    if (!processing) return
    const timer = setInterval(fetchDocs, 3000)
    return () => clearInterval(timer)
  }, [docs, fetchDocs])

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        await documentsApi.upload(file, fileType)
      }
      fetchDocs()
    } catch { /* ignore */ }
    finally { setUploading(false) }
  }

  const handleDelete = async (id: string) => {
    try {
      await documentsApi.remove(id)
      fetchDocs()
    } catch { /* ignore */ }
  }

  const handleAddKeywords = async (doc: Document) => {
    if (!doc.extracted_keywords) return
    const keywords: Array<{ keyword: string; category: string; source: string }> = []
    for (const [category, kws] of Object.entries(doc.extracted_keywords)) {
      if (category === 'summary' || category === 'error') continue
      if (!Array.isArray(kws)) continue
      for (const kw of kws) {
        keywords.push({ keyword: kw, category, source: 'document_extraction' })
      }
    }
    if (keywords.length > 0) {
      try {
        await keywordsApi.bulkAdd(keywords)
        alert(`Added ${keywords.length} keywords to your profile!`)
      } catch { /* ignore */ }
    }
  }

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800',
      processing: 'bg-blue-100 text-blue-800',
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
    }
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
        {status}
      </span>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Documents</h1>

      {/* Upload Zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragOver ? 'border-brand-500 bg-brand-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          handleUpload(e.dataTransfer.files)
        }}
      >
        <div className="space-y-3">
          <p className="text-gray-600">
            {uploading ? 'Uploading...' : 'Drag & drop your resume, CV, or papers here'}
          </p>
          <div className="flex items-center justify-center gap-3">
            <select
              value={fileType}
              onChange={(e) => setFileType(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-md text-sm"
            >
              <option value="resume">Resume</option>
              <option value="cv">CV</option>
              <option value="paper">Paper</option>
            </select>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="px-4 py-2 bg-brand-600 text-white rounded-md text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
            >
              Browse files
            </button>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt"
            multiple
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
          />
          <p className="text-xs text-gray-400">PDF or TXT, max 20MB</p>
        </div>
      </div>

      {/* Document List */}
      {loading ? (
        <div className="text-gray-500">Loading...</div>
      ) : docs.length === 0 ? (
        <div className="text-gray-500 text-center py-8">No documents uploaded yet.</div>
      ) : (
        <div className="space-y-4">
          {docs.map((doc) => (
            <div key={doc.id} className="bg-white shadow rounded-lg p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-sm font-semibold text-gray-900 truncate">{doc.filename}</h3>
                    {statusBadge(doc.upload_status)}
                    <span className="text-xs text-gray-500">{doc.file_type}</span>
                  </div>

                  {doc.upload_status === 'completed' && doc.extracted_keywords && (
                    <div className="space-y-2">
                      {Object.entries(doc.extracted_keywords).map(([cat, kws]) => {
                        if (cat === 'summary' || cat === 'error' || !Array.isArray(kws)) return null
                        return (
                          <div key={cat}>
                            <span className="text-xs font-medium text-gray-500 uppercase">{cat}:</span>
                            <div className="flex flex-wrap gap-1 mt-0.5">
                              {(kws as string[]).map((kw, i) => (
                                <span key={i} className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded-full text-xs">
                                  {kw}
                                </span>
                              ))}
                            </div>
                          </div>
                        )
                      })}
                      {doc.extracted_keywords.summary && typeof doc.extracted_keywords.summary === 'string' && (
                        <p className="text-sm text-gray-600 italic">{doc.extracted_keywords.summary}</p>
                      )}
                    </div>
                  )}

                  {doc.upload_status === 'failed' && doc.extracted_keywords?.error && (
                    <p className="text-sm text-red-600">Error: {String(doc.extracted_keywords.error)}</p>
                  )}
                </div>

                <div className="flex flex-col gap-2">
                  {doc.upload_status === 'completed' && doc.extracted_keywords && !doc.extracted_keywords.error && (
                    <button
                      onClick={() => handleAddKeywords(doc)}
                      className="px-3 py-1.5 bg-green-600 text-white rounded-md text-xs font-medium hover:bg-green-700"
                    >
                      Add to profile
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="px-3 py-1.5 border border-red-300 text-red-600 rounded-md text-xs font-medium hover:bg-red-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
