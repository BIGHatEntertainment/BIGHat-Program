//! Data models for PPTX parsing

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde::{Serialize, Deserialize};

/// Represents a single element (text or image) on a slide
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Element {
    pub element_type: String,  // "text" or "image"
    pub content: Option<String>,
    pub src: Option<String>,  // base64 data URL for images
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
    pub font_size: Option<i32>,
    pub font_weight: Option<String>,
    pub color: Option<String>,
    pub text_align: Option<String>,
    pub font_family: Option<String>,
}

impl Element {
    pub fn new_text(
        content: String,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    ) -> Self {
        Element {
            element_type: "text".to_string(),
            content: Some(content),
            src: None,
            x,
            y,
            width,
            height,
            font_size: Some(30),
            font_weight: Some("normal".to_string()),
            color: Some("#FFFFFF".to_string()),
            text_align: Some("left".to_string()),
            font_family: Some("Montserrat, sans-serif".to_string()),
        }
    }
    
    #[allow(dead_code)]  // Reserved for future image extraction feature
    pub fn new_image(
        src: String,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    ) -> Self {
        Element {
            element_type: "image".to_string(),
            content: None,
            src: Some(src),
            x,
            y,
            width,
            height,
            font_size: None,
            font_weight: None,
            color: None,
            text_align: None,
            font_family: None,
        }
    }
    
    pub fn to_py_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        
        // Generate a unique ID
        let id = format!("el-{}-{}-{}", self.element_type, self.x, self.y);
        dict.set_item("id", id)?;
        dict.set_item("type", &self.element_type)?;
        dict.set_item("x", self.x)?;
        dict.set_item("y", self.y)?;
        dict.set_item("width", self.width)?;
        dict.set_item("height", self.height)?;
        
        if let Some(ref content) = self.content {
            dict.set_item("content", content)?;
        }
        if let Some(ref src) = self.src {
            dict.set_item("src", src)?;
        }
        if let Some(font_size) = self.font_size {
            dict.set_item("fontSize", font_size)?;
        }
        if let Some(ref font_weight) = self.font_weight {
            dict.set_item("fontWeight", font_weight)?;
        }
        if let Some(ref color) = self.color {
            dict.set_item("color", color)?;
        }
        if let Some(ref text_align) = self.text_align {
            dict.set_item("textAlign", text_align)?;
        }
        if let Some(ref font_family) = self.font_family {
            dict.set_item("fontFamily", font_family)?;
        }
        
        Ok(dict.unbind())
    }
}

/// Metadata for a slide
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SlideMetadata {
    pub round_type: Option<String>,
    pub round_number: Option<i32>,
    pub slide_count: Option<i32>,
    pub slide_index_in_round: Option<i32>,
    pub is_round_title: bool,
    pub is_score_slide: bool,
    pub is_answer_slide: bool,
}

impl SlideMetadata {
    pub fn to_py_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        
        if let Some(ref rt) = self.round_type {
            dict.set_item("roundType", rt)?;
        }
        if let Some(rn) = self.round_number {
            dict.set_item("roundNumber", rn)?;
        }
        if let Some(sc) = self.slide_count {
            dict.set_item("slideCount", sc)?;
        }
        if let Some(sir) = self.slide_index_in_round {
            dict.set_item("slideIndexInRound", sir)?;
        }
        if self.is_round_title {
            dict.set_item("isRoundTitle", true)?;
        }
        if self.is_score_slide {
            dict.set_item("isScoreSlide", true)?;
        }
        if self.is_answer_slide {
            dict.set_item("isAnswerSlide", true)?;
        }
        
        Ok(dict.unbind())
    }
}

/// Represents a single slide
#[derive(Debug, Clone)]
pub struct Slide {
    pub id: String,
    pub order: i32,
    pub background: String,
    pub elements: Vec<Element>,
    pub metadata: Option<SlideMetadata>,
}

impl Slide {
    pub fn new(order: i32) -> Self {
        Slide {
            id: format!("slide-{}", uuid::Uuid::new_v4()),
            order,
            background: "radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)".to_string(),
            elements: Vec::new(),
            metadata: None,
        }
    }
    
    pub fn to_py_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        
        dict.set_item("id", &self.id)?;
        dict.set_item("order", self.order)?;
        dict.set_item("background", &self.background)?;
        
        // Convert elements to Python list of dicts
        let elements_list = PyList::empty_bound(py);
        for element in &self.elements {
            let elem_dict = element.to_py_dict(py)?;
            elements_list.append(elem_dict)?;
        }
        dict.set_item("elements", elements_list)?;
        
        // Add metadata if present
        if let Some(ref meta) = self.metadata {
            let meta_dict = meta.to_py_dict(py)?;
            dict.set_item("metadata", meta_dict)?;
        }
        
        Ok(dict.unbind())
    }
}
