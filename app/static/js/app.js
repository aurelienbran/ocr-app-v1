function OCRApp() {
    const [files, setFiles] = React.useState([]);
    const [uploading, setUploading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [processingStatus, setProcessingStatus] = React.useState('');
    const [deleteStatus, setDeleteStatus] = React.useState('');
    
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
            setFiles(groupedFiles);
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

    const handleDelete = async (directoryPath) => {
        if (!confirm("Are you sure you want to delete this document and all its files?")) {
            return;
        }
        try {
            setDeleteStatus(`Deleting files...`);
            const response = await fetch(`/files/${directoryPath}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Delete failed');
            }

            setDeleteStatus('Files deleted successfully');
            await fetchFiles();
        } catch (err) {
            setError("Error deleting files");
        } finally {
            setTimeout(() => setDeleteStatus(''), 3000);
        }
    };

    const groupFilesByBaseName = (files) => {
        const groups = {};
        files.forEach(file => {
            // Le répertoire est le premier niveau de regroupement
            const dirName = file.path.split('/')[0];
            if (!groups[dirName]) {
                groups[dirName] = {
                    files: [],
                    baseName: file.name.split('_')[0].split('.')[0]
                };
            }
            groups[dirName].files.push(file);
        });
        return groups;
    };

    const getFileTypeLabel = (fileName) => {
        if (fileName.endsWith('_results.json')) return 'Results (JSON)';
        if (fileName.endsWith('_text.txt')) return 'Text Content';
        if (fileName.endsWith('_summary.txt')) return 'Summary';
        return fileName;
    };

    const formatFileSize = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    };

    const downloadFile = (filePath) => {
        window.location.href = `/download/${filePath}`;
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
                {deleteStatus && (
                    <div className="mx-6 p-4 mb-4 text-green-700 bg-green-100 rounded-lg">
                        {deleteStatus}
                    </div>
                )}

                {/* Files List */}
                <div className="p-6 border-t bg-gray-50">
                    <h2 className="text-lg font-medium text-gray-800 mb-4">Processed Files</h2>
                    <div className="space-y-4">
                        {Object.entries(files).length > 0 ? (
                            Object.entries(files).map(([dirName, group]) => (
                                <div key={dirName} className="bg-white rounded-lg border p-4">
                                    <div className="flex flex-col gap-2">
                                        <div className="flex justify-between items-center mb-2">
                                            <div className="font-medium text-gray-700 text-lg">
                                                Document: {group.baseName}
                                            </div>
                                            <button
                                                onClick={() => handleDelete(dirName)}
                                                className="px-3 py-1 text-sm rounded-md bg-red-50 text-red-600 hover:bg-red-100 flex items-center"
                                            >
                                                <svg className="w-4 h-4 mr-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                                Delete
                                            </button>
                                        </div>
                                        <div className="space-y-2">
                                            {group.files.sort((a, b) => a.name.localeCompare(b.name)).map(file => (
                                                <div key={file.name} className="flex items-center justify-between bg-gray-50 p-2 rounded-lg">
                                                    <span className="text-sm text-gray-600">
                                                        {getFileTypeLabel(file.name)}
                                                    </span>
                                                    <div className="flex items-center gap-4">
                                                        <span className="text-xs text-gray-500">
                                                            {formatFileSize(file.size)}
                                                        </span>
                                                        <button
                                                            onClick={() => downloadFile(file.path)}
                                                            className="inline-flex items-center px-3 py-1 text-sm rounded-md bg-blue-50 text-blue-600 hover:bg-blue-100"
                                                        >
                                                            <svg className="w-4 h-4 mr-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                                            </svg>
                                                            Download
                                                        </button>
                                                    </div>
                                                </div>
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