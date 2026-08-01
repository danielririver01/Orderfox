function compressImageFile(file, maxSize = 1600, quality = 0.85) {
    return new Promise(function (resolve) {
        if (!file || !/^image\//.test(file.type)) {
            resolve(file);
            return;
        }
        const isStandardSmall = file.size < 500 * 1024 &&
            /^image\/(jpeg|png|webp)$/.test(file.type);
        if (isStandardSmall) {
            resolve(file);
            return;
        }
        const reader = new FileReader();
        reader.onload = function (e) {
            const img = new Image();
            img.onload = function () {
                let width = img.width;
                let height = img.height;
                if (width > maxSize || height > maxSize) {
                    const ratio = Math.min(maxSize / width, maxSize / height);
                    width = Math.round(width * ratio);
                    height = Math.round(height * ratio);
                }
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                canvas.toBlob(function (blob) {
                    if (blob) {
                        const base = (file.name || 'imagen').replace(/\.[^.]+$/, '') || 'imagen';
                        resolve(new File([blob], base + '.jpg', { type: 'image/jpeg' }));
                    } else {
                        resolve(file);
                    }
                }, 'image/jpeg', quality);
            };
            img.onerror = function () { resolve(file); };
            img.src = e.target.result;
        };
        reader.onerror = function () { resolve(file); };
        reader.readAsDataURL(file);
    });
}

function prepareImageUpload(input, onPreview) {
    if (!input.files || !input.files[0]) return;
    const original = input.files[0];
    compressImageFile(original).then(function (compressed) {
        if (compressed !== original) {
            try {
                const dt = new DataTransfer();
                dt.items.add(compressed);
                input.files = dt.files;
            } catch (err) {
                /* DataTransfer no soportado: se conserva el archivo original */
            }
        }
        if (onPreview && input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function (e) { onPreview(e.target.result); };
            reader.readAsDataURL(input.files[0]);
        }
    });
}
