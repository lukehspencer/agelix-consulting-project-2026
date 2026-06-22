import { useRef, useState } from 'react'
import { parseUploadedFile, downloadTemplate } from '../utils/dataParser'

export default function DataUpload({ onDataLoaded, onReset, uploadInfo }) {
  const fileRef = useRef(null)
  const [errors, setErrors] = useState(null)

  async function handleFile(e) {
    const file = e.target.files[0]
    if (!file) return
    fileRef.current.value = ''
    setErrors(null)

    const result = await parseUploadedFile(file)
    if (result.errors.length) {
      setErrors(result.errors)
      return
    }

    onDataLoaded(result.pumps, file.name)
  }

  function handleReset() {
    setErrors(null)
    onReset()
  }

  function handleTemplate(e) {
    e.preventDefault()
    downloadTemplate()
  }

  return (
    <section className="card upload-section">
      <div className="upload-row">
        <div className="upload-status">
          <h3 className="upload-title">Data Source</h3>
          <p className="upload-indicator">
            {uploadInfo
              ? <>Using uploaded data: <strong>{uploadInfo.filename}</strong> ({uploadInfo.count} pumps)</>
              : 'Using default data (optional: upload your own)'}
          </p>
        </div>
        <div className="upload-actions">
          <button className="btn-upload" onClick={() => fileRef.current.click()}>
            Upload Your Own Data
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".json,.csv"
            onChange={handleFile}
            hidden
          />
          {uploadInfo && (
            <button className="btn-reset" onClick={handleReset}>
              Reset to Default Data
            </button>
          )}
          <a href="#" className="template-link" onClick={handleTemplate}>
            Download Template
          </a>
        </div>
      </div>

      {errors && (
        <div className="upload-errors">
          <strong>Validation failed:</strong>
          <ul>
            {errors.map((err, i) => <li key={i}>{err}</li>)}
          </ul>
        </div>
      )}
    </section>
  )
}
