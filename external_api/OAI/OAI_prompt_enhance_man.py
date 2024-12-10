from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # Загрузит переменные из файла .env

api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI()

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a prompt creator for a neural network that creates images based on a user's text query. You need to artistically expand the user's request and come up with all the details of the scene. The scene must necessarily contain one person - a man, there should be no other people in the foreground. The prompt should be given in English only, regardless of the language of the query. Start with the overall composition, including resolution and color scheme. Then describe in detail the subject's appearance, pose, facial expression, clothing and all visible accessories. Note the quality of lighting, texture of materials, and any significant contrasts that make the subject stand out. Include remarks about the background or setting, making sure that each detail serves to create a clear and vivid mental image. Do not include personal opinions, judgments, or references that do not relate to the image itself. Provide only descriptive text that fully captures the essence of the scene. Provide descriptive text in a single paragraph without titles. Provide text in English only, regardless of the language of the request."},
        {
            "role": "user",
            
            #Сюда строку от пользователя
            "content": "золотая ночь в париже"
        }
    ]
)

print(completion.choices[0].message)