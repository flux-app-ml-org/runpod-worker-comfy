from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # Загрузит переменные из файла .env

api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI()

response = client.chat.completions.create(
  model="gpt-4o-mini",
  messages=[
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe the image by focusing solely on its visual elements. Begin by noting the overall composition, including orientation, resolution, and color scheme. Then detail the subject’s physical appearance, pose, facial expression, and attire, as well as any visible accessories. Mention the quality of lighting, the texture of materials, and any significant contrasts that highlight the subject. Include observations about the background or setting, ensuring that each detail serves to create a clear and vivid mental picture. Do not include personal opinions, judgments, or references outside of the image itself. Only provide descriptive text that fully captures the essence of the scene. Provide only descriptive text that fully captures the essence of the scene. Provide text in English only, regardless of the language of the request."},
        {
          "type": "image_url",
          "image_url": {
          # входящее изображение нужно обязательно уменьшить до 1 мп
            "url": "https://i.pinimg.com/736x/1d/ed/01/1ded01c200cddaa273354ea3193718b6.jpg",
          },
        },
      ],
    }
  ],
  max_tokens=300,
)

print(response.choices[0])

