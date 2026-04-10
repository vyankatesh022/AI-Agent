/**
 * Image Processing & Client-Side Compression Module
 * Handles client-side image validation, metadata extraction, off-screen canvas
 * resizing, quality compression, and data URL generation using pure Web APIs.
 */

import { CONFIG } from "./config.js";

class ImageService {
  /**
   * Validate file against supported MIME types and size constraints.
   * @param {File} file - Candidate file from input or drop.
   * @returns {{ valid: boolean, error?: string }}
   */
  validateFile(file) {
    if (!file) {
      return { valid: false, error: "No file selected." };
    }

    if (!file.type || !CONFIG.SUPPORTED_IMAGE_TYPES.includes(file.type)) {
      return {
        valid: false,
        error: `Unsupported image format (${file.type || "unknown"}). Allowed formats: JPEG, PNG, WebP.`,
      };
    }

    if (file.size <= 0) {
      return { valid: false, error: "Selected image file is empty (0 bytes)." };
    }

    if (file.size > CONFIG.MAX_IMAGE_SIZE_BYTES) {
      const maxMb = (CONFIG.MAX_IMAGE_SIZE_BYTES / (1024 * 1024)).toFixed(0);
      return {
        valid: false,
        error: `Image exceeds maximum allowed size of ${maxMb} MB. Please select a smaller image.`,
      };
    }

    return { valid: true };
  }

  /**
   * Safely decode image binary in the browser to verify readability and extract dimensions.
   * Defends against corrupted or spoofed files with automatic data-URL fallback.
   * @param {File|Blob} file - Validated image file.
   * @returns {Promise<HTMLImageElement>}
   */
  async decodeImage(file) {
    return new Promise((resolve, reject) => {
      let objectUrl = null;
      const img = new Image();

      const cleanup = () => {
        if (objectUrl) {
          try {
            URL.revokeObjectURL(objectUrl);
          } catch {
            // Ignore revocation errors
          }
        }
      };

      img.onload = () => {
        cleanup();
        if (img.naturalWidth === 0 || img.naturalHeight === 0) {
          reject(new Error("Image has zero resolution or is corrupted."));
        } else {
          resolve(img);
        }
      };

      img.onerror = () => {
        cleanup();
        // Fallback: try reading via FileReader data URL in case object URL was blocked by browser sandbox
        this.fileToDataUrl(file)
          .then((dataUrl) => {
            const fallbackImg = new Image();
            fallbackImg.onload = () => {
              if (fallbackImg.naturalWidth === 0 || fallbackImg.naturalHeight === 0) {
                reject(new Error("Image has zero resolution or is corrupted."));
              } else {
                resolve(fallbackImg);
              }
            };
            fallbackImg.onerror = () => {
              reject(new Error("Failed to decode image. File may be corrupted or disguised."));
            };
            fallbackImg.src = dataUrl;
          })
          .catch(() => {
            reject(new Error("Failed to decode image. File may be corrupted or disguised."));
          });
      };

      try {
        objectUrl = URL.createObjectURL(file);
        img.src = objectUrl;
      } catch {
        this.fileToDataUrl(file)
          .then((dataUrl) => {
            img.src = dataUrl;
          })
          .catch((err) => {
            reject(err);
          });
      }
    });
  }

  /**
   * Extract comprehensive metadata from an image file.
   * @param {File} file - Image file.
   * @returns {Promise<object>} Image metadata.
   */
  async getImageMetadata(file) {
    const validation = this.validateFile(file);
    if (!validation.valid) {
      throw new Error(validation.error);
    }

    const img = await this.decodeImage(file);
    return {
      file,
      name: file.name,
      type: file.type,
      size: file.size,
      sizeFormatted: this.formatBytes(file.size),
      width: img.naturalWidth,
      height: img.naturalHeight,
      aspectRatio: img.naturalWidth / img.naturalHeight,
    };
  }

  /**
   * Determine whether compression/optimization is recommended for the image.
   * @param {object} metadata - Metadata from getImageMetadata.
   * @returns {boolean}
   */
  shouldCompress(metadata) {
    if (!metadata) return false;
    return (
      metadata.size > CONFIG.IMAGE_COMPRESSION_THRESHOLD_BYTES ||
      metadata.width > CONFIG.MAX_IMAGE_DIMENSION ||
      metadata.height > CONFIG.MAX_IMAGE_DIMENSION
    );
  }

  /**
   * Calculate proportional dimensions maintaining aspect ratio. Never upscales.
   * @param {number} originalWidth - Source width.
   * @param {number} originalHeight - Source height.
   * @param {number} [maxDimension=CONFIG.MAX_IMAGE_DIMENSION] - Maximum allowed dimension.
   * @returns {{ width: number, height: number, scaled: boolean }}
   */
  calculateDimensions(originalWidth, originalHeight, maxDimension = CONFIG.MAX_IMAGE_DIMENSION) {
    if (originalWidth <= maxDimension && originalHeight <= maxDimension) {
      return {
        width: originalWidth,
        height: originalHeight,
        scaled: false,
      };
    }

    const scale = Math.min(maxDimension / originalWidth, maxDimension / originalHeight);
    return {
      width: Math.max(1, Math.round(originalWidth * scale)),
      height: Math.max(1, Math.round(originalHeight * scale)),
      scaled: true,
    };
  }

  /**
   * Detect whether a canvas has transparent pixels (relevant for PNGs).
   * @private
   */
  _hasTransparency(ctx, width, height) {
    try {
      // Sample up to 1000 pixels across the canvas for transparency
      const stepX = Math.max(1, Math.floor(width / 32));
      const stepY = Math.max(1, Math.floor(height / 32));
      for (let y = 0; y < height; y += stepY) {
        for (let x = 0; x < width; x += stepX) {
          const pixel = ctx.getImageData(x, y, 1, 1).data;
          if (pixel[3] < 250) {
            return true;
          }
        }
      }
    } catch {
      // If getImageData fails due to security restrictions, assume transparency to be safe
      return true;
    }
    return false;
  }

  /**
   * Compress and resize an image file using browser-native Canvas APIs.
   * @param {File} file - Original image file.
   * @param {object} [options={}] - Optional compression parameters.
   * @returns {Promise<object>} Compression result details with optimized File.
   */
  async compressImage(file, options = {}) {
    const startTime = performance.now();
    const maxDimension = options.maxDimension || CONFIG.MAX_IMAGE_DIMENSION;
    const quality = options.quality !== undefined ? options.quality : CONFIG.IMAGE_COMPRESSION_QUALITY;

    const img = await this.decodeImage(file);
    const { width, height } = this.calculateDimensions(img.naturalWidth, img.naturalHeight, maxDimension);

    // Create offscreen canvas for rendering
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) {
      throw new Error("Unable to create canvas 2D rendering context.");
    }

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    // Handle background and target MIME type
    let targetMime = file.type;
    let extension = file.name.split(".").pop() || "jpg";

    if (file.type === "image/png") {
      // Check if PNG has transparent regions
      ctx.drawImage(img, 0, 0, width, height);
      const isTransparent = this._hasTransparency(ctx, width, height);

      if (isTransparent) {
        // Preserve PNG to protect alpha transparency (logos, diagrams)
        targetMime = "image/png";
      } else {
        // If completely opaque, convert to JPEG for significant payload reduction
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);
        targetMime = "image/jpeg";
        extension = "jpg";
      }
    } else {
      if (file.type === "image/jpeg") {
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(0, 0, width, height);
      }
      ctx.drawImage(img, 0, 0, width, height);
    }

    // Convert canvas to Blob
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(
        (b) => {
          if (b) resolve(b);
          else reject(new Error("Canvas blob conversion failed."));
        },
        targetMime,
        targetMime === "image/png" ? undefined : quality
      );
    });

    // Generate output filename preserving base name
    const baseName = file.name.substring(0, file.name.lastIndexOf(".")) || file.name;
    const optimizedFileName = `${baseName}.${extension}`;

    const optimizedFile = new File([blob], optimizedFileName, {
      type: targetMime,
      lastModified: Date.now(),
    });

    const durationMs = Math.round(performance.now() - startTime);
    const originalBytes = file.size;
    const compressedBytes = optimizedFile.size;
    const savedBytes = Math.max(0, originalBytes - compressedBytes);
    const reductionPercent =
      originalBytes > 0 ? Math.round(((originalBytes - compressedBytes) / originalBytes) * 100) : 0;

    return {
      file: optimizedFile,
      originalSize: originalBytes,
      originalFormatted: this.formatBytes(originalBytes),
      compressedSize: compressedBytes,
      compressedFormatted: this.formatBytes(compressedBytes),
      savedBytes,
      savedFormatted: this.formatBytes(savedBytes),
      reductionPercent: Math.max(0, reductionPercent),
      width,
      height,
      originalWidth: img.naturalWidth,
      originalHeight: img.naturalHeight,
      mimeType: targetMime,
      durationMs,
    };
  }

  /**
   * Convert File or Blob to standard base64 Data URL.
   * @param {File|Blob} file - Target file.
   * @returns {Promise<string>} Data URL string (data:image/...;base64,...).
   */
  async fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("Failed to read image file into data URL."));
      reader.readAsDataURL(file);
    });
  }

  /**
   * Human-readable byte formatting.
   * @param {number} bytes - Number of bytes.
   * @param {number} [decimals=1] - Decimal precision.
   * @returns {string} Formatted string (e.g. '4.8 MB').
   */
  formatBytes(bytes, decimals = 1) {
    if (bytes <= 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const val = parseFloat((bytes / Math.pow(k, i)).toFixed(decimals));
    return `${val} ${sizes[i]}`;
  }
}

export const imageService = new ImageService();
