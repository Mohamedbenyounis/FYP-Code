# ENROLLMENT_UI_LOG.md
## Iteration 13: Guided Multi-Pose Enrollment

### Architecture
We refactored the enrollment workflow to support **Atomic Batch Enrollment**. The system now processes batches of images in memory, rejecting the entire payload unless a configurable `min_captures=3` threshold of high-quality face profiles is validated. 

### Two Operating Modes

1. **Upload Mode**: Operates exactly as previous iterations. The standard HTML file input was upgraded with the `multiple` attribute, allowing users to select several images simultaneously from disk.
2. **WebCamera Guided Mode**: Uses HTML5 `<video>` and `navigator.mediaDevices` bound to a vanilla Javascript state machine. It prompts users to present 5 distinct angles (Center, Left, Right, Up, Down).

### Constraints & Limitations
- **Browser Security**: Modern browsers restrict camera access across standard HTTP to only `localhost` or `127.0.0.1`. When deploying to a network server, it MUST run behind HTTPS or a Reverse Proxy (like NGINX bounding port 443) or the browser will block the webcam.
- **Blob Payload Transfer**: Standard canvas `.toDataURL()` extraction yields massive base64 text strings capable of exceeding standard web server thresholds. We compress images strictly using `canvas.toBlob('image/jpeg', 0.85)` and bundle them natively into FormData before transit.

### DB Mechanics
The `SQLitePersonRepository` and `SQLiteEmbeddingRepository` were already built with scale in mind. Rather than uploading 1 vector, the backend saves 3-5 vectors instantaneously, using them mathematically to synthesize a superior, median-averaged biometric template.
