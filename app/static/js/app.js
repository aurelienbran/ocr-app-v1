function OCRApp() {
    const [files, setFiles] = React.useState([]);
    const [uploading, setUploading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [processingStatus, setProcessingStatus] = React.useState('');
    
    React.useEffect(() => {
        fetchFiles();
        // Rafraîchir la liste toutes les 5 secondes
        const interval = setInterval(fetchFiles, 5000);
        return () => clearInterval(interval);
    }, []);

    const fetchFiles = async () => {
        try {
            const response = await fetch('/files');
            const data = await response.json();
            const groupedFiles = groupFilesByBaseName(data);
            setFiles(Object.entries(groupedFiles));
        } catch (err) {
            setError("Error loading files");
        }
    };

    const handleUpload = async (event) => {
        const file = event.target.files[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            setError("Please upload a PDF file");
            return;
        }

        setUploading(true);
        setError(null);
        setProcessingStatus('Uploading file...');
        const formData = new FormData();
        formData.append('file', file);

        try {
            setProcessingStatus(`Processing ${file.name}...`);
            const response = await fetch('/process', {
                method: 'POST',
                body: formData,
            });
            
            if (!response.ok) {
                throw new Error('Upload failed');
            }

            const result = await response.json();
            setProcessingStatus('Processing completed successfully!');
            await fetchFiles();
        } catch (err) {
            setError("Error processing file");
            setProcessingStatus('');
        } finally {
            setUploading(false);
            setTimeout(() => setProcessingStatus(''), 3000);
        }
    };

    const groupFilesByBaseName = (files) => {
        const groups = {};
        files.forEach(fileName => {
            const baseName = fileName.split('_')[0];
            if (!groups[baseName]) {
                groups[baseName] = [];
            }
            groups[baseName].push(fileName);
        });
        return groups;
    };

    const getFileTypeLabel = (fileName) => {
        if (fileName.endsWith('_results.json')) return 'Results (JSON)';
        if (fileName.endsWith('_text.txt')) return 'Text Content';
        if (fileName.endsWith('_summary.txt')) return 'Summary';
        return fileName;
    };

    return (
        <div className="min-h-screen bg-gray-50 py-8">
            <div className="max-w-3xl mx-auto bg-white rounded-lg shadow-sm">
                {/* Header */}
                <div className="p-6 border-b">
                    <h1 className="text-2xl font-semibold text-gray-800">TechnicIA OCR App</h1>
                    <p className="mt-2 text-sm text-gray-600">Upload your technical documents for OCR processing</p>
                </div>

                {/* Upload Zone */}
                <div className="p-6">
                    <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50 relative">
                        <div className="flex flex-col items-center justify-center pt-5 pb-6">
                            <svg className="w-8 h-8 mb-4 text-gray-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                            <p className="mb-2 text-sm text-gray-500">
                                <span className="font-semibold">Click to upload</span> or drag and drop
                            </p>
                            <p className="text-xs text-gray-500">PDF only</p>
                        </div>
                        <input
                            type="file"
                            className="hidden"
                            accept=".pdf"
                            onChange={handleUpload}
                            disabled={uploading}
                        />
                    </label>
                </div>

                {/* Status Messages */}
                {error && (
                    <div className="mx-6 p-4 mb-4 text-red-700 bg-red-100 rounded-lg">
                        {error}
                    </div>
                )}
                {uploading && (
                    <div className="mx-6 p-4 mb-4 text-blue-700 bg-blue-100 rounded-lg flex items-center">
                        <div className="w-4 h-4 border-2 border-t-blue-600 rounded-full animate-spin mr-2"></div>
                        {processingStatus || 'Processing... This may take a few minutes.'}
                    </div>
                )}

                {/* Files List */}
                <div className="p-6 border-t bg-gray-50">
                    <h2 className="text-lg font-medium text-gray-800 mb-4">Processed Files</h2>
                    <div className="space-y-4">
                        {files.length > 0 ? (
                            files.map(([baseName, groupFiles]) => (
                                <div key={baseName} className="bg-white rounded-lg border p-4">
                                    <div className="flex flex-col gap-2">
                                        <div className="font-medium text-gray-700 text-lg mb-2">{baseName}</div>
                                        <div className="flex flex-wrap gap-2">
                                            {groupFiles.sort().map(fileName => (
                                                <a
                                                    key={fileName}
                                                    href={`/files/${fileName}`}
                                                    className="inline-flex items-center px-3 py-1 text-sm rounded-md bg-blue-50 text-blue-600 hover:bg-blue-100"
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                >
                                                    <svg className="w-4 h-4 mr-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                                    </svg>
                                                    {getFileTypeLabel(fileName)}
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="text-center text-gray-500 py-4">
                                No processed files yet
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// Render the app
ReactDOM.render(<OCRApp />, document.getElementById('root'));