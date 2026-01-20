from moviepy.editor import VideoFileClip

path = r"E:\emili-adoption-video-gpt4-ready-patched - Copy\examples\pets\Bruno\Clips\clip 4.mp4"

print("Loading clip...")
clip = VideoFileClip(path)
print("Reading first frame...")
frame = clip.get_frame(0)
print("Duration:", clip.duration)
clip.close()
