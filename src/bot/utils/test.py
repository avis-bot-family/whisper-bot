


url = "https://api.telegram.org/file/bot{token}/{path}"

token = '1619204043:AAH56vPdnCBvS4P-z8cENZJ0VKXk4bAkOO8'
path = "voice/file_34.oga"

base_url = str(url).replace('{token}', f'{token}')
file_url = base_url.replace('{path}', f'{path}')

print(file_url)

