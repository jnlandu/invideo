from moviepy import *
from gtts import gTTS
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import textwrap

def create_text_overlay(text, bg_size, font_path="Arial.ttf", font_size=48, text_color=(255, 255, 255)):
    """Create a text overlay image with proper text wrapping and positioning"""
    # Create transparent image for text overlay
    overlay = Image.new("RGBA", bg_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        font = ImageFont.truetype(font_path, size=font_size)
    except (OSError, IOError):
        # Fallback to default font if custom font not found
        try:
            font = ImageFont.load_default()
            print(f"Warning: Could not load font {font_path}, using default font")
        except:
            font = ImageFont.load_default()
    
    # Wrap text to fit the image width
    max_width = bg_size[0] - 100  # Leave 50px margin on each side
    
    # Estimate characters per line based on average character width
    avg_char_width = font.getbbox("A")[2]  # Width of 'A' character
    chars_per_line = max_width // avg_char_width
    
    # Wrap the text
    wrapped_text = textwrap.fill(text, width=int(chars_per_line * 0.8))
    
    # Get text bounding box
    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Center the text
    x = (bg_size[0] - text_width) // 2
    y = (bg_size[1] - text_height) // 2
    
    # Add semi-transparent background for better readability
    padding = 20
    bg_rect = [
        x - padding, 
        y - padding, 
        x + text_width + padding, 
        y + text_height + padding
    ]
    draw.rectangle(bg_rect, fill=(0, 0, 0, 128))  # Semi-transparent black
    
    # Draw the text
    draw.multiline_text((x, y), wrapped_text, font=font, fill=text_color, align="center")
    
    return overlay

def make_clip(text, duration, bg_image_path, font_path="Arial.ttf", font_size=48):
    """Create a video clip with text overlay on background image"""
    
    # Load and prepare background image
    try:
        bg_image = Image.open(bg_image_path).convert("RGB")
    except Exception as e:
        print(f"Error loading background image {bg_image_path}: {e}")
        # Create a default background
        bg_image = Image.new("RGB", (1920, 1080), (50, 50, 50))
    
    # Resize to standard video dimensions if needed
    target_size = (1920, 1080)
    bg_image = bg_image.resize(target_size, Image.Resampling.LANCZOS)
    
    # Create text overlay
    text_overlay = create_text_overlay(text, target_size, font_path, font_size)
    
    # Composite the images
    final_image = Image.alpha_composite(bg_image.convert("RGBA"), text_overlay)
    final_image = final_image.convert("RGB")
    
    # Save temporary image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        temp_image_path = tmp.name
        final_image.save(temp_image_path)
    
    # Create MoviePy clip
    video_clip = ImageClip(temp_image_path).with_duration(duration)
    
    # Clean up temporary file
    os.unlink(temp_image_path)
    
    return video_clip

def generate_audio_for_text(text, output_path, lang="en", slow=False):
    """Generate TTS audio for given text"""
    try:
        tts = gTTS(text=text, lang=lang, slow=slow)
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"Error generating TTS for text: {e}")
        return False

def estimate_speech_duration(text, words_per_minute=150):
    """Estimate duration based on text length and speaking speed"""
    word_count = len(text.split())
    duration = (word_count / words_per_minute) * 60
    return max(duration, 2.0)  # Minimum 2 seconds

def create_text_to_video(script_data, bg_image_path="bg_generic.jpg", output_path="tutorial.mp4"):
    """
    Create a complete text-to-video from script data
    
    Args:
        script_data: List of tuples (text, duration) or list of strings
        bg_image_path: Path to background image
        output_path: Output video file path
    """
    
    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Process script data
    if isinstance(script_data[0], str):
        # If just text strings, estimate durations
        processed_script = [(text, estimate_speech_duration(text)) for text in script_data]
    else:
        # Already has durations
        processed_script = script_data
    
    clips = []
    temp_files = []
    
    try:
        for i, (text_chunk, duration) in enumerate(processed_script):
            print(f"Processing segment {i+1}/{len(processed_script)}: {text_chunk[:50]}...")
            
            # Generate TTS audio
            audio_path = f"temp_audio_{i}.mp3"
            temp_files.append(audio_path)
            
            if generate_audio_for_text(text_chunk, audio_path):
                # Load audio and adjust duration if needed
                audio_clip = AudioFileClip(audio_path)
                actual_duration = audio_clip.duration
                
                # Use actual audio duration if it's longer than estimated
                final_duration = max(duration, actual_duration)
                
                # Create video clip
                video_clip = make_clip(
                    text_chunk, 
                    final_duration, 
                    bg_image_path,
                    font_size=60  # Larger font for better readability
                )
                
                # Set audio
                final_clip = video_clip.with_audio(audio_clip)
                clips.append(final_clip)
                
            else:
                # If TTS fails, create video-only clip
                print(f"TTS failed for segment {i+1}, creating video-only clip")
                video_clip = make_clip(text_chunk, duration, bg_image_path)
                clips.append(video_clip)
        
        if not clips:
            raise ValueError("No clips were successfully created")
        
        # Concatenate all clips
        print("Combining all segments...")
        final_video = concatenate_videoclips(clips, method="compose")
        
        # Write final video - FIXED: removed verbose parameter
        print(f"Rendering final video to {output_path}...")
        final_video.write_videofile(
            output_path, 
            fps=24,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True
        )
        
        print(f"Video successfully created: {output_path}")
        
    except Exception as e:
        print(f"Error creating video: {e}")
        raise
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except:
                pass
        
        # Close clips to free memory
        for clip in clips:
            try:
                clip.close()
            except:
                pass

# Example usage
if __name__ == "__main__":
    # Script with estimated durations
    script = [
        ("Welcome to this tutorial on how to animate your images.", 4),
        ("First, we'll cover the basics of motion planning.", 3),
        ("This involves understanding coordinate systems and transformations.", 5),
        ("Next, we'll explore different animation techniques.", 4),
        ("Finally, we'll put it all together in a complete example.", 5),
    ]
    
    # Alternative: Just text (durations will be estimated)
    simple_script = [
        "Welcome to this tutorial on how to animate your images.",
        "First, we'll cover the basics of motion planning.",
        "This involves understanding coordinate systems and transformations.",
        "Next, we'll explore different animation techniques.",
        "Finally, we'll put it all together in a complete example."
    ]
    
    # Create a default background if none exists
    bg_path = "bg_generic.jpg"
    if not os.path.exists(bg_path):
        print("Creating default background image...")
        default_bg = Image.new("RGB", (1920, 1080), (30, 30, 60))  # Dark blue gradient
        # Add a simple gradient effect
        for y in range(1080):
            color_value = int(30 + (y / 1080) * 50)
            for x in range(1920):
                default_bg.putpixel((x, y), (color_value, color_value, color_value + 30))
        default_bg.save(bg_path)
    
    # Create the video
    try:
        create_text_to_video(script, bg_path, "tutorial.mp4")
    except Exception as e:
        print(f"Failed to create video: {e}")
        print("Trying with simple script...")
        create_text_to_video(simple_script, bg_path, "tutorial_simple.mp4")