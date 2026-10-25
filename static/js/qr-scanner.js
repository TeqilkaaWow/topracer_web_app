// QR-сканер через камеру телефона (jsQR библиотека)
class QRScanner {
    constructor(videoElement, canvasElement, onScan) {
        this.video = videoElement;
        this.canvas = canvasElement;
        this.context = canvasElement.getContext('2d');
        this.onScan = onScan;
        this.scanning = false;
        this.stream = null;
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment" }
            });
            this.video.srcObject = this.stream;
            this.video.setAttribute("playsinline", true);
            await this.video.play();
            this.scanning = true;
            requestAnimationFrame(this.tick.bind(this));
        } catch (err) {
            console.error("Камера ошибка:", err);
            alert("Не удалось получить доступ к камере");
        }
    }

    stop() {
        this.scanning = false;
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }
    }

    tick() {
        if (!this.scanning) return;

        if (this.video.readyState === this.video.HAVE_ENOUGH_DATA) {
            this.canvas.height = this.video.videoHeight;
            this.canvas.width = this.video.videoWidth;
            this.context.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);

            const imageData = this.context.getImageData(0, 0, this.canvas.width, this.canvas.height);

            // Используем jsQR (подключается отдельно)
            if (typeof jsQR !== 'undefined') {
                const code = jsQR(imageData.data, imageData.width, imageData.height);
                if (code) {
                    this.onScan(code.data);
                    this.stop();
                    return;
                }
            }
        }

        requestAnimationFrame(this.tick.bind(this));
    }
}

// Инициализация сканера на странице
document.addEventListener('DOMContentLoaded', () => {
    const scanBtn = document.getElementById('start-camera-scan');
    if (scanBtn) {
        const video = document.getElementById('qr-video');
        const canvas = document.getElementById('qr-canvas');

        const scanner = new QRScanner(video, canvas, async (data) => {
            // data - это URL или ID из QR
            const match = data.match(/\/admin\/scan\/(\d+)/);
            if (match) {
                const tracerdb_id = match[1];
                await fetch('/api/scan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({topRacerId: tracerdb_id})
                });
                alert('✅ Посещение засчитано!');
                window.location.reload();
            }
        });

        scanBtn.addEventListener('click', () => scanner.start());
    }
});