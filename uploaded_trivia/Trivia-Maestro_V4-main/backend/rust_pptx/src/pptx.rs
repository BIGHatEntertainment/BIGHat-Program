//! PPTX parsing implementation

use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, BufReader};
use std::sync::atomic::{AtomicI64, Ordering};
use zip::ZipArchive;
use quick_xml::Reader;
use quick_xml::events::Event;
use thiserror::Error;

use crate::models::{Slide, Element, SlideMetadata};

#[derive(Error, Debug)]
pub enum PptxError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("ZIP error: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("XML error: {0}")]
    Xml(#[from] quick_xml::Error),
}

pub struct PptxParser {
    slides_parsed: AtomicI64,
    elements_extracted: AtomicI64,
    images_processed: AtomicI64,
}

impl PptxParser {
    pub fn new() -> Self {
        PptxParser {
            slides_parsed: AtomicI64::new(0),
            elements_extracted: AtomicI64::new(0),
            images_processed: AtomicI64::new(0),
        }
    }
    
    pub fn get_stats(&self) -> HashMap<String, i64> {
        let mut stats = HashMap::new();
        stats.insert("slides_parsed".to_string(), self.slides_parsed.load(Ordering::Relaxed));
        stats.insert("elements_extracted".to_string(), self.elements_extracted.load(Ordering::Relaxed));
        stats.insert("images_processed".to_string(), self.images_processed.load(Ordering::Relaxed));
        stats
    }
    
    pub fn parse_pptx(
        &self,
        pptx_path: &str,
        start_order: i32,
        round_type: Option<&str>,
        round_number: Option<i32>,
    ) -> Result<Vec<Slide>, PptxError> {
        let file = File::open(pptx_path)?;
        let reader = BufReader::new(file);
        let mut archive = ZipArchive::new(reader)?;
        
        // Get slide dimensions from presentation.xml
        let (slide_width, slide_height) = self.get_slide_dimensions(&mut archive)?;
        
        // Find all slide files
        let slide_files: Vec<String> = (0..archive.len())
            .filter_map(|i| {
                let name = archive.by_index(i).ok()?.name().to_string();
                if name.starts_with("ppt/slides/slide") && name.ends_with(".xml") {
                    Some(name)
                } else {
                    None
                }
            })
            .collect();
        
        // Sort slide files numerically
        let mut slide_files = slide_files;
        slide_files.sort_by(|a, b| {
            let num_a = extract_slide_number(a);
            let num_b = extract_slide_number(b);
            num_a.cmp(&num_b)
        });
        
        let total_slides = slide_files.len() as i32;
        
        // Parse each slide
        let mut slides = Vec::new();
        for (idx, slide_file) in slide_files.iter().enumerate() {
            let slide = self.parse_slide(
                &mut archive,
                slide_file,
                idx as i32,
                start_order + idx as i32,
                slide_width,
                slide_height,
                round_type,
                round_number,
                total_slides,
            )?;
            slides.push(slide);
            self.slides_parsed.fetch_add(1, Ordering::Relaxed);
        }
        
        Ok(slides)
    }
    
    fn get_slide_dimensions(&self, archive: &mut ZipArchive<BufReader<File>>) -> Result<(i64, i64), PptxError> {
        // Default to 16:9 dimensions if presentation.xml not found
        let default_width: i64 = 12192000; // 12.7 inches in EMU
        let default_height: i64 = 6858000; // 7.14 inches in EMU
        
        let mut pres_file = match archive.by_name("ppt/presentation.xml") {
            Ok(f) => f,
            Err(_) => return Ok((default_width, default_height)),
        };
        
        let mut content = String::new();
        pres_file.read_to_string(&mut content)?;
        
        // Parse XML to find sldSz (slide size)
        let mut reader = Reader::from_str(&content);
        reader.config_mut().trim_text(true);
        
        let mut buf = Vec::new();
        loop {
            match reader.read_event_into(&mut buf) {
                Ok(Event::Empty(ref e)) if e.name().as_ref() == b"p:sldSz" => {
                    let mut width = default_width;
                    let mut height = default_height;
                    
                    for attr in e.attributes().flatten() {
                        match attr.key.as_ref() {
                            b"cx" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    width = val.parse().unwrap_or(default_width);
                                }
                            }
                            b"cy" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    height = val.parse().unwrap_or(default_height);
                                }
                            }
                            _ => {}
                        }
                    }
                    return Ok((width, height));
                }
                Ok(Event::Eof) => break,
                Err(e) => return Err(PptxError::Xml(e)),
                _ => {}
            }
            buf.clear();
        }
        
        Ok((default_width, default_height))
    }
    
    fn parse_slide(
        &self,
        archive: &mut ZipArchive<BufReader<File>>,
        slide_file: &str,
        idx: i32,
        order: i32,
        slide_width: i64,
        slide_height: i64,
        round_type: Option<&str>,
        round_number: Option<i32>,
        total_slides: i32,
    ) -> Result<Slide, PptxError> {
        let mut slide = Slide::new(order);
        
        // Read slide XML
        let mut file = archive.by_name(slide_file)?;
        let mut content = String::new();
        file.read_to_string(&mut content)?;
        drop(file);  // Release the borrow
        
        // Parse XML to extract shapes
        let mut reader = Reader::from_str(&content);
        reader.config_mut().trim_text(true);
        
        let mut buf = Vec::new();
        let mut current_shape: Option<ShapeInfo> = None;
        let mut in_text_body = false;
        let mut text_content = String::new();
        let mut in_paragraph = false;
        // Note: group_shapes tracking for future enhancement
        let mut _in_group = false;
        
        loop {
            match reader.read_event_into(&mut buf) {
                Ok(Event::Start(ref e)) => {
                    match e.name().as_ref() {
                        b"p:grpSp" => {
                            // Handle grouped shapes - shapes inside groups are still parsed
                            _in_group = true;
                        }
                        b"p:sp" => {
                            current_shape = Some(ShapeInfo::default());
                        }
                        b"p:txBody" => {
                            in_text_body = true;
                            text_content.clear();
                        }
                        b"a:p" => {
                            // Start of paragraph - add separator if we already have content
                            if in_text_body && !text_content.is_empty() && !text_content.ends_with('\n') {
                                text_content.push('\n');
                            }
                            in_paragraph = true;
                        }
                        _ => {}
                    }
                }
                Ok(Event::Empty(ref e)) => {
                    if let Some(ref mut shape) = current_shape {
                        match e.name().as_ref() {
                            b"a:off" => {
                                for attr in e.attributes().flatten() {
                                    match attr.key.as_ref() {
                                        b"x" => {
                                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                                shape.x = val.parse().unwrap_or(0);
                                            }
                                        }
                                        b"y" => {
                                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                                shape.y = val.parse().unwrap_or(0);
                                            }
                                        }
                                        _ => {}
                                    }
                                }
                            }
                            b"a:ext" => {
                                for attr in e.attributes().flatten() {
                                    match attr.key.as_ref() {
                                        b"cx" => {
                                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                                shape.width = val.parse().unwrap_or(0);
                                            }
                                        }
                                        b"cy" => {
                                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                                shape.height = val.parse().unwrap_or(0);
                                            }
                                        }
                                        _ => {}
                                    }
                                }
                            }
                            b"a:srgbClr" => {
                                for attr in e.attributes().flatten() {
                                    if attr.key.as_ref() == b"val" {
                                        if let Ok(val) = std::str::from_utf8(&attr.value) {
                                            shape.color = Some(format!("#{}", val));
                                        }
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }
                Ok(Event::Text(ref e)) if in_text_body && in_paragraph => {
                    if let Ok(text) = e.unescape() {
                        text_content.push_str(&text);
                    }
                }
                Ok(Event::End(ref e)) => {
                    match e.name().as_ref() {
                        b"p:grpSp" => {
                            _in_group = false;
                        }
                        b"a:p" => {
                            in_paragraph = false;
                        }
                        b"p:sp" => {
                            if let Some(shape) = current_shape.take() {
                                // Clean up text content - trim and normalize whitespace
                                let cleaned_text = text_content
                                    .lines()
                                    .map(|l| l.trim())
                                    .filter(|l| !l.is_empty())
                                    .collect::<Vec<_>>()
                                    .join("\n");
                                
                                if !cleaned_text.is_empty() {
                                    // Convert EMU to 1920x1080 coordinates
                                    let x = ((shape.x as f64 / slide_width as f64) * 1920.0) as i32;
                                    let y = ((shape.y as f64 / slide_height as f64) * 1080.0) as i32;
                                    let width = ((shape.width as f64 / slide_width as f64) * 1920.0) as i32;
                                    let height = ((shape.height as f64 / slide_height as f64) * 1080.0) as i32;
                                    
                                    let mut element = Element::new_text(
                                        cleaned_text,
                                        x, y, width, height,
                                    );
                                    
                                    if let Some(ref color) = shape.color {
                                        element.color = Some(color.clone());
                                    }
                                    
                                    slide.elements.push(element);
                                    self.elements_extracted.fetch_add(1, Ordering::Relaxed);
                                }
                            }
                            text_content.clear();
                        }
                        b"p:txBody" => {
                            in_text_body = false;
                            in_paragraph = false;
                        }
                        _ => {}
                    }
                }
                Ok(Event::Eof) => break,
                Err(e) => return Err(PptxError::Xml(e)),
                _ => {}
            }
            buf.clear();
        }
        
        // Add metadata
        if let Some(rt) = round_type {
            let mut meta = SlideMetadata::default();
            meta.round_type = Some(rt.to_string());
            meta.round_number = round_number;
            meta.slide_count = Some(total_slides);
            meta.slide_index_in_round = Some(idx);
            
            if idx == 0 {
                meta.is_round_title = true;
            }
            
            slide.metadata = Some(meta);
        }
        
        Ok(slide)
    }
}

#[derive(Default)]
struct ShapeInfo {
    x: i64,
    y: i64,
    width: i64,
    height: i64,
    color: Option<String>,
}

fn extract_slide_number(filename: &str) -> i32 {
    // Extract number from "ppt/slides/slide1.xml" -> 1
    filename
        .trim_start_matches("ppt/slides/slide")
        .trim_end_matches(".xml")
        .parse()
        .unwrap_or(0)
}
