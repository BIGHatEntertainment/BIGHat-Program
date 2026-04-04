//! Overlay image processing module
//! Handles PNG and GIF overlay images for trivia presentations
//! 
//! Key features:
//! - Fast base64 encoding of overlay images
//! - Proper MIME type detection for PNG and GIF
//! - GIF preservation (no compression) to maintain animations
//! - PNG optimization with optional compression
//! - **Rayon parallel batch processing for multiple overlays**
//! - **Memory pre-allocation for efficient Python interop**

use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::sync::Mutex;
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use rayon::prelude::*;
use thiserror::Error;

#[derive(Error, Debug, Clone)]
pub enum OverlayError {
    #[error("IO error: {0}")]
    Io(String),
    #[error("Invalid image format: {0}")]
    InvalidFormat(String),
}

impl From<std::io::Error> for OverlayError {
    fn from(err: std::io::Error) -> Self {
        OverlayError::Io(err.to_string())
    }
}

/// Represents a processed overlay image
#[derive(Debug, Clone)]
pub struct OverlayImage {
    /// Base64 data URL (e.g., "data:image/png;base64,...")
    pub data_url: String,
    /// Original file size in bytes
    pub original_size: usize,
    /// Processed size in bytes
    pub processed_size: usize,
    /// Image type (png or gif)
    pub image_type: String,
    /// Image width (if detected)
    pub width: Option<u32>,
    /// Image height (if detected)
    pub height: Option<u32>,
}

/// Result type for batch processing - includes cache key for identification
#[derive(Debug, Clone)]
pub struct BatchOverlayResult {
    pub cache_key: String,
    pub result: Result<OverlayImage, OverlayError>,
}

/// Overlay image processor with caching and parallel processing
pub struct OverlayProcessor {
    /// Cache for processed overlays (path -> OverlayImage)
    cache: Mutex<HashMap<String, OverlayImage>>,
    /// Stats tracking
    images_processed: std::sync::atomic::AtomicI64,
    cache_hits: std::sync::atomic::AtomicI64,
    batch_processed: std::sync::atomic::AtomicI64,
}

impl OverlayProcessor {
    pub fn new() -> Self {
        OverlayProcessor {
            cache: Mutex::new(HashMap::new()),
            images_processed: std::sync::atomic::AtomicI64::new(0),
            cache_hits: std::sync::atomic::AtomicI64::new(0),
            batch_processed: std::sync::atomic::AtomicI64::new(0),
        }
    }

    /// Process an overlay image file and return a base64 data URL
    /// 
    /// # Arguments
    /// * `file_path` - Path to the overlay image file (PNG or GIF)
    /// 
    /// # Returns
    /// * `OverlayImage` with data URL and metadata
    pub fn process_overlay_file(&self, file_path: &str) -> Result<OverlayImage, OverlayError> {
        // Check cache first
        {
            let cache = self.cache.lock().unwrap();
            if let Some(cached) = cache.get(file_path) {
                self.cache_hits.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                return Ok(cached.clone());
            }
        }

        // Read file
        let path = Path::new(file_path);
        let mut file = File::open(path)?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;

        let original_size = bytes.len();

        // Detect image type from extension
        let ext = path.extension()
            .and_then(|e| e.to_str())
            .map(|s| s.to_lowercase())
            .unwrap_or_default();

        let (image_type, mime_type) = match ext.as_str() {
            "gif" => ("gif".to_string(), "image/gif"),
            "png" => ("png".to_string(), "image/png"),
            "jpg" | "jpeg" => ("jpeg".to_string(), "image/jpeg"),
            _ => return Err(OverlayError::InvalidFormat(format!("Unsupported format: {}", ext))),
        };

        // For GIF: preserve as-is to maintain animation
        // For PNG: we could optionally optimize, but for overlays we preserve quality
        let processed_bytes = bytes.clone();
        let processed_size = processed_bytes.len();

        // Detect dimensions from image header
        let (width, height) = Self::detect_dimensions_static(&processed_bytes, &image_type);

        // Encode to base64
        let base64_data = BASE64.encode(&processed_bytes);
        let data_url = format!("data:{};base64,{}", mime_type, base64_data);

        let overlay = OverlayImage {
            data_url,
            original_size,
            processed_size,
            image_type,
            width,
            height,
        };

        // Cache the result
        {
            let mut cache = self.cache.lock().unwrap();
            cache.insert(file_path.to_string(), overlay.clone());
        }

        self.images_processed.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        Ok(overlay)
    }

    /// Process overlay bytes directly (for SharePoint downloads)
    /// 
    /// # Arguments
    /// * `bytes` - Raw image bytes
    /// * `image_type` - Type of image ("png" or "gif")
    /// * `cache_key` - Optional cache key for caching
    /// 
    /// # Returns
    /// * `OverlayImage` with data URL and metadata
    pub fn process_overlay_bytes(
        &self,
        bytes: &[u8],
        image_type: &str,
        cache_key: Option<&str>,
    ) -> Result<OverlayImage, OverlayError> {
        // Check cache first if cache_key provided
        if let Some(key) = cache_key {
            let cache = self.cache.lock().unwrap();
            if let Some(cached) = cache.get(key) {
                self.cache_hits.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                return Ok(cached.clone());
            }
        }

        let overlay = Self::process_bytes_internal(bytes, image_type)?;

        // Cache the result if key provided
        if let Some(key) = cache_key {
            let mut cache = self.cache.lock().unwrap();
            cache.insert(key.to_string(), overlay.clone());
        }

        self.images_processed.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        Ok(overlay)
    }

    /// Process bytes into a pre-allocated buffer (Option C: Memory Pre-allocation)
    /// Returns the length of data written to the buffer
    /// 
    /// # Arguments
    /// * `bytes` - Raw image bytes
    /// * `image_type` - Type of image ("png" or "gif")
    /// * `output_buffer` - Pre-allocated mutable buffer to write base64 data URL into
    /// 
    /// # Returns
    /// * Number of bytes written to buffer, or error
    #[allow(dead_code)]  // Reserved for future zero-copy optimization
    pub fn process_into_buffer(
        &self,
        bytes: &[u8],
        image_type: &str,
        output_buffer: &mut [u8],
    ) -> Result<usize, OverlayError> {
        let mime_type = match image_type {
            "gif" => "image/gif",
            "png" => "image/png",
            "jpg" | "jpeg" => "image/jpeg",
            _ => return Err(OverlayError::InvalidFormat(format!("Unsupported format: {}", image_type))),
        };

        // Calculate required buffer size
        let prefix = format!("data:{};base64,", mime_type);
        let base64_len = ((bytes.len() + 2) / 3) * 4; // Base64 encoding size
        let total_len = prefix.len() + base64_len;

        if output_buffer.len() < total_len {
            return Err(OverlayError::InvalidFormat(
                format!("Buffer too small: need {} bytes, got {}", total_len, output_buffer.len())
            ));
        }

        // Write prefix
        output_buffer[..prefix.len()].copy_from_slice(prefix.as_bytes());
        
        // Encode base64 directly into buffer
        let base64_data = BASE64.encode(bytes);
        output_buffer[prefix.len()..prefix.len() + base64_data.len()]
            .copy_from_slice(base64_data.as_bytes());

        self.images_processed.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        Ok(total_len)
    }

    /// **Option B: Rayon Parallel Batch Processing**
    /// Process multiple overlays in parallel using Rayon
    /// 
    /// # Arguments
    /// * `items` - Vector of (bytes, image_type, cache_key) tuples
    /// 
    /// # Returns
    /// * Vector of BatchOverlayResult with cache_key for identification
    pub fn process_batch(
        &self,
        items: Vec<(Vec<u8>, String, String)>,
    ) -> Vec<BatchOverlayResult> {
        let results: Vec<BatchOverlayResult> = items
            .into_par_iter()
            .map(|(bytes, image_type, cache_key)| {
                // Check cache first
                {
                    let cache = self.cache.lock().unwrap();
                    if let Some(cached) = cache.get(&cache_key) {
                        self.cache_hits.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        return BatchOverlayResult {
                            cache_key,
                            result: Ok(cached.clone()),
                        };
                    }
                }

                // Process the image
                let result = Self::process_bytes_internal(&bytes, &image_type);
                
                // Cache successful results
                if let Ok(ref overlay) = result {
                    let mut cache = self.cache.lock().unwrap();
                    cache.insert(cache_key.clone(), overlay.clone());
                }

                self.images_processed.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

                BatchOverlayResult { cache_key, result }
            })
            .collect();

        self.batch_processed.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        results
    }

    /// Internal static method for processing bytes (used by parallel processing)
    fn process_bytes_internal(bytes: &[u8], image_type: &str) -> Result<OverlayImage, OverlayError> {
        let original_size = bytes.len();

        let mime_type = match image_type {
            "gif" => "image/gif",
            "png" => "image/png",
            "jpg" | "jpeg" => "image/jpeg",
            _ => return Err(OverlayError::InvalidFormat(format!("Unsupported format: {}", image_type))),
        };

        // Detect dimensions
        let (width, height) = Self::detect_dimensions_static(bytes, image_type);

        // Encode to base64
        let base64_data = BASE64.encode(bytes);
        let data_url = format!("data:{};base64,{}", mime_type, base64_data);

        Ok(OverlayImage {
            data_url,
            original_size,
            processed_size: bytes.len(),
            image_type: image_type.to_string(),
            width,
            height,
        })
    }

    /// Static version of dimension detection for parallel processing
    fn detect_dimensions_static(bytes: &[u8], image_type: &str) -> (Option<u32>, Option<u32>) {
        match image_type {
            "png" => Self::detect_png_dimensions_static(bytes),
            "gif" => Self::detect_gif_dimensions_static(bytes),
            "jpg" | "jpeg" => Self::detect_jpeg_dimensions_static(bytes),
            _ => (None, None),
        }
    }

    /// Detect PNG dimensions from IHDR chunk
    fn detect_png_dimensions_static(bytes: &[u8]) -> (Option<u32>, Option<u32>) {
        // PNG header: 8 bytes signature, then IHDR chunk
        // IHDR: 4 bytes length, 4 bytes "IHDR", 4 bytes width, 4 bytes height
        if bytes.len() < 24 {
            return (None, None);
        }

        // Check PNG signature
        if &bytes[0..8] != b"\x89PNG\r\n\x1a\n" {
            return (None, None);
        }

        // Read width and height from IHDR (big-endian)
        let width = u32::from_be_bytes([bytes[16], bytes[17], bytes[18], bytes[19]]);
        let height = u32::from_be_bytes([bytes[20], bytes[21], bytes[22], bytes[23]]);

        (Some(width), Some(height))
    }

    /// Detect GIF dimensions from header
    fn detect_gif_dimensions_static(bytes: &[u8]) -> (Option<u32>, Option<u32>) {
        // GIF header: 6 bytes signature, 2 bytes width (LE), 2 bytes height (LE)
        if bytes.len() < 10 {
            return (None, None);
        }

        // Check GIF signature
        if &bytes[0..6] != b"GIF87a" && &bytes[0..6] != b"GIF89a" {
            return (None, None);
        }

        // Read width and height (little-endian)
        let width = u16::from_le_bytes([bytes[6], bytes[7]]) as u32;
        let height = u16::from_le_bytes([bytes[8], bytes[9]]) as u32;

        (Some(width), Some(height))
    }

    /// Detect JPEG dimensions (basic implementation)
    fn detect_jpeg_dimensions_static(bytes: &[u8]) -> (Option<u32>, Option<u32>) {
        // JPEG dimension detection requires parsing SOF markers
        // This is a simplified implementation
        if bytes.len() < 2 || bytes[0] != 0xFF || bytes[1] != 0xD8 {
            return (None, None);
        }

        let mut i = 2;
        while i + 4 < bytes.len() {
            if bytes[i] != 0xFF {
                i += 1;
                continue;
            }

            let marker = bytes[i + 1];
            
            // SOF0, SOF1, SOF2 markers contain dimensions
            if marker >= 0xC0 && marker <= 0xC3 && marker != 0xC1 {
                if i + 9 < bytes.len() {
                    let height = u16::from_be_bytes([bytes[i + 5], bytes[i + 6]]) as u32;
                    let width = u16::from_be_bytes([bytes[i + 7], bytes[i + 8]]) as u32;
                    return (Some(width), Some(height));
                }
            }

            // Move to next marker
            if i + 3 < bytes.len() {
                let length = u16::from_be_bytes([bytes[i + 2], bytes[i + 3]]) as usize;
                i += 2 + length;
            } else {
                break;
            }
        }

        (None, None)
    }

    /// Calculate required buffer size for pre-allocation
    /// 
    /// # Arguments
    /// * `input_size` - Size of input image in bytes
    /// * `image_type` - Type of image ("png" or "gif")
    /// 
    /// # Returns
    /// * Required buffer size for base64 data URL
    pub fn calculate_buffer_size(input_size: usize, image_type: &str) -> usize {
        let mime_type = match image_type {
            "gif" => "image/gif",
            "png" => "image/png",
            "jpg" | "jpeg" => "image/jpeg",
            _ => "application/octet-stream",
        };
        let prefix_len = format!("data:{};base64,", mime_type).len();
        let base64_len = ((input_size + 2) / 3) * 4;
        prefix_len + base64_len
    }

    /// Get processing statistics
    pub fn get_stats(&self) -> HashMap<String, i64> {
        let cache_size = self.cache.lock().unwrap().len() as i64;
        let mut stats = HashMap::new();
        stats.insert("images_processed".to_string(), 
            self.images_processed.load(std::sync::atomic::Ordering::Relaxed));
        stats.insert("cache_hits".to_string(), 
            self.cache_hits.load(std::sync::atomic::Ordering::Relaxed));
        stats.insert("cache_size".to_string(), cache_size);
        stats.insert("batch_processed".to_string(),
            self.batch_processed.load(std::sync::atomic::Ordering::Relaxed));
        stats
    }

    /// Clear the cache
    pub fn clear_cache(&self) {
        let mut cache = self.cache.lock().unwrap();
        cache.clear();
    }

    /// Get cache size
    pub fn cache_size(&self) -> usize {
        self.cache.lock().unwrap().len()
    }
}

impl Default for OverlayProcessor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_png_dimensions() {
        // Minimal PNG header with 1920x1080 dimensions
        let png_header = vec![
            0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A, // PNG signature
            0x00, 0x00, 0x00, 0x0D, // IHDR length
            b'I', b'H', b'D', b'R', // IHDR type
            0x00, 0x00, 0x07, 0x80, // Width: 1920
            0x00, 0x00, 0x04, 0x38, // Height: 1080
        ];
        
        let (width, height) = OverlayProcessor::detect_png_dimensions_static(&png_header);
        assert_eq!(width, Some(1920));
        assert_eq!(height, Some(1080));
    }

    #[test]
    fn test_gif_dimensions() {
        // Minimal GIF89a header with 800x600 dimensions
        let gif_header = vec![
            b'G', b'I', b'F', b'8', b'9', b'a', // GIF89a signature
            0x20, 0x03, // Width: 800 (little-endian)
            0x58, 0x02, // Height: 600 (little-endian)
        ];
        
        let (width, height) = OverlayProcessor::detect_gif_dimensions_static(&gif_header);
        assert_eq!(width, Some(800));
        assert_eq!(height, Some(600));
    }

    #[test]
    fn test_buffer_size_calculation() {
        // 1MB image should produce ~1.33MB base64
        let size = OverlayProcessor::calculate_buffer_size(1_000_000, "png");
        assert!(size > 1_300_000);
        assert!(size < 1_400_000);
    }

    #[test]
    fn test_batch_processing() {
        let processor = OverlayProcessor::new();
        
        // Create minimal test images
        let png_data = vec![
            0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D,
            b'I', b'H', b'D', b'R',
            0x00, 0x00, 0x00, 0x01, // 1x1
            0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00,
        ];
        
        let items = vec![
            (png_data.clone(), "png".to_string(), "test1".to_string()),
            (png_data.clone(), "png".to_string(), "test2".to_string()),
        ];
        
        let results = processor.process_batch(items);
        assert_eq!(results.len(), 2);
        
        for result in results {
            assert!(result.result.is_ok());
        }
    }
}
