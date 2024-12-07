from gradio_client import Client, handle_file

client = Client("fancyfeast/joy-caption-pre-alpha")
result = client.predict(
		input_image=handle_file('https://i.pinimg.com/736x/10/74/6f/10746fd254ceab9596910a3d170b050e.jpg'),
		api_name="/stream_chat"
)
print(result)