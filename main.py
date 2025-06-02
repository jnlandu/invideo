import os
import tempfile
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from pathlib import Path
import json

from moviepy import *
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
import textwrap


# Configuration and data classes
@dataclass
class VideoConfig:
    """Configuration for video generation"""
    width: int = 1920
    height: int = 1080
    fps: int = 24
    font_size: int = 60
    font_path: str = "Arial.ttf"
    text_color: Tuple[int, int, int] = (255, 255, 255)
    bg_overlay_color: Tuple[int, int, int, int] = (0, 0, 0, 128)
    margin: int = 100
    padding: int = 20
    words_per_minute: int = 150
    min_duration: float = 2.0
    tts_language: str = "en"
    tts_slow: bool = False


@dataclass
class ScriptSegment:
    """Represents a single script segment"""
    text: str
    duration: Optional[float] = None
    font_size: Optional[int] = None
    
    def __post_init__(self):
        if self.duration is None:
            self.duration = self._estimate_duration()
    
    def _estimate_duration(self, words_per_minute: int = 150) -> float:
        """Estimate duration based on text length"""
        word_count = len(self.text.split())
        duration = (word_count / words_per_minute) * 60
        return max(duration, 2.0)


class TextToVideoGenerator:
    """Enhanced text-to-video generator with better error handling and organization"""
    
    def __init__(self, config: VideoConfig = None):
        self.config = config or VideoConfig()
        self.temp_files: List[str] = []
        self.logger = self._setup_logging()
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    self.logger.debug(f"Cleaned up temp file: {temp_file}")
            except Exception as e:
                self.logger.warning(f"Failed to clean up {temp_file}: {e}")
        self.temp_files.clear()
    
    def _validate_inputs(self, script_data: List[Union[str, ScriptSegment]], 
                        bg_image_path: str, output_path: str) -> bool:
        """Validate input parameters"""
        if not script_data:
            raise ValueError("Script data cannot be empty")
        
        if not os.path.exists(bg_image_path):
            self.logger.warning(f"Background image not found: {bg_image_path}")
            return False
        
        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def _load_font(self, font_path: str, font_size: int) -> ImageFont.ImageFont:
        """Load font with fallback options"""
        try:
            return ImageFont.truetype(font_path, size=font_size)
        except (OSError, IOError):
            self.logger.warning(f"Could not load font {font_path}, trying fallbacks")
            
            # Try common system fonts
            fallback_fonts = [
                "/System/Library/Fonts/Arial.ttf",  # macOS
                "/Windows/Fonts/arial.ttf",         # Windows
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            ]
            
            for fallback in fallback_fonts:
                try:
                    return ImageFont.truetype(fallback, size=font_size)
                except (OSError, IOError):
                    continue
            
            # Final fallback to default font
            self.logger.warning("Using default font")
            return ImageFont.load_default()
    
    def _create_default_background(self, output_path: str) -> str:
        """Create a default background image"""
        self.logger.info("Creating default background image")
        
        # Create gradient background
        bg_image = Image.new("RGB", (self.config.width, self.config.height), (30, 30, 60))
        
        # Add gradient effect
        for y in range(self.config.height):
            color_value = int(30 + (y / self.config.height) * 50)
            for x in range(self.config.width):
                bg_image.putpixel((x, y), (color_value, color_value, color_value + 30))
        
        bg_image.save(output_path)
        return output_path
    
    def _create_text_overlay(self, text: str, segment: ScriptSegment) -> Image.Image:
        """Create text overlay with improved formatting"""
        bg_size = (self.config.width, self.config.height)
        overlay = Image.new("RGBA", bg_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Use segment-specific font size or default
        font_size = segment.font_size or self.config.font_size
        font = self._load_font(self.config.font_path, font_size)
        
        # Improved text wrapping
        max_width = bg_size[0] - self.config.margin
        
        # More accurate character width calculation
        test_text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz"
        avg_char_width = draw.textbbox((0, 0), test_text, font=font)[2] / len(test_text)
        chars_per_line = max(1, int(max_width / avg_char_width * 0.8))
        
        # Wrap text
        wrapped_text = textwrap.fill(text, width=chars_per_line)
        
        # Get text dimensions
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Center text
        x = (bg_size[0] - text_width) // 2
        y = (bg_size[1] - text_height) // 2
        
        # Add background rectangle for readability
        padding = self.config.padding
        bg_rect = [
            x - padding, y - padding,
            x + text_width + padding, y + text_height + padding
        ]
        draw.rectangle(bg_rect, fill=self.config.bg_overlay_color)
        
        # Draw text
        draw.multiline_text((x, y), wrapped_text, font=font, 
                          fill=self.config.text_color, align="center")
        
        return overlay
    
    def _generate_audio(self, text: str, segment_index: int) -> Optional[str]:
        """Generate TTS audio for text segment"""
        audio_path = f"temp_audio_{segment_index}_{os.getpid()}.mp3"
        self.temp_files.append(audio_path)
        
        try:
            tts = gTTS(text=text, lang=self.config.tts_language, slow=self.config.tts_slow)
            tts.save(audio_path)
            self.logger.debug(f"Generated audio for segment {segment_index}")
            return audio_path
        except Exception as e:
            self.logger.error(f"Failed to generate TTS for segment {segment_index}: {e}")
            return None
    
    def _create_video_segment(self, segment: ScriptSegment, segment_index: int, 
                            bg_image_path: str) -> Optional[VideoClip]:
        """Create a single video segment"""
        try:
            self.logger.info(f"Processing segment {segment_index + 1}: {segment.text[:50]}...")
            
            # Load background image
            try:
                bg_image = Image.open(bg_image_path).convert("RGB")
                bg_image = bg_image.resize((self.config.width, self.config.height), 
                                        Image.Resampling.LANCZOS)
            except Exception as e:
                self.logger.error(f"Error loading background: {e}")
                return None
            
            # Create text overlay
            text_overlay = self._create_text_overlay(segment.text, segment)
            
            # Composite images
            final_image = Image.alpha_composite(bg_image.convert("RGBA"), text_overlay)
            final_image = final_image.convert("RGB")
            
            # Save temporary image
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_image_path = tmp.name
                final_image.save(temp_image_path)
                self.temp_files.append(temp_image_path)
            
            # Generate audio
            audio_path = self._generate_audio(segment.text, segment_index)
            
            if audio_path and os.path.exists(audio_path):
                # Create clip with audio
                audio_clip = AudioFileClip(audio_path)
                duration = max(segment.duration, audio_clip.duration)
                # FIXED: use with_duration instead of set_duration
                video_clip = ImageClip(temp_image_path).with_duration(duration)
                # FIXED: use with_audio instead of set_audio
                final_clip = video_clip.with_audio(audio_clip)
                
                self.logger.debug(f"Created segment {segment_index + 1} with audio ({duration:.2f}s)")
                return final_clip
            else:
                # Create video-only clip
                self.logger.warning(f"Creating video-only clip for segment {segment_index + 1}")
                # FIXED: use with_duration instead of set_duration
                video_clip = ImageClip(temp_image_path).with_duration(segment.duration)
                return video_clip
                
        except Exception as e:
            self.logger.error(f"Failed to create segment {segment_index + 1}: {e}")
            return None
    
    def generate_video(self, script_data: List[Union[str, ScriptSegment, Tuple[str, float]]], 
                      bg_image_path: str = "bg_generic.jpg", 
                      output_path: str = "tutorial.mp4") -> bool:
        """
        Generate complete video from script data
        
        Args:
            script_data: List of strings, ScriptSegments, or (text, duration) tuples
            bg_image_path: Path to background image
            output_path: Output video file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Normalize script data to ScriptSegment objects
            segments = []
            for item in script_data:
                if isinstance(item, str):
                    segments.append(ScriptSegment(text=item))
                elif isinstance(item, tuple) and len(item) == 2:
                    segments.append(ScriptSegment(text=item[0], duration=item[1]))
                elif isinstance(item, ScriptSegment):
                    segments.append(item)
                else:
                    raise ValueError(f"Invalid script data format: {item}")
            
            # Create default background if needed
            if not os.path.exists(bg_image_path):
                bg_image_path = self._create_default_background(bg_image_path)
            
            # Validate inputs
            self._validate_inputs(segments, bg_image_path, output_path)
            
            # Generate video segments
            clips = []
            for i, segment in enumerate(segments):
                clip = self._create_video_segment(segment, i, bg_image_path)
                if clip:
                    clips.append(clip)
                else:
                    self.logger.error(f"Failed to create segment {i + 1}")
            
            if not clips:
                raise ValueError("No video segments were successfully created")
            
            # Concatenate clips
            self.logger.info("Combining all segments...")
            final_video = concatenate_videoclips(clips, method="compose")
            
            # Render final video
            self.logger.info(f"Rendering final video to {output_path}...")
            final_video.write_videofile(
                output_path,
                fps=self.config.fps,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                logger=None  # Suppress moviepy verbose output
            )
            
            self.logger.info(f"Video successfully created: {output_path}")
            
            # Close clips to free memory
            final_video.close()
            for clip in clips:
                clip.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to generate video: {e}")
            return False
        
        finally:
            self._cleanup_temp_files()
    
    def save_config(self, config_path: str):
        """Save current configuration to JSON file"""
        config_dict = {
            'width': self.config.width,
            'height': self.config.height,
            'fps': self.config.fps,
            'font_size': self.config.font_size,
            'font_path': self.config.font_path,
            'text_color': self.config.text_color,
            'bg_overlay_color': self.config.bg_overlay_color,
            'margin': self.config.margin,
            'padding': self.config.padding,
            'words_per_minute': self.config.words_per_minute,
            'min_duration': self.config.min_duration,
            'tts_language': self.config.tts_language,
            'tts_slow': self.config.tts_slow
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        self.logger.info(f"Configuration saved to {config_path}")
    
    @classmethod
    def load_config(cls, config_path: str) -> 'TextToVideoGenerator':
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        
        config = VideoConfig(**config_dict)
        return cls(config)


# Example usage and demo
def demo():
    """Demonstration of the enhanced text-to-video generator"""
    
    # Create custom configuration
    config = VideoConfig(
        font_size=72,
        text_color=(255, 255, 255),
        bg_overlay_color=(0, 0, 0, 150),
        words_per_minute=140
    )
    
    # Initialize generator
    generator = TextToVideoGenerator(config)
    
    # Script with various formats
    script = [
        ScriptSegment("Welcome to this enhanced tutorial!", duration=3),
        ScriptSegment("This new version has better error handling.", font_size=64),
        ("Configuration management makes it flexible.", 4),
        "And improved code organization makes it maintainable.",
        ScriptSegment("Let's see how it performs!", duration=2.5)
    ]
    
    # Generate video
    success = generator.generate_video(
        script_data=script,
        bg_image_path="bg_generic.jpg",
        output_path="enhanced_tutorial.mp4"
    )
    
    if success:
        print("✓ Video generation completed successfully!")
        
        # Save configuration for future use
        generator.save_config("video_config.json")
        print("✓ Configuration saved!")
    else:
        print("✗ Video generation failed!")


if __name__ == "__main__":
    demo()