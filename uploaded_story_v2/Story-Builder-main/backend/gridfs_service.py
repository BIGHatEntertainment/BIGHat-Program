"""
GridFS Service for storing large presentation slide data.
MongoDB has a 16MB document size limit, so we use GridFS to store
large slide data in chunks.
"""

import json
import logging
import gzip
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorDatabase
from bson import ObjectId
from typing import Optional, Dict, List, Any
from io import BytesIO

logger = logging.getLogger(__name__)

# Maximum size for a single response (10MB to be safe with infrastructure limits)
MAX_CHUNK_SIZE_MB = 10
MAX_CHUNK_SIZE_BYTES = MAX_CHUNK_SIZE_MB * 1024 * 1024


class GridFSService:
    """Service for storing and retrieving large slide data using GridFS"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.fs = AsyncIOMotorGridFSBucket(db, bucket_name='slides')
    
    async def store_slides(self, presentation_id: str, slides: List[Dict], metadata: Optional[Dict] = None) -> Dict:
        """
        Store slides data in GridFS, automatically chunking if necessary.
        Returns metadata about the stored data including chunk information.
        """
        try:
            # CRITICAL: Make a deep copy of slides to prevent external modifications
            import copy
            slides = copy.deepcopy(slides)
            
            # Debug: Check overlays at entry
            overlay_count_entry = sum(1 for s in slides if any(e.get('zIndex') == 1000 for e in s.get('elements', [])))
            logger.info(f"🔍 store_slides entry: {len(slides)} slides, {overlay_count_entry} with overlays")
            
            # Convert slides to JSON and compress
            slides_json = json.dumps(slides)
            slides_bytes = slides_json.encode('utf-8')
            original_size = len(slides_bytes)
            
            # Compress the data
            compressed_data = gzip.compress(slides_bytes)
            compressed_size = len(compressed_data)
            
            logger.info(f"📦 Storing slides for {presentation_id}: {original_size / (1024*1024):.2f}MB -> {compressed_size / (1024*1024):.2f}MB compressed")
            
            # Delete any existing slides for this presentation BEFORE creating new ones
            # Use underlying collection to get file IDs
            files_to_delete = []
            
            # Find by metadata.presentation_id
            cursor = self.db['slides.files'].find(
                {'metadata.presentation_id': presentation_id}, 
                {'_id': 1}
            )
            async for doc in cursor:
                files_to_delete.append(doc['_id'])
            
            # Find by filename pattern
            cursor2 = self.db['slides.files'].find(
                {'filename': {'$regex': f'^{presentation_id}_chunk_'}},
                {'_id': 1}
            )
            async for doc in cursor2:
                if doc['_id'] not in files_to_delete:
                    files_to_delete.append(doc['_id'])
            
            # Delete the old files using GridFS
            for file_id in files_to_delete:
                try:
                    await self.fs.delete(file_id)
                except Exception:
                    pass  # Ignore errors if file already deleted
            
            # Delete old metadata
            await self.db.slides_metadata.delete_one({'presentation_id': presentation_id})
            
            logger.info(f"🗑️ Deleted {len(files_to_delete)} old files for {presentation_id}")
            
            # Create chunks with strict size limits
            # Target max 8MB uncompressed per chunk for safe HTTP responses
            MAX_CHUNK_UNCOMPRESSED = 8 * 1024 * 1024  # 8MB
            
            chunks_info = []
            chunk_number = 0
            current_chunk_slides = []
            current_chunk_size = 0
            
            for idx, slide in enumerate(slides):
                slide_json = json.dumps(slide)
                slide_size = len(slide_json.encode('utf-8'))
                
                # If adding this slide would exceed limit, save current chunk first
                if current_chunk_slides and (current_chunk_size + slide_size > MAX_CHUNK_UNCOMPRESSED):
                    # Save the current chunk
                    chunk_json = json.dumps(current_chunk_slides)
                    chunk_bytes = chunk_json.encode('utf-8')
                    chunk_compressed = gzip.compress(chunk_bytes)
                    
                    start_idx = idx - len(current_chunk_slides)
                    file_id = await self.fs.upload_from_stream(
                        f"{presentation_id}_chunk_{chunk_number}",
                        BytesIO(chunk_compressed),
                        metadata={
                            'presentation_id': presentation_id,
                            'chunk_number': chunk_number,
                            'slide_start': start_idx,
                            'slide_end': idx - 1,
                            'slide_count': len(current_chunk_slides),
                            'original_size': len(chunk_bytes),
                            'compressed_size': len(chunk_compressed),
                            'content_type': 'application/gzip'
                        }
                    )
                    
                    chunks_info.append({
                        'chunk_number': chunk_number,
                        'file_id': str(file_id),
                        'slide_start': start_idx,
                        'slide_end': idx - 1,
                        'slide_count': len(current_chunk_slides)
                    })
                    
                    logger.info(f"📦 Chunk {chunk_number}: {len(current_chunk_slides)} slides, {len(chunk_bytes)/(1024*1024):.2f}MB")
                    
                    chunk_number += 1
                    current_chunk_slides = []
                    current_chunk_size = 0
                
                # Add slide to current chunk
                current_chunk_slides.append(slide)
                current_chunk_size += slide_size
            
            # Debug: Verify overlays still present
            overlay_count_after = sum(1 for s in slides if any(e.get('zIndex') == 1000 for e in s.get('elements', [])))
            logger.info(f"🔍 After chunking loop: {overlay_count_after} slides with overlays")
            
            # Save final chunk if there are remaining slides
            if current_chunk_slides:
                chunk_json = json.dumps(current_chunk_slides)
                chunk_bytes = chunk_json.encode('utf-8')
                chunk_compressed = gzip.compress(chunk_bytes)
                
                start_idx = len(slides) - len(current_chunk_slides)
                file_id = await self.fs.upload_from_stream(
                    f"{presentation_id}_chunk_{chunk_number}",
                    BytesIO(chunk_compressed),
                    metadata={
                        'presentation_id': presentation_id,
                        'chunk_number': chunk_number,
                        'slide_start': start_idx,
                        'slide_end': len(slides) - 1,
                        'slide_count': len(current_chunk_slides),
                        'original_size': len(chunk_bytes),
                        'compressed_size': len(chunk_compressed),
                        'content_type': 'application/gzip'
                    }
                )
                
                chunks_info.append({
                    'chunk_number': chunk_number,
                    'file_id': str(file_id),
                    'slide_start': start_idx,
                    'slide_end': len(slides) - 1,
                    'slide_count': len(current_chunk_slides)
                })
                
                logger.info(f"📦 Chunk {chunk_number}: {len(current_chunk_slides)} slides, {len(chunk_bytes)/(1024*1024):.2f}MB")
                chunk_number += 1
            
            # Store metadata in a separate collection for quick lookup
            total_slides = len(slides)
            slides_metadata = {
                'presentation_id': presentation_id,
                'total_slides': total_slides,
                'total_chunks': chunk_number,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'chunks': chunks_info,
                'metadata': metadata or {}
            }
            
            await self.db.slides_metadata.update_one(
                {'presentation_id': presentation_id},
                {'$set': slides_metadata},
                upsert=True
            )
            
            logger.info(f"✅ Stored {total_slides} slides in {chunk_number} chunks for {presentation_id}")
            
            return slides_metadata
            
        except Exception as e:
            logger.error(f"Error storing slides in GridFS: {str(e)}")
            raise
    
    async def get_slides_metadata(self, presentation_id: str) -> Optional[Dict]:
        """Get metadata about stored slides without loading the actual data"""
        return await self.db.slides_metadata.find_one(
            {'presentation_id': presentation_id},
            {'_id': 0}
        )
    
    async def get_slide_chunk(self, presentation_id: str, chunk_number: int) -> Optional[List[Dict]]:
        """Retrieve a specific chunk of slides"""
        try:
            # Find the chunk file
            cursor = self.fs.find({
                'filename': f"{presentation_id}_chunk_{chunk_number}"
            })
            
            file_doc = await cursor.to_list(length=1)
            if not file_doc:
                logger.warning(f"Chunk {chunk_number} not found for {presentation_id}")
                return None
            
            file_doc = file_doc[0]
            
            # Download and decompress
            stream = await self.fs.open_download_stream(file_doc['_id'])
            compressed_data = await stream.read()
            
            decompressed_data = gzip.decompress(compressed_data)
            slides = json.loads(decompressed_data.decode('utf-8'))
            
            logger.info(f"📥 Retrieved chunk {chunk_number} with {len(slides)} slides for {presentation_id}")
            
            # Return as dict with slides key for consistency
            return {'slides': slides}
            
        except Exception as e:
            logger.error(f"Error retrieving chunk {chunk_number}: {str(e)}")
            raise
    
    async def get_all_slides(self, presentation_id: str) -> Optional[List[Dict]]:
        """Retrieve all slides by loading all chunks"""
        try:
            metadata = await self.get_slides_metadata(presentation_id)
            if not metadata:
                return None
            
            all_slides = []
            for chunk_info in metadata['chunks']:
                chunk_data = await self.get_slide_chunk(presentation_id, chunk_info['chunk_number'])
                if chunk_data and chunk_data.get('slides'):
                    all_slides.extend(chunk_data['slides'])
            
            logger.info(f"📥 Retrieved all {len(all_slides)} slides for {presentation_id}")
            return all_slides
            
        except Exception as e:
            logger.error(f"Error retrieving all slides: {str(e)}")
            raise
    
    async def delete_slides(self, presentation_id: str) -> bool:
        """Delete all stored slides for a presentation"""
        try:
            # Find and delete all chunk files
            cursor = self.fs.find({'metadata.presentation_id': presentation_id})
            async for file_doc in cursor:
                await self.fs.delete(file_doc['_id'])
            
            # Also try deleting by filename pattern
            cursor = self.fs.find({'filename': {'$regex': f'^{presentation_id}_chunk_'}})
            async for file_doc in cursor:
                await self.fs.delete(file_doc['_id'])
            
            # Delete metadata
            await self.db.slides_metadata.delete_one({'presentation_id': presentation_id})
            
            logger.info(f"🗑️ Deleted slides for {presentation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting slides: {str(e)}")
            return False
    
    async def delete_presentation_slides(self, presentation_id: str) -> int:
        """Delete all cached slides for a specific presentation and return count"""
        try:
            deleted_count = 0
            
            # First, get metadata to find chunk file IDs
            metadata = await self.db.slides_metadata.find_one({'presentation_id': presentation_id})
            
            if metadata and 'chunks' in metadata:
                # Delete each chunk by its file_id
                for chunk_info in metadata['chunks']:
                    file_id = chunk_info.get('file_id')
                    if file_id:
                        try:
                            from bson import ObjectId
                            await self.fs.delete(ObjectId(file_id))
                            deleted_count += 1
                            logger.info(f"  Deleted chunk file: {file_id}")
                        except Exception as chunk_err:
                            logger.warning(f"  Could not delete chunk {file_id}: {chunk_err}")
            
            # Also try finding by metadata.presentation_id
            cursor = self.fs.find({'metadata.presentation_id': presentation_id})
            async for file_doc in cursor:
                try:
                    await self.fs.delete(file_doc['_id'])
                    deleted_count += 1
                except:
                    pass
            
            # Delete by filename pattern  
            cursor = self.fs.find({'filename': {'$regex': f'^{presentation_id}_chunk_'}})
            async for file_doc in cursor:
                try:
                    await self.fs.delete(file_doc['_id'])
                    deleted_count += 1
                except:
                    pass
            
            # Delete metadata
            await self.db.slides_metadata.delete_one({'presentation_id': presentation_id})
            
            logger.info(f"🗑️ Deleted {deleted_count} cached items for {presentation_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting presentation slides: {str(e)}")
            return 0
    
    async def delete_all_slides(self) -> int:
        """Delete ALL cached slides (admin function)"""
        try:
            deleted_count = 0
            
            # Delete all files in GridFS
            cursor = self.fs.find({})
            async for file_doc in cursor:
                await self.fs.delete(file_doc['_id'])
                deleted_count += 1
            
            # Delete all metadata
            result = await self.db.slides_metadata.delete_many({})
            
            logger.info(f"🗑️ Deleted ALL cache: {deleted_count} files")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting all slides: {str(e)}")
            return 0
    
    async def has_slides(self, presentation_id: str) -> bool:
        """Check if slides exist for a presentation"""
        metadata = await self.get_slides_metadata(presentation_id)
        return metadata is not None


# Global instance (will be set by server.py)
gridfs_service: Optional[GridFSService] = None


def get_gridfs_service() -> GridFSService:
    """Get the global GridFS service instance"""
    if gridfs_service is None:
        raise RuntimeError("GridFS service not initialized")
    return gridfs_service


def init_gridfs_service(db: AsyncIOMotorDatabase) -> GridFSService:
    """Initialize the global GridFS service"""
    global gridfs_service
    gridfs_service = GridFSService(db)
    return gridfs_service
