from gradio_client import Client, handle_file

client = Client("fancyfeast/joy-caption-alpha-two")
result = client.predict(
		input_image=handle_file('https://i.pinimg.com/736x/10/74/6f/10746fd254ceab9596910a3d170b050e.jpg'),
		caption_type="Descriptive",
		caption_length="long",
		extra_options=[],
		name_input="",
		custom_prompt="",
		api_name="/stream_chat"
)
print(result)