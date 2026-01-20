


from __future__ import annotations

try:
    from PIL import Image 


    if not hasattr(Image, "ANTIALIAS"):
        try:
          
            Image.ANTIALIAS = Image.Resampling.LANCZOS  
        except Exception:
            
            pass

except Exception as e:
   
    print(f"[compat] Pillow compatibility patch skipped: {e}")
    pass
