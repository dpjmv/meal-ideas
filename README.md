MEAL IDEA DATABASE
==================

It's a web server with an sqlite database, I use it to store meal ideas. This way whenever I cook something new I can enter it and when I don't know what to eat, I just query the database for ideas. I can enter some parameters to search for meals, such as the time it requires or the ingredients. To achieve this I also store ingredients in the database. The app requires a password to be accessed.

The front end is a mess but, hey, it works. Also it's in french, but there's not that much text anyway, it's just a big form.

If my app happens to suit your needs, know that it is written in python and requires `flask` and `unidecode` modules. You also have to fill the config.py file according to the sample. And that's it, run it on your raspberry pi or whatever.