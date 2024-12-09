import asyncio
from gradio_client import Client, handle_file

async def fetch_result(client, **kwargs):
    loop = asyncio.get_running_loop()
    # Предполагается, что predict синхронный, поэтому запускаем в пуле потоков
    return await loop.run_in_executor(None, lambda: client.predict(**kwargs))

async def main():
    # Создаем клиентов для каждой модели
    client1 = Client("fancyfeast/joy-caption-pre-alpha")
    client2 = Client("fancyfeast/joy-caption-alpha-two")

    # Подготавливаем общий входной файл
    img = handle_file('https://i.pinimg.com/736x/10/74/6f/10746fd254ceab9596910a3d170b050e.jpg')

    # Формируем задачи на выполнение
    task1 = fetch_result(client1, input_image=img, api_name="/stream_chat")
    task2 = fetch_result(
        client2,
        input_image=img,
        caption_type="Descriptive",
        caption_length="long",
        extra_options=[],
        name_input="",
        custom_prompt="",
        api_name="/stream_chat"
    )

    # Запускаем обе задачи параллельно и ждем результатов
    result1, result2 = await asyncio.gather(task1, task2)

    # Выводим результаты каждой модели отдельно
    print("Result from fancyfeast/joy-caption-pre-alpha:", result1)
    print("Result from fancyfeast/joy-caption-alpha-two:", result2)

if __name__ == "__main__":
    asyncio.run(main())
